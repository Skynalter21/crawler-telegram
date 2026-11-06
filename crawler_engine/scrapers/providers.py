import asyncio
import json
import re
from urllib.parse import quote_plus
import httpx

from crawler_engine.domain.models import ProductOffer
from crawler_engine.scrapers.base import BaseScraperProvider
from crawler_engine.utils.text_normalizer import (
    decode_redirect_url,
    extract_card_image,
    infer_store_from_url,
    normalize_store_name,
    parse_brl_price,
)


class BingShoppingScraper(BaseScraperProvider):
    """Provedor de busca agregada no Bing Shopping Brasil."""

    @property
    def source_name(self) -> str:
        return "bing_shopping"

    async def _scrape_impl(self, client: httpx.AsyncClient, query: str) -> list[ProductOffer]:
        url = f"https://www.bing.com/shop?q={quote_plus(query)}&cc=br&setlang=pt-br"
        soup = await self._fetch_html(client, url)
        if not soup:
            return []

        results: list[ProductOffer] = []

        # 1. Cards com link direto (br-gOffCard / br-offCard)
        for card in soup.select(".br-gOffCard, .br-offCard"):
            link_el = card.select_one("a.br-offLink, a[href]")
            span_title = card.select_one(".br-offTtl [title], [title]")
            title_el = card.select_one(".br-offTtl")
            price_el = card.select_one(".br-price, .pd-price")
            seller_el = card.select_one(".br-offSlrTxt, .br-sellersCite")

            if not (span_title or title_el) or not price_el:
                continue

            title = (
                span_title.get("title")
                if span_title and span_title.get("title")
                else title_el.get_text(" ", strip=True)
            )
            price_val = parse_brl_price(price_el.get_text(strip=True))
            if not title or price_val is None or price_val <= 0:
                continue

            raw_store = seller_el.get_text(strip=True) if seller_el else "Web Shopping"
            store = normalize_store_name(raw_store)
            href = decode_redirect_url(link_el.get("href", "")) if link_el else ""
            img = extract_card_image(card)

            results.append(
                ProductOffer(
                    title=str(title),
                    price=round(price_val, 2),
                    store=store,
                    url=href or url,
                    image=img,
                    source=self.source_name,
                )
            )

        # 2. Cards da grade principal do Bing Shopping (li.br-item)
        for card in soup.select("li.br-item"):
            span_title = card.select_one(".br-pdItemName [title], .br-pdItemName-noHover [title]")
            title_el = card.select_one(".br-pdItemName, .br-pdItemName-noHover")
            price_el = card.select_one(".pd-price")
            seller_el = card.select_one(".br-sellersCite, .br-seller")
            img_el = card.select_one(".br-pdMainImg img, div.rms_iac[data-alt], img")
            direct_a = card.select_one(
                "a.br-offLink[href], a.br-VoidLink[href], a[href^='http']:not(.br-compareSellers)"
            )

            if not (span_title or title_el) or not price_el:
                continue

            alt_title = (img_el.get("alt") or img_el.get("data-alt")) if img_el else None
            title = (
                span_title.get("title")
                if span_title and span_title.get("title")
                else (
                    alt_title
                    if alt_title and alt_title != "Imagem do Produto"
                    else title_el.get_text(" ", strip=True)
                )
            )
            price_val = parse_brl_price(price_el.get_text(strip=True))
            if not title or price_val is None or price_val <= 0:
                continue

            raw_store = seller_el.get_text(strip=True) if seller_el else "Web Shopping"
            store = normalize_store_name(raw_store)

            href = ""
            if direct_a and direct_a.get("href"):
                href = decode_redirect_url(str(direct_a["href"]))

            # Ignora links internos quebrados do próprio Bing Shopping (/shop/productpage)
            if not href or "bing.com/shop" in href or "bing.com/search" in href:
                continue

            img = extract_card_image(card)

            results.append(
                ProductOffer(
                    title=str(title),
                    price=round(price_val, 2),
                    store=store,
                    url=href,
                    image=img,
                    source=self.source_name,
                )
            )

        return results


