import statistics
from crawler_engine.domain.models import ProductOffer
from crawler_engine.utils.text_normalizer import tokenize


class OfferDeduplicator:
    """
    Serviço focado na remoção de ofertas duplicadas entre múltiplos motores de busca (SRP).
    Prioriza a versão que possui link direto para a loja, imagem válida e product_id de histórico.
    """

    def deduplicate(self, offers: list[ProductOffer]) -> list[ProductOffer]:
        seen: dict[tuple[str, float, str], ProductOffer] = {}
        for offer in offers:
            norm_title_prefix = " ".join(tokenize(offer.title)[:6])
            key = (offer.store.lower(), offer.price, norm_title_prefix)

            if key not in seen:
                seen[key] = offer
            else:
                existing = seen[key]
                pid = existing.product_id or offer.product_id
                existing_is_direct = "bing.com/shop" not in existing.url
                new_is_direct = "bing.com/shop" not in offer.url

                if (new_is_direct and not existing_is_direct) or (not existing.image and offer.image):
                    seen[key] = offer.model_copy(
                        update={
                            "product_id": pid,
                            "image": offer.image or existing.image,
                        }
                    )
                else:
                    updates: dict[str, str | None] = {}
                    if pid and not existing.product_id:
                        updates["product_id"] = pid
                    if not existing.image and offer.image:
                        updates["image"] = offer.image
                    if updates:
                        seen[key] = existing.model_copy(update=updates)

        return list(seen.values())


class MedianPriceOutlierFilter:
    """
    Serviço estatístico que remove anúncios com preços absurdamente abaixo da mediana
    (ex: peças avulsas ou acessórios não filtrados por texto) (SRP).
    """

    def __init__(self, min_ratio_of_median: float = 0.28, min_sample_size: int = 4) -> None:
        self.min_ratio_of_median = min_ratio_of_median
        self.min_sample_size = min_sample_size

    def filter_outliers(self, offers: list[ProductOffer]) -> list[ProductOffer]:
        if len(offers) < self.min_sample_size:
            return offers

        median_price = statistics.median(o.price for o in offers)
        min_reasonable_price = median_price * self.min_ratio_of_median
        filtered = [o for o in offers if o.price >= min_reasonable_price]
        return filtered if filtered else offers

