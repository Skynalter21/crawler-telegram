import base64
from difflib import SequenceMatcher
import re
import unicodedata
from typing import Any
from urllib.parse import unquote, urlparse

COMMON_ECOMMERCE_VOCABULARY = (
    "airfryer", "fritadeira", "iphone", "samsung", "xiaomi", "motorola",
    "playstation", "nintendo", "switch", "xbox", "notebook", "macbook",
    "monitor", "teclado", "mouse", "headset", "fone", "bluetooth",
    "geladeira", "refrigerador", "microondas", "liquidificador", "cafeteira",
    "ventilador", "climatizador", "ar", "condicionado", "televisao", "smartv",
    "lavadora", "maquina", "aspirador", "robo", "panela", "pressao",
    "churrasqueira", "cerveja", "heineken", "stella", "budweiser", "Brahma",
    "chopp", "whisky", "vinho", "energetico", "monster", "redbull",
    "whey", "protein", "creatina", "yopro", "chocolate", "cafe", "capsula",
    "placa", "video", "processador", "ryzen", "intel", "memoria", "ssd",
    "gabinete", "fonte", "cadeira", "gamer", "mesa", "escritorio",
    "perfume", "hidratante", "shampoo", "tenis", "nike", "adidas", "puma",
    "camisa", "mochila", "relógio", "smartwatch", "garrafa", "termica",
    "stanley", "luminaria", "cozinha", "armario", "colchao", "travesseiro",
    "furadeira", "parafusadeira", "bosch", "makita", "wap", "lavadora",
    "philips", "walita", "mondial", "britania", "electrolux", "consul",
    "brastemp", "lg", "tcl", "philco", "aoc", "acer", "asus", "lenovo", "dell",
    "logitech", "razer", "hyperx", "corsair", "jbl", "caixa", "som",
)

DIRECT_TYPO_MAP = {
    "ayirfrier": "air fryer",
    "airfrier": "air fryer",
    "ayrfryer": "air fryer",
    "airfrayer": "air fryer",
    "ayrfrayer": "air fryer",
    "arfrayer": "air fryer",
    "arfryer": "air fryer",
    "airfry": "air fryer",
    "airfryer": "air fryer",
    "ifone": "iphone",
    "ipone": "iphone",
    "iphon": "iphone",
    "sansung": "samsung",
    "sansumg": "samsung",
    "samsumg": "samsung",
    "xiomi": "xiaomi",
    "xiami": "xiaomi",
    "xiaome": "xiaomi",
    "xaomi": "xiaomi",
    "pleisteixon": "playstation",
    "pleystation": "playstation",
    "playstatiom": "playstation",
    "notebuk": "notebook",
    "notbook": "notebook",
    "notbuk": "notebook",
    "heinekem": "heineken",
    "heinek": "heineken",
    "cerveija": "cerveja",
}


def phonetic_skeleton(word: str) -> str:
    """
    Gera uma representação fonética simplificada para aproximar palavras digitadas
    com erros ortográficos em português/inglês (ex: 'ayirfrier' -> 'airfrier').
    """
    w = normalize_text(word)
    w = w.replace("ph", "f").replace("y", "i").replace("w", "v").replace("k", "c")
    w = w.replace("ch", "x").replace("sh", "x").replace("ç", "s").replace("z", "s")
    w = re.sub(r"([a-z])\1+", r"\1", w)  # remove letras duplicadas (ss -> s, rr -> r, ii -> i)
    w = re.sub(r"ai+", "ai", w)
    w = re.sub(r"ei+", "ei", w)
    return w


def fuzzy_similarity(word1: str, word2: str) -> float:
    """Calcula a similaridade máxima entre a forma literal e a forma fonética de duas palavras."""
    w1, w2 = normalize_text(word1), normalize_text(word2)
    if w1 == w2:
        return 1.0
    raw_ratio = SequenceMatcher(None, w1, w2).ratio()
    p1, p2 = phonetic_skeleton(w1), phonetic_skeleton(w2)
    if p1 == p2 and len(p1) >= 3:
        return 0.95
    phonetic_ratio = SequenceMatcher(None, p1, p2).ratio()
    return max(raw_ratio, phonetic_ratio * 0.96)