class YahooSearchScraper(BaseScraperProvider):
    """Provedor de busca em Shopping e resultados orgânicos do Yahoo Search Brasil."""

    @property
    def source_name(self) -> str:
        return "search_engine"

    async def _scrape_impl(self, client: httpx.AsyncClient, query: str) -> list[ProductOffer]:
        search_q = f"{query} preço"
        url = f"https://br.search.yahoo.com/search?p={quote_plus(search_q)}"
        soup = await self._fetch_html(client, url)
        if not soup:
            return []

        results: list[ProductOffer] = []

        # 1. Cards de Shopping (li.plaItem)
        for card in soup.select("li.plaItem"):
            link_el = card.select_one("a[href]")
            title_el = card.select_one(".text span")
            price_el = card.select_one(".current-price")
            seller_el = card.select_one(".seller")
            img_el = card.select_one("img.s-img, img")

            if not title_el or not price_el:
                continue

            title = title_el.get_text(" ", strip=True)
            price_val = parse_brl_price(price_el.get_text(strip=True))
            if not title or price_val is None or price_val <= 0:
                continue

            href = decode_redirect_url(str(link_el.get("href", ""))) if link_el else ""
            raw_store = seller_el.get_text(strip=True) if seller_el else ""
            store = normalize_store_name(raw_store) if raw_store else (infer_store_from_url(href) or "Web")
            img = str(img_el.get("src") or "") if img_el else ""

            results.append(
                ProductOffer(
                    title=title,
                    price=round(price_val, 2),
                    store=store,
                    url=href or url,
                    image=img,
                    source=self.source_name,
                )
            )

        # 2. Resultados orgânicos da 1ª página com preço
        for div in soup.select("div.algo"):
            h3 = div.select_one("h3")
            link_el = div.select_one("a[href]")
            if not h3 or not link_el:
                continue

            full_text = div.get_text(" ", strip=True)
            price_val = parse_brl_price(full_text)
            if price_val is None or price_val <= 0:
                continue

            href = decode_redirect_url(str(link_el.get("href", "")))
            store = infer_store_from_url(href)
            if not store:
                continue

            raw_h3 = h3.get_text(" ", strip=True)
            title = re.sub(r"^.*?(?:›\s*[^\s]+)+\s*", "", raw_h3).strip()
            title = re.sub(
                r"\s*\|\s*(Mercado Livre|Shopee|Amazon|Magalu|KaBuM!|enjoei|OLX).*$",
                "",
                title,
                flags=re.I,
            )

            results.append(
                ProductOffer(
                    title=title,
                    price=round(price_val, 2),
                    store=store,
                    url=href,
                    image="",
                    source="organic_search",
                )
            )

        return results


class _SherlockCatalogScraper(BaseScraperProvider):
    """
    Classe base para comparadores baseados na plataforma Sherlock (Buscapé e Zoom).
    Evita duplicação de código (DRY) preservando polimorfismo (LSP).
    """

    def __init__(self, base_domain: str, default_store_label: str, source_id: str) -> None:
        super().__init__()
        self.base_domain = base_domain
        self.default_store_label = default_store_label
        self._source_id = source_id

    @property
    def source_name(self) -> str:
        return self._source_id

    async def _scrape_impl(self, client: httpx.AsyncClient, query: str) -> list[ProductOffer]:
        url = f"{self.base_domain}/search?q={quote_plus(query)}"
        soup = await self._fetch_html(client, url)
        if not soup:
            return []

        results: list[ProductOffer] = []
        for card in soup.select('[data-testid="product-card"]'):
            name_el = card.select_one('[data-testid="product-card::name"]')
            price_el = card.select_one('[data-testid="product-card::price"]')
            link_el = card.select_one('[data-testid="product-card::card"]')
            merchant_el = card.select_one('[aria-label="Menor preço"]')
            img_el = card.select_one('[data-testid="product-card::image"] img')

            if not name_el or not price_el:
                continue

            lbl = str(card.get("aria-labelledby", ""))
            m_pid = re.search(r"product-card-(\d+)", lbl)
            product_id = m_pid.group(1) if m_pid else None

            title = name_el.get_text(strip=True)
            price_val = parse_brl_price(price_el.get_text(strip=True))
            if price_val is None or price_val <= 0:
                continue

            store_raw = merchant_el.get_text(strip=True) if merchant_el else self.default_store_label
            store_clean = re.sub(r"^Via\s+", "", store_raw, flags=re.IGNORECASE).strip() or self.default_store_label
            store = normalize_store_name(store_clean)

            href = str(link_el.get("href", "")) if link_el else ""
            full_url = f"{self.base_domain}{href}" if href.startswith("/") else href
            image = str(img_el.get("src") or img_el.get("data-src") or "") if img_el else ""

            results.append(
                ProductOffer(
                    title=title,
                    price=round(price_val, 2),
                    store=store,
                    url=full_url,
                    image=image,
                    source=self.source_name,
                    product_id=product_id,
                )
            )

        return results


