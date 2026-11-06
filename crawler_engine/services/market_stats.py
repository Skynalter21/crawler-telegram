import statistics
from typing import Any

from crawler_engine.domain.models import ProductOffer


class MarketPriceStatsCalculator:
    """
    Serviço de domínio responsável por calcular estatísticas de mercado separadas
    entre Produtos Novos (Varejo) e Produtos Usados/Seminovos (Recommerce: OLX, Enjoei,
    Facebook Marketplace, etc.) (Single Responsibility Principle).

    Utiliza Média Aparada (Trimmed Mean — removendo extremos superiores/inferiores quando
    a amostra possui >= 6 itens) e Mediana para evitar distorções causadas por anúncios fora da curva.
    """

    @staticmethod
    def _compute_segment_stats(offers: list[ProductOffer]) -> dict[str, Any] | None:
        if not offers:
            return None

        prices = sorted(o.price for o in offers)
        n = len(prices)

        # Média aparada (remove 1 extremo de cada ponta se houver >= 6 ofertas)
        if n >= 6:
            trimmed = prices[1:-1]
            avg_price = sum(trimmed) / len(trimmed)
        else:
            avg_price = sum(prices) / n

        median_price = statistics.median(prices)
        min_offer = min(offers, key=lambda o: o.price)
        max_offer = max(offers, key=lambda o: o.price)

        return {
            "count": n,
            "avg_price": round(avg_price, 2),
            "median_price": round(median_price, 2),
            "min_price": round(min_offer.price, 2),
            "max_price": round(max_offer.price, 2),
            "lowest_offer": {
                "title": min_offer.title,
                "price": min_offer.price,
                "store": min_offer.store,
                "url": min_offer.url,
            },
        }

    def calculate(self, offers: list[ProductOffer]) -> dict[str, Any]:
        new_offers = [o for o in offers if not o.is_used]
        used_offers = [o for o in offers if o.is_used]

        new_stats = self._compute_segment_stats(new_offers)
        used_stats = self._compute_segment_stats(used_offers)

        comparison: dict[str, Any] | None = None
        if new_stats and used_stats and new_stats["avg_price"] > 0:
            avg_diff = new_stats["avg_price"] - used_stats["avg_price"]
            avg_pct = (avg_diff / new_stats["avg_price"]) * 100

            min_diff = new_stats["min_price"] - used_stats["min_price"]
            min_pct = (
                (min_diff / new_stats["min_price"]) * 100
                if new_stats["min_price"] > 0
                else 0.0
            )

            comparison = {
                "avg_savings_brl": round(avg_diff, 2),
                "avg_savings_pct": round(avg_pct, 1),
                "min_savings_brl": round(min_diff, 2),
                "min_savings_pct": round(min_pct, 1),
            }

        return {
            "new": new_stats,
            "used": used_stats,
            "comparison": comparison,
        }

