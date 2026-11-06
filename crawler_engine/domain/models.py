from dataclasses import dataclass
from typing import Any
from pydantic import BaseModel, Field


@dataclass(frozen=True)
class SearchCriteria:
    """Critérios de busca e filtragem definidos pelo usuário."""
    query: str
    include_used: bool = True
    strict_model: bool = True
    force_refresh: bool = False


@dataclass(frozen=True)
class MatchEvaluation:
    """Resultado da avaliação de compatibilidade de um título com a busca."""
    is_valid: bool
    relevance_score: int
    is_exact_model: bool
    is_used_item: bool = False


class ProductOffer(BaseModel):
    """Representa uma oferta de produto encontrada por um provedor de scraping."""
    title: str
    price: float
    store: str
    url: str
    image: str = ""
    source: str
    product_id: str | None = None
    relevance: int = 100
    exact_model: bool = True
    is_used: bool = False

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()


class PricePoint(BaseModel):
    """Ponto diário da série histórica de preços."""
    date: str
    price: float


class PriceHistoryData(BaseModel):
    """Histórico consolidado de preços de um produto."""
    product_id: str
    title: str
    points: list[PricePoint]


class WatchlistCreateRequest(BaseModel):
    """Payload de entrada para criação de alerta de preço."""
    query: str = Field(..., min_length=1)
    product_title: str = Field(..., min_length=1)
    target_price: float = Field(..., gt=0)
    current_price: float = Field(..., gt=0)
    store: str
    url: str
    image: str = ""
