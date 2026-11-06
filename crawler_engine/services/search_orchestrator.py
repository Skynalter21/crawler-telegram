import asyncio
import time
from datetime import datetime
from typing import Any, Sequence
import httpx

from crawler_engine.domain.interfaces import (
    PriceHistoryGateway,
    PriceScraperProvider,
    ProductMatcher,
    SearchCacheRepository,
)
from crawler_engine.domain.models import ProductOffer, SearchCriteria
from crawler_engine.services.deduplicator import MedianPriceOutlierFilter, OfferDeduplicator
from crawler_engine.services.market_stats import MarketPriceStatsCalculator
from crawler_engine.utils.text_normalizer import correct_query_typos, normalize_text


class PriceSearchOrchestrator:
    """
    Caso de Uso / Serviço de Aplicação que orquestra a busca de menor preço (SRP & DIP).
    Depende exclusivamente de abstrações (interfaces) e serviços de domínio injetados:
    - Provedores de scraping (PriceScraperProvider)
    - Avaliador de relevância (ProductMatcher)
    - Deduplicador (OfferDeduplicator)
    - Filtro estatístico de outliers (MedianPriceOutlierFilter)
    - Calculadora de estatísticas de mercado Novos vs. Usados (MarketPriceStatsCalculator)
    - Gateway de histórico de preços (PriceHistoryGateway)
    - Repositório de cache (SearchCacheRepository)
    """

    def __init__(
        self,
        providers: Sequence[PriceScraperProvider],
        matcher: ProductMatcher,
        deduplicator: OfferDeduplicator,
        outlier_filter: MedianPriceOutlierFilter,
        history_gateway: PriceHistoryGateway,
        cache: SearchCacheRepository,
        stats_calculator: MarketPriceStatsCalculator | None = None,
    ) -> None:
        self.providers = providers
        self.matcher = matcher
        self.deduplicator = deduplicator
        self.outlier_filter = outlier_filter
        self.history_gateway = history_gateway
        self.cache = cache
        self.stats_calculator = stats_calculator or MarketPriceStatsCalculator()

    async def execute_search(self, criteria: SearchCriteria) -> dict[str, Any]:
        t0 = time.perf_counter()
        raw_query = criteria.query.strip()
        cleaned_query = correct_query_typos(raw_query) if raw_query else ""
        if not cleaned_query:
            return {
                "query": "",
                "lowest": None,
                "results": [],
                "total": 0,
                "stores": [],
                "market_stats": {"new": None, "used": None, "comparison": None},
                "price_history": None,
                "history_products": [],
                "cached": False,
                "cached_at": None,
                "elapsed_ms": 0,
            }

        normalized_criteria = SearchCriteria(
            query=cleaned_query,
            include_used=criteria.include_used,
            strict_model=criteria.strict_model,
            force_refresh=criteria.force_refresh,
        )

        cache_key = (
            normalize_text(cleaned_query),
            normalized_criteria.include_used,
            normalized_criteria.strict_model,
        )

        if not normalized_criteria.force_refresh:
            cached_hit = self.cache.get(cache_key)
            if cached_hit is not None:
                saved_time_str, cached_payload = cached_hit
                elapsed = round((time.perf_counter() - t0) * 1000, 1)
                return {
                    **cached_payload,
                    "cached": True,
                    "cached_at": saved_time_str,
                    "elapsed_ms": elapsed,
                }

        async with httpx.AsyncClient() as client:
            # 1. Executa todos os provedores de scraping concorrentemente (OCP)
            provider_batches = await asyncio.gather(
                *(p.scrape(client, cleaned_query) for p in self.providers)
            )
            raw_offers: list[ProductOffer] = [
                offer for batch in provider_batches for offer in batch
            ]

            # 2. Remove anúncios duplicados preservando links diretos, fotos e product_id
            unique_offers = self.deduplicator.deduplicate(raw_offers)

            # 3. Avalia compatibilidade semântica (avaliando primeiro com include_used=True
            # para podermos calcular a média de usados vs. novos mesmo se o filtro estiver ativo)
            eval_criteria_all = SearchCriteria(
                query=cleaned_query,
                include_used=True,
                strict_model=normalized_criteria.strict_model,
            )
            matched_offers: list[ProductOffer] = []
            for offer in unique_offers:
                evaluation = self.matcher.evaluate(offer.title, eval_criteria_all)
                if evaluation.is_valid:
                    matched_offers.append(
                        offer.model_copy(
                            update={
                                "relevance": evaluation.relevance_score,
                                "exact_model": evaluation.is_exact_model,
                                "is_used": offer.is_used or evaluation.is_used_item,
                            }
                        )
                    )

            # 4. Aplica filtro de Modelo Exato se ativo
            if normalized_criteria.strict_model:
                exact_only = [o for o in matched_offers if o.exact_model]
                if exact_only:
                    matched_offers = exact_only

            # 5. Remove outliers estatísticos de preço (< 28% da mediana)
            matched_offers = self.outlier_filter.filter_outliers(matched_offers)

            # 6. Calcula as médias e estatísticas comparativas (Novos vs. Usados/Seminovos)
            market_stats = self.stats_calculator.calculate(matched_offers)

            # 7. Se o usuário pediu apenas produtos novos (include_used=False), filtra os usados
            if not normalized_criteria.include_used:
                matched_offers = [o for o in matched_offers if not o.is_used]

            # 8. Ordena pelo menor preço (desempate por maior relevância)
            matched_offers.sort(key=lambda o: (o.price, -o.relevance))

            # 9. Identifica produtos que possuem histórico de preços disponível
            history_products: list[dict[str, Any]] = []
            seen_pids: set[str] = set()
            for offer in matched_offers:
                if offer.product_id and offer.product_id not in seen_pids:
                    seen_pids.add(offer.product_id)
                    history_products.append(
                        {
                            "product_id": offer.product_id,
                            "title": offer.title,
                            "current_price": offer.price,
                        }
                    )

            price_history_data: dict[str, Any] | None = None
            if history_products:
                primary = history_products[0]
                points = await self.history_gateway.fetch_history(
                    client, primary["product_id"]
                )
                if points:
                    price_history_data = {
                        "product_id": primary["product_id"],
                        "title": primary["title"],
                        "points": [pt.model_dump() for pt in points],
                    }

        serialized_results = [o.to_dict() for o in matched_offers]
        stores_found = sorted({o.store for o in matched_offers})
        lowest = serialized_results[0] if serialized_results else None
        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
        now_str = datetime.now().strftime("%H:%M:%S")

        payload = {
            "query": cleaned_query,
            "lowest": lowest,
            "total": len(serialized_results),
            "stores": stores_found,
            "market_stats": market_stats,
            "price_history": price_history_data,
            "history_products": history_products,
            "results": serialized_results,
            "cached": False,
            "cached_at": now_str,
            "elapsed_ms": elapsed_ms,
        }

        if serialized_results:
            saved_at = self.cache.set(cache_key, payload)
            payload["cached_at"] = saved_at

        return payload

    async def get_product_history(self, product_id: str, title: str = "") -> dict[str, Any]:
        async with httpx.AsyncClient() as client:
            points = await self.history_gateway.fetch_history(client, product_id)
        return {
            "product_id": product_id,
            "title": title,
            "points": [pt.model_dump() for pt in points],
        }