def correct_query_typos(query: str) -> str:
    """
    Corrige erros de digitação comuns em buscas de produtos (ex: 'ayirfrier' -> 'air fryer',
    'ifone 15' -> 'iphone 15', 'geladera' -> 'geladeira') preservando modelos numéricos.
    """
    norm_q = normalize_text(query).strip()
    if not norm_q:
        return query.strip()

    # Normaliza variações compostas de air fryer antes de tokenizar
    norm_q = re.sub(
        r"\b(?:a[yi]+r|ar)\s*(?:fr[iy]+er|fra[iy]+er|frier|fry)\b",
        "air fryer",
        norm_q,
    )

    words = norm_q.split()
    corrected_words: list[str] = []

    for w in words:
        clean_w = re.sub(r"\W+", "", w)
        if not clean_w or any(ch.isdigit() for ch in clean_w) or len(clean_w) <= 3:
            corrected_words.append(w)
            continue

        if clean_w in DIRECT_TYPO_MAP:
            corrected_words.append(DIRECT_TYPO_MAP[clean_w])
            continue

        if clean_w in COMMON_ECOMMERCE_VOCABULARY:
            corrected_words.append(clean_w)
            continue

        # Busca a palavra mais próxima no vocabulário
        best_match = clean_w
        best_score = 0.0
        for candidate in COMMON_ECOMMERCE_VOCABULARY:
            score = fuzzy_similarity(clean_w, candidate)
            if score > best_score:
                best_score = score
                best_match = candidate

        if best_score >= 0.78:
            corrected_words.append("air fryer" if best_match == "airfryer" else best_match)
        else:
            corrected_words.append(w)

    return " ".join(corrected_words)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
}

DOMAIN_STORE_MAP = {
    "mercadolivre.com.br": "Mercado Livre",
    "shopee.com.br": "Shopee",
    "amazon.com.br": "Amazon",
    "kabum.com.br": "KaBuM!",
    "magazineluiza.com.br": "Magazine Luiza",
    "magalu.com": "Magazine Luiza",
    "casasbahia.com.br": "Casas Bahia",
    "americanas.com.br": "Americanas",
    "aliexpress.com": "AliExpress",
    "pichau.com.br": "Pichau",
    "terabyteshop.com.br": "Terabyte",
    "fastshop.com.br": "Fast Shop",
    "carrefour.com.br": "Carrefour",
    "netshoes.com.br": "Netshoes",
    "nike.com.br": "Nike",
    "kalunga.com.br": "Kalunga",
    "havan.com.br": "Havan",
    "berlanda.com.br": "Lojas Berlanda",
    "zoom.com.br": "Zoom",
    "buscape.com.br": "Buscapé",
    "enjoei.com.br": "Enjoei",
    "olx.com.br": "OLX",
    "facebook.com": "Facebook Marketplace",
}


def normalize_text(text: str) -> str:
    """Remove acentos e converte para minúsculas."""
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def tokenize(text: str) -> list[str]:
    """
    Normaliza e extrai tokens alfanuméricos, tratando sinônimos e unidades comuns:
    - '43"' / '43 pol' -> '43 polegada'
    - '4,5L' / '4.5 litros' -> '4_5l'
    - '128gb' -> '128 gb'
    - 'air fryer' / 'ayirfrier' / 'airfrier' -> 'airfryer'
    """
    norm = normalize_text(text)
    norm = re.sub(
        r"\b(?:a[yi]+r|ar)\s*(?:fr[iy]+er|fra[iy]+er|frier|fry)\b",
        " airfryer ",
        norm,
    )
    norm = re.sub(r"\bmicro\s+ondas\b", " microondas ", norm)
    norm = re.sub(r"(\d+)\s*(?:\"|''|pol\b|polegadas\b)", r"\1 polegada ", norm)
    norm = re.sub(r"(\d+)[,\.](\d+)\s*(?:l\b|litros?\b)", r"\1_\2l ", norm)
    norm = re.sub(r"(\d+)\s+(w|v|l)\b", r"\1\2", norm)
    norm = re.sub(r"(\d+)(gb|tb|hz|mm|cm)\b", r"\1 \2", norm)
    return [w for w in re.split(r"\W+", norm) if w]


def stem_word(word: str) -> str:
    """Normaliza plural simples em português (ex: polegadas -> polegada)."""
    if len(word) > 4 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def expand_synonyms(tokens: list[str]) -> list[str]:
    """Expande abreviações conhecidas (ex: ps5 -> playstation 5, ps4 -> playstation 4)."""
    expanded: list[str] = []
    for t in tokens:
        if t == "ps5":
            expanded.extend(["playstation", "5"])
        elif t == "ps4":
            expanded.extend(["playstation", "4"])
        else:
            expanded.append(t)
    return expanded


