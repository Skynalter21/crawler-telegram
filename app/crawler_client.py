import logging
from typing import Any
import httpx

from app.spell_corrector import correct_query_local, fetch_online_suggestion
from crawler_engine.dependencies import get_search_orchestrator
from crawler_engine.domain.models import SearchCriteria

logger = logging.getLogger(__name__)


class CrawlerClientError(Exception):
    """Erro ao consultar o motor do Crawler de Preços."""


BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
}


class CrawlerClient:
    """
    Cliente para consultar o Caçador de Menor Preço (nas 13 lojas).
    Executa diretamente via motor embutido (crawler_engine) para funcionar tanto
    localmente quanto no Render em um único serviço, sem precisar subir 2 servidores.
    """

    def __init__(self, base_url: str = "http://localhost:8000", timeout: float = 35.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._orchestrator = get_search_orchestrator()

    async def _run_search(
        self,
        query: str,
        include_used: bool,
        strict_model: bool,
        force_refresh: bool,
    ) -> dict[str, Any]:
        criteria = SearchCriteria(
            query=query,
            include_used=include_used,
            strict_model=strict_model,
            force_refresh=force_refresh,
        )
        return await self._orchestrator.execute_search(criteria)

    async def search_product(
        self,
        query: str,
        include_used: bool = True,
        strict_model: bool = True,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        """
        Executa a busca nas 13 fontes com correção ortográfica e aproximação:
        1. Corrige erros de digitação locais/fonéticos (ex: 'ayirfrier' -> 'air fryer')
        2. Se retornar 0 ofertas, consulta sugestões de Autocomplete online e tenta novamente
        3. Se ainda retornar 0 ofertas, flexibiliza strict_model=False
        """
        raw_query = query.strip()
        effective_query = correct_query_local(raw_query)
        if effective_query.lower() != raw_query.lower():
            logger.info("Correção ortográfica aplicada: '%s' -> '%s'", raw_query, effective_query)

        try:
            data = await self._run_search(
                query=effective_query,
                include_used=include_used,
                strict_model=strict_model,
                force_refresh=force_refresh,
            )

            # Fallback 1: Se não achou nada, tenta buscar sugestão via Autocomplete online
            if not data.get("results"):
                online_suggested = await fetch_online_suggestion(raw_query)
                if online_suggested and online_suggested.lower() != effective_query.lower():
                    logger.info(
                        "Tentando sugestão online para '%s' -> '%s'",
                        raw_query,
                        online_suggested,
                    )
                    effective_query = online_suggested
                    data = await self._run_search(
                        query=effective_query,
                        include_used=include_used,
                        strict_model=strict_model,
                        force_refresh=force_refresh,
                    )

            # Fallback 2: Se ainda não achou nada e strict_model=True, flexibiliza variantes
            if not data.get("results") and strict_model:
                data = await self._run_search(
                    query=effective_query,
                    include_used=include_used,
                    strict_model=False,
                    force_refresh=force_refresh,
                )

            data["original_query"] = raw_query
            data["corrected_query"] = (
                effective_query if effective_query.lower() != raw_query.lower() else None
            )
            return data
        except Exception as exc:
            raise CrawlerClientError(f"Falha ao buscar '{raw_query}' no Crawler: {exc}") from exc

    async def fetch_image_bytes(self, image_url: str) -> bytes | None:
        """
        Baixa os bytes da imagem do produto para enviar via send_photo no Telegram,
        evitando bloqueios de CDN (ex: Mercado Livre, OLX, KaBuM, Zoom).
        """
        if not image_url or not image_url.startswith("http"):
            return None
        try:
            async with httpx.AsyncClient(
                timeout=10.0,
                follow_redirects=True,
                headers=BROWSER_HEADERS,
            ) as client:
                resp = await client.get(image_url)
                if resp.status_code == 200 and len(resp.content) > 500:
                    return resp.content
        except Exception:
            return None
        return None

    async def shorten_url(self, long_url: str) -> str:
        """
        Encurta a URL real da loja usando TinyURL / is.gd para gerar um link curto
        100% funcional que abre direto na loja ao clicar.
        """
        if not long_url or not long_url.startswith("http"):
            return long_url
        if len(long_url) <= 45:
            return long_url

        try:
            async with httpx.AsyncClient(timeout=3.5, follow_redirects=True) as client:
                resp = await client.get(
                    "https://tinyurl.com/api-create.php",
                    params={"url": long_url},
                )
                if resp.status_code == 200 and resp.text.strip().startswith("http"):
                    return resp.text.strip()
        except Exception:
            pass

        try:
            async with httpx.AsyncClient(timeout=3.5, follow_redirects=True) as client:
                resp = await client.get(
                    "https://is.gd/create.php",
                    params={"format": "simple", "url": long_url},
                )
                if resp.status_code == 200 and resp.text.strip().startswith("http"):
                    return resp.text.strip()
        except Exception:
            pass

        return long_url