class BuscapeScraper(_SherlockCatalogScraper):
    """Provedor de ofertas comparadas no Buscapé."""

    def __init__(self) -> None:
        super().__init__(
            base_domain="https://www.buscape.com.br",
            default_store_label="Buscapé",
            source_id="buscape",
        )


class ZoomScraper(_SherlockCatalogScraper):
    """Provedor de ofertas comparadas no Zoom."""

    def __init__(self) -> None:
        super().__init__(
            base_domain="https://www.zoom.com.br",
            default_store_label="Zoom",
            source_id="zoom",
        )


class KabumScraper(BaseScraperProvider):
    """Provedor de busca direta no catálogo da KaBuM! via estado Next.js."""

    @property
    def source_name(self) -> str:
        return "kabum"

    async def _scrape_impl(self, client: httpx.AsyncClient, query: str) -> list[ProductOffer]:
        slug = re.sub(r"\s+", "-", query.strip().lower())
        url = f"https://www.kabum.com.br/busca/{quote_plus(slug)}"
        soup = await self._fetch_html(client, url)
        if not soup:
            return []

        next_data = soup.find("script", id="__NEXT_DATA__")
        if not next_data or not next_data.string:
            return []

        try:
            payload = json.loads(next_data.string)
            raw_data = payload.get("props", {}).get("pageProps", {}).get("data", {})
            if isinstance(raw_data, str):
                raw_data = json.loads(raw_data)
            catalog = raw_data.get("catalogServer", {}).get("data", [])
        except (json.JSONDecodeError, AttributeError, TypeError):
            return []

        results: list[ProductOffer] = []
        for item in catalog[:35]:
            if not item.get("available", True):
                continue
            price_val = item.get("priceWithDiscount") or item.get("price")
            if not price_val or float(price_val) <= 0:
                continue

            code = item.get("code")
            friendly = item.get("friendlyName", "")
            product_url = (
                f"https://www.kabum.com.br/produto/{code}/{friendly}"
                if code
                else "https://www.kabum.com.br"
            )

            results.append(
                ProductOffer(
                    title=item.get("name", "Produto KaBuM!"),
                    price=round(float(price_val), 2),
                    store="KaBuM!",
                    url=product_url,
                    image=item.get("image") or "",
                    source=self.source_name,
                )
            )

        return results


class PelandoScraper(BaseScraperProvider):
    """Provedor de promoções ativas da comunidade Pelando."""

    @property
    def source_name(self) -> str:
        return "pelando"

    async def _scrape_impl(self, client: httpx.AsyncClient, query: str) -> list[ProductOffer]:
        url = f"https://www.pelando.com.br/busca/{quote_plus(query)}"
        soup = await self._fetch_html(client, url)
        if not soup:
            return []

        results: list[ProductOffer] = []
        for card in soup.select('div[class*="_deal-card_"]'):
            if card.select_one('[data-inactive="true"]'):
                continue

            a_el = card.select_one("h3 a[href]")
            price_el = card.select_one('[class*="_deal-card-stamp_"]')
            store_el = card.select_one('[class*="_default-deal-card-store_"] strong')
            img_el = card.select_one('img[class*="_deal-card-image_"], img')

            if not a_el or not price_el:
                continue

            title = a_el.get_text(" ", strip=True)
            price_val = parse_brl_price(price_el.get_text(" ", strip=True))
            if not title or price_val is None or price_val <= 0:
                continue

            raw_store = store_el.get_text(strip=True) if store_el else "Pelando"
            store = normalize_store_name(raw_store)
            href = str(a_el.get("href", ""))
            full_url = f"https://www.pelando.com.br{href}" if href.startswith("/") else href
            img = str(img_el.get("src") or "") if img_el else ""

            results.append(
                ProductOffer(
                    title=title,
                    price=round(price_val, 2),
                    store=f"{store} (Promo Pelando)" if store != "Pelando" else "Pelando",
                    url=full_url,
                    image=img,
                    source=self.source_name,
                )
            )

        return results


