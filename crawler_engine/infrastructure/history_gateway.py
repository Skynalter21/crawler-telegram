import httpx
from crawler_engine.domain.models import PricePoint
from crawler_engine.scrapers.base import DEFAULT_HEADERS


class ZoomSherlockHistoryGateway:
    """
    Gateway de infraestrutura para consulta de série histórica diária real (até 365 dias)
    na API RestQL Sherlock (Zoom/Buscapé). Cumpre PriceHistoryGateway (DIP & ISP).
    """

    def __init__(self, timeout: float = 8.0) -> None:
        self.timeout = timeout

    async def fetch_history(
        self, client: httpx.AsyncClient, product_id: str
    ) -> list[PricePoint]:
        url = (
            "https://api-v1.zoom.com.br/restql/run-query/sherlock/product_price_history/1"
            f"?tenant=DEFAULT&product_id={product_id}&period=months&amount=12"
        )
        try:
            resp = await client.get(url, headers=DEFAULT_HEADERS, timeout=self.timeout)
            if resp.status_code != 200:
                return []
            payload = resp.json()
            raw_points = payload.get("product_price_history", {}).get("result") or []
        except Exception:
            return []

        by_date: dict[str, float] = {}
        for pt in raw_points:
            dt = pt.get("date")
            pr = pt.get("price")
            if dt and pr and float(pr) > 0:
                val = round(float(pr), 2)
                if dt not in by_date or val < by_date[dt]:
                    by_date[dt] = val

        return [PricePoint(date=d, price=by_date[d]) for d in sorted(by_date.keys())]

