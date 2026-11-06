from abc import ABC, abstractmethod
import httpx
from bs4 import BeautifulSoup

from crawler_engine.domain.models import ProductOffer

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
}


class BaseScraperProvider(ABC):
    """
    Classe base abstrata para provedores de scraping (Template Method Pattern).
    Garante cumprimento do Liskov Substitution Principle (LSP) e Open/Closed Principle (OCP):
    qualquer subclasse pode ser plugada no orquestrador sem risco de quebrar a execução
    global caso um site específico sofra timeout ou mude o layout.
    """

    def __init__(self, timeout: float = 12.0) -> None:
        self.timeout = timeout

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Identificador único da fonte de dados."""

    async def scrape(self, client: httpx.AsyncClient, query: str) -> list[ProductOffer]:
        """Método Template que executa a coleta com isolamento seguro de falhas."""
        try:
            return await self._scrape_impl(client, query)
        except Exception:
            return []

    async def _fetch_html(self, client: httpx.AsyncClient, url: str) -> BeautifulSoup | None:
        """Helper reutilizável para buscar e parsear páginas HTML com segurança."""
        try:
            resp = await client.get(
                url,
                headers=DEFAULT_HEADERS,
                follow_redirects=True,
                timeout=self.timeout,
            )
            if resp.status_code != 200:
                return None
            return BeautifulSoup(resp.text, "html.parser")
        except httpx.HTTPError:
            return None

    @abstractmethod
    async def _scrape_impl(self, client: httpx.AsyncClient, query: str) -> list[ProductOffer]:
        """Implementação específica de cada motor ou loja."""