class KalungaScraper(BaseScraperProvider):
    """Provedor de busca direta no catálogo da Kalunga."""

    @property
    def source_name(self) -> str:
        return "kalunga"

    async def _scrape_impl(self, client: httpx.AsyncClient, query: str) -> list[ProductOffer]:
        url = f"https://www.kalunga.com.br/busca/1?q={quote_plus(query)}"
        soup = await self._fetch_html(client, url)
        if not soup:
            return []

        results: list[ProductOffer] = []
        for card in soup.select("div.blocoproduto")[:25]:
            link_el = card.select_one("a.blocoproduto__link[href]")
            price_el = card.select_one(".blocoproduto__price")
            source_el = card.select_one("picture source")
            img_el = card.select_one("img.blocoproduto__image, img")

            if not link_el or not price_el:
                continue

            title = str(link_el.get("title") or link_el.get_text(" ", strip=True))
            price_val = parse_brl_price(price_el.get_text(" ", strip=True))
            if not title or price_val is None or price_val <= 0:
                continue

            href = str(link_el.get("href", ""))
            full_url = f"https://www.kalunga.com.br{href}" if href.startswith("/") else href

            img = ""
            if source_el and (source_el.get("srcset") or source_el.get("data-srcset")):
                raw_srcset = str(source_el.get("srcset") or source_el.get("data-srcset") or "")
                img = raw_srcset.split()[0] if raw_srcset else ""
            elif img_el:
                img = str(img_el.get("data-src") or img_el.get("src") or "")

            results.append(
                ProductOffer(
                    title=title,
                    price=round(price_val, 2),
                    store="Kalunga",
                    url=full_url,
                    image=img,
                    source=self.source_name,
                )
            )

        return results


class HavanScraper(BaseScraperProvider):
    """Provedor de busca direta no catálogo da Havan."""

    @property
    def source_name(self) -> str:
        return "havan"

    async def _scrape_impl(self, client: httpx.AsyncClient, query: str) -> list[ProductOffer]:
        url = f"https://www.havan.com.br/catalogsearch/result/?q={quote_plus(query)}"
        soup = await self._fetch_html(client, url)
        if not soup:
            return []

        results: list[ProductOffer] = []
        for card in soup.select("li.product-item")[:20]:
            link_el = card.select_one("a.product-item-link[href]")
            price_el = card.select_one('[data-price-type="finalPrice"], .price-box .price')
            img_el = card.select_one("img.img-default, img.product-image-photo, img")

            if not link_el or not price_el:
                continue

            title = link_el.get_text(" ", strip=True)
            price_val = parse_brl_price(price_el.get_text(" ", strip=True))
            if not title or price_val is None or price_val <= 0:
                continue

            href = str(link_el.get("href", ""))
            img = str(img_el.get("src") or img_el.get("data-src") or "") if img_el else ""

            results.append(
                ProductOffer(
                    title=title,
                    price=round(price_val, 2),
                    store="Havan",
                    url=href,
                    image=img,
                    source=self.source_name,
                )
            )

        return results


