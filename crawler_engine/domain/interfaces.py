from typing import Any, Protocol
import httpx

from crawler_engine.domain.models import (
    MatchEvaluation,
    PricePoint,
    ProductOffer,
    SearchCriteria,
)


class PriceScraperProvider(Protocol):
    """Contrato (Interface) para qualquer motor/loja de scraping (OCP & LSP)."""

    @property
    def source_name(self) -> str:
        ...

    async def scrape(self, client: httpx.AsyncClient, query: str) -> list[ProductOffer]:
        ...


class ProductMatcher(Protocol):
    """Contrato para avaliadores de relevância e precisão de título (SRP & DIP)."""

    def evaluate(self, title: str, criteria: SearchCriteria) -> MatchEvaluation:
        ...


class PriceHistoryGateway(Protocol):
    """Contrato para provedor de série histórica de preços (ISP & DIP)."""

    async def fetch_history(
        self, client: httpx.AsyncClient, product_id: str
    ) -> list[PricePoint]:
        ...


class SearchCacheRepository(Protocol):
    """Contrato para armazenamento de cache de buscas com TTL (ISP & DIP)."""

    def get(self, key: tuple[str, bool, bool]) -> tuple[str, dict[str, Any]] | None:
        ...

    def set(self, key: tuple[str, bool, bool], payload: dict[str, Any]) -> str:
        ...


class WatchlistRepository(Protocol):
    """Contrato de persistência para alertas de preço monitorados (DIP)."""

    def list_all(self) -> list[dict[str, Any]]:
        ...

    def add(
        self,
        query: str,
        product_title: str,
        target_price: float,
        current_price: float,
        store: str,
        url: str,
        image: str = "",
    ) -> dict[str, Any]:
        ...

    def update_price(
        self,
        item_id: int,
        new_price: float,
        store: str,
        url: str,
        product_title: str,
        image: str,
    ) -> None:
        ...

    def delete(self, item_id: int) -> bool:
        ...

