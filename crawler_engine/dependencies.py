from functools import lru_cache

from crawler_engine.infrastructure.cache_memory import InMemorySearchCache
from crawler_engine.infrastructure.history_gateway import ZoomSherlockHistoryGateway
from crawler_engine.infrastructure.watchlist_sqlite import SQLiteWatchlistRepository
from crawler_engine.scrapers.providers import get_default_scraper_providers
from crawler_engine.services.deduplicator import MedianPriceOutlierFilter, OfferDeduplicator
from crawler_engine.services.market_stats import MarketPriceStatsCalculator
from crawler_engine.services.relevance_matcher import RelevanceProductMatcher
from crawler_engine.services.search_orchestrator import PriceSearchOrchestrator
from crawler_engine.services.watchlist_service import WatchlistService


@lru_cache(maxsize=1)
def get_search_cache() -> InMemorySearchCache:
    return InMemorySearchCache(ttl_seconds=600.0)


@lru_cache(maxsize=1)
def get_watchlist_repository() -> SQLiteWatchlistRepository:
    return SQLiteWatchlistRepository()


@lru_cache(maxsize=1)
def get_search_orchestrator() -> PriceSearchOrchestrator:
    """
    Composition Root / Container de Injeção de Dependências (DIP) para o motor de busca.
    """
    return PriceSearchOrchestrator(
        providers=get_default_scraper_providers(),
        matcher=RelevanceProductMatcher(),
        deduplicator=OfferDeduplicator(),
        outlier_filter=MedianPriceOutlierFilter(min_ratio_of_median=0.28, min_sample_size=4),
        history_gateway=ZoomSherlockHistoryGateway(),
        cache=get_search_cache(),
        stats_calculator=MarketPriceStatsCalculator(),
    )


@lru_cache(maxsize=1)
def get_watchlist_service() -> WatchlistService:
    """
    Composition Root / Container de Injeção de Dependências (DIP) para o serviço de Watchlist.
    """
    return WatchlistService(
        repository=get_watchlist_repository(),
        search_orchestrator=get_search_orchestrator(),
    )