def normalize_store_name(raw_store: str) -> str:
    """Padroniza nomes de lojas vindas de diferentes buscadores."""
    s = raw_store.strip()
    low = s.lower()
    if "mercado livre" in low or "mercadolivre" in low:
        return "Mercado Livre"
    if "shopee" in low:
        return "Shopee"
    if "amazon" in low:
        return "Amazon"
    if "kabum" in low:
        return "KaBuM!"
    if "magalu" in low or "magazine luiza" in low:
        return "Magazine Luiza"
    if "aliexpress" in low:
        return "AliExpress"
    if "casas bahia" in low:
        return "Casas Bahia"
    if "americanas" in low:
        return "Americanas"
    if "enjoei" in low:
        return "Enjoei"
    if "olx" in low:
        return "OLX"
    if "facebook" in low:
        return "Facebook Marketplace"
    return s


def parse_brl_price(price_text: str) -> float | None:
    """
    Converte strings monetárias em float, suportando:
    - Formato BRL padrão: 'R$ 1.699,90' -> 1699.90
    - Formato inteiro com milhar (OLX): 'R$ 5.200' -> 5200.0
    - Formato Facebook Marketplace: 'R$ 2,300', 'R $3,500', 'R$2850,' -> 2300.0, 3500.0, 2850.0
    """
    if not price_text:
        return None

    m = re.search(r"R\s*\$\s*(\d[\d\.,]*\d|\d+)", price_text)
    if m:
        target = m.group(1)
    elif re.fullmatch(r"[\s\d\.,]+", price_text.strip()):
        target = price_text.strip().strip(".,")
    else:
        return None

    # Caso 1: Vírgula seguida de exatamente 3 dígitos no final (milhar padrão US do FB Marketplace: '2,300')
    if re.search(r",\d{3}$", target) and "." not in target:
        cleaned = target.replace(",", "")
    # Caso 2: Vírgula seguida de 1 ou 2 dígitos no final (centavos padrão BR: '1.699,90' ou '56,36')
    elif re.search(r",\d{1,2}$", target):
        cleaned = target.replace(".", "").replace(",", ".")
    # Caso 3: Sem centavos ('5.200' na OLX ou '2850')
    else:
        cleaned = target.replace(".", "").replace(",", "")

    try:
        return float(cleaned)
    except ValueError:
        return None


def decode_redirect_url(href: str) -> str:
    """
    Desembrulha links de redirecionamento do Yahoo/Bing/DoubleClick/AliExpress
    para obter a URL direta da loja (Mercado Livre, Shopee, Amazon, KaBuM!, etc.).
    """
    if not href:
        return ""

    url = href
    m_ru = re.search(r"/RU=([^/]+)/", url)
    if m_ru:
        url = unquote(m_ru.group(1))

    m_u = re.search(r"[?&]u=([A-Za-z0-9+/=%_-]+)", url)
    if m_u:
        b64 = unquote(m_u.group(1))
        if b64.startswith("a1"):
            b64 = b64[2:]
        b64 += "=" * ((4 - len(b64) % 4) % 4)
        try:
            decoded = base64.urlsafe_b64decode(b64).decode("utf-8", errors="ignore")
            decoded = unquote(decoded)
            if decoded.startswith("http"):
                url = decoded
            elif decoded.startswith("/"):
                url = "https://www.bing.com" + decoded
        except Exception:
            pass

    for param in ("ds_dest_url", "dl_target_url", "url"):
        m_dest = re.search(rf"[?&]{param}=([^&]+)", url)
        if m_dest:
            candidate = unquote(m_dest.group(1))
            if candidate.startswith("http"):
                url = candidate
                break

    if url.startswith("/"):
        return "https://www.bing.com" + url
    return url


def infer_store_from_url(url: str) -> str | None:
    """Identifica o nome da loja a partir do domínio da URL."""
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return None
    for domain, store_name in DOMAIN_STORE_MAP.items():
        if domain in host:
            return store_name
    return None


def extract_card_image(card: Any) -> str:
    """
    Extrai a URL real da imagem do produto em cards (suporta lazy-load div.rms_iac[data-src],
    img[src], img[data-src] e ignora ícones 18x18 ou base64).
    """
    for sel in (
        ".br-offImg img",
        ".br-pdMainImg img",
        "div.rms_iac[data-src]",
        "img.s-img",
        "img",
        "[data-src]",
    ):
        for el in card.select(sel):
            if el.get("width") in ("16", "18", "20") or el.find_parent(class_="br-offNewTabIc"):
                continue
            candidate = (
                el.get("data-src")
                or el.get("src")
                or (el.get("srcset", "").split()[0] if el.get("srcset") else "")
            )
            if not candidate or candidate.startswith("data:"):
                continue
            if candidate.startswith("//"):
                return "https:" + candidate
            if candidate.startswith("/th"):
                return "https://www.bing.com" + candidate
            if candidate.startswith("http"):
                return candidate
    return ""