class BerlandaScraper(BaseScraperProvider):
    """Provedor de busca direta no catálogo das Lojas Berlanda."""

    @property
    def source_name(self) -> str:
        return "berlanda"

    async def _scrape_impl(self, client: httpx.AsyncClient, query: str) -> list[ProductOffer]:
        url = f"https://www.berlanda.com.br/pesquisa?t={quote_plus(query)}"
        soup = await self._fetch_html(client, url)
        if not soup:
            return []

        results: list[ProductOffer] = []
        for art in soup.select("article.wd-product-line")[:20]:
            title = str(art.get("data-name") or "")
            link_el = art.select_one("a[href]")
            img_el = art.select_one("img.main-image, img")

            text_content = art.get_text(" ", strip=True)
            m_por = re.search(r"Por\s+R\$\s*([\d\.]+,\d{2})", text_content, re.I)
            price_val = (
                parse_brl_price(f"R$ {m_por.group(1)}")
                if m_por
                else parse_brl_price(text_content)
            )

            if not title or price_val is None or price_val <= 0:
                continue

            href = str(link_el.get("href", "")) if link_el else ""
            full_url = f"https://www.berlanda.com.br{href}" if href.startswith("/") else href
            img = str(img_el.get("src") or img_el.get("data-src") or "") if img_el else ""

            results.append(
                ProductOffer(
                    title=title,
                    price=round(price_val, 2),
                    store="Lojas Berlanda",
                    url=full_url,
                    image=img,
                    source=self.source_name,
                )
            )

        return results


class EnjoeiScraper(BaseScraperProvider):
    """
    Provedor de busca direta no catálogo do Enjoei via API GraphQL oficial de busca.
    """

    _GRAPHQL_ENDPOINT = "https://enjusearch.enjoei.com.br/graphql-search"
    _SEARCH_QUERY = """
    query searchProducts($term: String!, $first: Int) {
      search(products: { term: $term }) {
        products(first: $first) {
          edges {
            node {
              id
              used
              path
              photo {
                image_public_id
              }
              title {
                name
              }
              price {
                original
                current
              }
            }
          }
        }
      }
    }
    """

    @property
    def source_name(self) -> str:
        return "enjoei"

    async def _scrape_impl(self, client: httpx.AsyncClient, query: str) -> list[ProductOffer]:
        resp = await client.post(
            self._GRAPHQL_ENDPOINT,
            json={
                "operationName": "searchProducts",
                "query": self._SEARCH_QUERY,
                "variables": {"term": query, "first": 25},
            },
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
                ),
                "Content-Type": "application/json",
            },
            timeout=self.timeout,
        )
        if resp.status_code != 200:
            return []

        payload = resp.json()
        edges = (
            payload.get("data", {})
            .get("search", {})
            .get("products", {})
            .get("edges")
            or []
        )

        results: list[ProductOffer] = []
        for edge in edges:
            node = edge.get("node") or {}
            title_obj = node.get("title") or {}
            price_obj = node.get("price") or {}
            photo_obj = node.get("photo") or {}

            title = str(title_obj.get("name") or "").strip()
            price_val = price_obj.get("current") or price_obj.get("original")
            if not title or not price_val or float(price_val) <= 0:
                continue

            is_used = bool(node.get("used"))
            if is_used and "usado" not in title.lower() and "seminovo" not in title.lower():
                title = f"{title} (Seminovo)"

            path = node.get("path") or node.get("id") or ""
            product_url = f"https://www.enjoei.com.br/p/{path}" if path else "https://www.enjoei.com.br"

            pub_id = photo_obj.get("image_public_id")
            image_url = (
                f"https://photos.enjoei.com.br/public/300x300/{pub_id}.jpg"
                if pub_id
                else ""
            )

            results.append(
                ProductOffer(
                    title=title,
                    price=round(float(price_val), 2),
                    store="Enjoei",
                    url=product_url,
                    image=image_url,
                    source=self.source_name,
                    is_used=is_used,
                )
            )

        return results


