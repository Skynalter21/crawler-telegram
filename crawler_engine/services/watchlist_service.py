import asyncio
from typing import Any

from crawler_engine.domain.interfaces import WatchlistRepository
from crawler_engine.domain.models import SearchCriteria, WatchlistCreateRequest
from crawler_engine.services.search_orchestrator import PriceSearchOrchestrator


class WatchlistService:
    """
    Serviço de aplicação responsável pelo gerenciamento e atualização ao vivo
    dos alertas de preço (Watchlist) (SRP & DIP).
    """

    def __init__(
        self,
        repository: WatchlistRepository,
        search_orchestrator: PriceSearchOrchestrator,
    ) -> None:
        self.repository = repository
        self.search_orchestrator = search_orchestrator

    def list_alerts(self) -> list[dict[str, Any]]:
        return self.repository.list_all()

    def create_alert(self, request: WatchlistCreateRequest) -> dict[str, Any]:
        item = self.repository.add(
            query=request.query,
            product_title=request.product_title,
            target_price=request.target_price,
            current_price=request.current_price,
            store=request.store,
            url=request.url,
            image=request.image,
        )
        return {"item": item, "items": self.repository.list_all()}

    def remove_alert(self, item_id: int) -> list[dict[str, Any]]:
        self.repository.delete(item_id)
        return self.repository.list_all()

    async def refresh_all_alerts(self) -> list[dict[str, Any]]:
        items = self.repository.list_all()
        if not items:
            return []

        async def _refresh_single(w_item: dict[str, Any]) -> None:
            criteria = SearchCriteria(
                query=w_item["query"],
                include_used=False,
                strict_model=True,
                force_refresh=True,
            )
            result = await self.search_orchestrator.execute_search(criteria)
            lowest = result.get("lowest")
            if lowest:
                self.repository.update_price(
                    item_id=w_item["id"],
                    new_price=lowest["price"],
                    store=lowest["store"],
                    url=lowest["url"],
                    product_title=lowest["title"],
                    image=lowest.get("image") or w_item.get("image", ""),
                )

        await asyncio.gather(*(_refresh_single(item) for item in items))
        return self.repository.list_all()