class OlxScraper(BaseScraperProvider):
    """
    Provedor de busca direta nos anúncios da OLX Brasil (novos, seminovos e usados).
    """

    @property
    def source_name(self) -> str:
        return "olx"

    async def _scrape_impl(self, client: httpx.AsyncClient, query: str) -> list[ProductOffer]:
        url = f"https://www.olx.com.br/brasil?q={quote_plus(query)}"
        soup = await self._fetch_html(client, url)
        if not soup:
            return []

        results: list[ProductOffer] = []
        for card in soup.select("section.olx-adcard")[:28]:
            title_el = card.select_one("h2")
            price_el = card.select_one("h3")
            link_el = card.select_one('a[data-testid="adcard-link"], a[href]')
            img_el = card.select_one("picture img, img")

            if not title_el or not price_el:
                continue

            title = title_el.get_text(" ", strip=True)
            price_val = parse_brl_price(price_el.get_text(" ", strip=True))
            if not title or price_val is None or price_val <= 0:
                continue

            href = str(link_el.get("href", "")) if link_el else url
            img = ""
            if img_el:
                img = str(img_el.get("src") or img_el.get("data-src") or "")
                if not img and img_el.get("srcset"):
                    img = str(img_el.get("srcset")).split()[0]

            low_title = title.lower()
            is_explicitly_new = bool(
                re.search(r"\b(lacrad[oa]|na\s+caixa\s+lacrad[oa])\b", low_title)
                or (
                    re.search(r"\b(novo|nova)\b", low_title)
                    and not re.search(
                        r"\b(semi\s*nov[oa]|seminov[oa]|usad[oa]|estado\s+de\s+nov[oa]|como\s+nov[oa]|cordas?\s+novas?|bateria\s+nova|pneus?\s+novos?|pe[cç]as?\s+novas?|meses\s+de\s+uso)\b",
                        low_title,
                    )
                )
            )

            results.append(
                ProductOffer(
                    title=title,
                    price=round(price_val, 2),
                    store="OLX",
                    url=href,
                    image=img,
                    source=self.source_name,
                    is_used=not is_explicitly_new,
                )
            )

        return results


class FacebookMarketplaceScraper(BaseScraperProvider):
    """
    Provedor de anúncios públicos do Facebook Marketplace Brasil com extração
    de fotos reais via metadados OpenGraph (og:image).
    """

    @property
    def source_name(self) -> str:
        return "facebook_marketplace"

    async def _scrape_impl(self, _client: httpx.AsyncClient, query: str) -> list[ProductOffer]:
        search_q = f"site:facebook.com/marketplace/item {query} R$"
        url = f"https://br.search.yahoo.com/search?p={quote_plus(search_q)}"
        async with httpx.AsyncClient() as fb_client:
            soup = await self._fetch_html(fb_client, url)
            if not soup:
                return []

            draft_items: list[dict[str, str | float]] = []
            for div in soup.select("div.algo"):
                h3 = div.select_one("h3")
                link_el = div.select_one("a[href]")
                if not h3 or not link_el:
                    continue

                full_text = div.get_text(" ", strip=True)
                price_val = parse_brl_price(full_text)
                if price_val is None or price_val <= 0:
                    continue

                href = decode_redirect_url(str(link_el.get("href", "")))
                if "facebook.com/marketplace/item" not in href:
                    continue

                raw_h3 = h3.get_text(" ", strip=True)
                no_bc = re.sub(
                    r"^.*?marketplace\s*›\s*item\s*", "", raw_h3, flags=re.I
                ).strip()
                parts = [
                    p.strip() for p in re.split(r"\s+[-—|]\s+", no_bc) if p.strip()
                ]
                clean_title = parts[0] if parts else no_bc
                if not clean_title:
                    continue

                if (
                    "cases, covers" in raw_h3.lower()
                    and price_val < 200
                    and "capa" not in clean_title.lower()
                ):
                    clean_title = f"{clean_title} (Capinha)"

                draft_items.append(
                    {
                        "title": clean_title,
                        "price": round(price_val, 2),
                        "url": href,
                        "image": "",
                    }
                )

            async def _enrich_og_image(item: dict[str, str | float]) -> None:
                try:
                    resp = await fb_client.get(
                        str(item["url"]),
                        headers={
                            "User-Agent": (
                                "facebookexternalhit/1.1 "
                                "(+http://www.facebook.com/externalhit_uatext.php)"
                            ),
                            "Accept-Language": "pt-BR,pt;q=0.9",
                        },
                        follow_redirects=True,
                        timeout=3.2,
                    )
                    if resp.status_code == 200:
                        m_img = re.search(
                            r'property="og:image"\s+content="([^"]+)"', resp.text
                        )
                        if m_img:
                            item["image"] = m_img.group(1).replace("&amp;", "&")
                except Exception:
                    pass

            if draft_items:
                await asyncio.gather(*(_enrich_og_image(it) for it in draft_items[:8]))

        return [
            ProductOffer(
                title=str(it["title"]),
                price=float(it["price"]),
                store="Facebook Marketplace",
                url=str(it["url"]),
                image=str(it["image"]),
                source=self.source_name,
                is_used=not bool(
                    re.search(r"\b(lacrad[oa])\b", str(it["title"]).lower())
                    or (
                        re.search(r"\b(novo|nova)\b", str(it["title"]).lower())
                        and not re.search(
                            r"\b(semi\s*nov[oa]|seminov[oa]|usad[oa]|estado\s+de\s+nov[oa]|como\s+nov[oa]|cordas?\s+novas?|bateria\s+nova|meses\s+de\s+uso)\b",
                            str(it["title"]).lower(),
                        )
                    )
                ),
            )
            for it in draft_items
        ]


class AmazonBrasilScraper(BaseScraperProvider):
    """
    Provedor de busca direta no catálogo da Amazon Brasil (amazon.com.br).
    """

    _USER_AGENTS = [
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:128.0) "
            "Gecko/20100101 Firefox/128.0"
        ),
        (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15"
        ),
        (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1"
        ),
    ]

    @property
    def source_name(self) -> str:
        return "amazon_br"

    async def _scrape_impl(self, _client: httpx.AsyncClient, query: str) -> list[ProductOffer]:
        from bs4 import BeautifulSoup

        html_text = ""
        async with httpx.AsyncClient(follow_redirects=True, timeout=self.timeout) as amz_client:
            for ua in self._USER_AGENTS:
                try:
                    resp = await amz_client.get(
                        "https://www.amazon.com.br/s",
                        params={"k": query},
                        headers={
                            "User-Agent": ua,
                            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                            "Accept-Language": "pt-BR,pt;q=0.9",
                            "Accept-Encoding": "gzip, deflate",
                        },
                    )
                    if resp.status_code == 200 and len(resp.text) > 15000:
                        html_text = resp.text
                        break
                except httpx.HTTPError:
                    continue

        if not html_text:
            return []

        soup = BeautifulSoup(html_text, "html.parser")
        results: list[ProductOffer] = []

        for card in soup.select('[data-component-type="s-search-result"]')[:35]:
            asin = str(card.get("data-asin") or "").strip()
            h2 = card.select_one("h2")
            price_el = card.select_one(".a-price .a-offscreen")
            img_el = card.select_one("img.s-image")

            if not h2 or not price_el:
                continue

            title = h2.get_text(" ", strip=True)
            price_val = parse_brl_price(price_el.get_text(strip=True))
            if not title or price_val is None or price_val <= 0:
                continue

            link_el = card.select_one('h2 a[href], a.a-link-normal[href*="/dp/"]')
            if asin:
                product_url = f"https://www.amazon.com.br/dp/{asin}"
            elif link_el and link_el.get("href"):
                href = str(link_el.get("href"))
                product_url = f"https://www.amazon.com.br{href}" if href.startswith("/") else href
            else:
                product_url = f"https://www.amazon.com.br/s?k={quote_plus(query)}"

            img = str(img_el.get("src") or "") if img_el else ""

            results.append(
                ProductOffer(
                    title=title,
                    price=round(price_val, 2),
                    store="Amazon",
                    url=product_url,
                    image=img,
                    source=self.source_name,
                    is_used=False,
                )
            )

        return results


def get_default_scraper_providers() -> list[BaseScraperProvider]:
    """
    Factory de provedores ativos (Open/Closed Principle).
    Para adicionar uma nova loja no futuro, basta criar uma subclasse de BaseScraperProvider
    e registrá-la nesta lista, sem alterar o orquestrador de buscas.
    """
    return [
        AmazonBrasilScraper(),
        YahooSearchScraper(),
        BingShoppingScraper(),
        BuscapeScraper(),
        ZoomScraper(),
        KabumScraper(),
        PelandoScraper(),
        KalungaScraper(),
        HavanScraper(),
        BerlandaScraper(),
        EnjoeiScraper(),
        OlxScraper(),
        FacebookMarketplaceScraper(),
    ]

