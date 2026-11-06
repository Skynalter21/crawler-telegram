from difflib import SequenceMatcher
import re
import unicodedata
import httpx

ECOMMERCE_VOCABULARY = (
    # Eletroportáteis e Cozinha
    "airfryer", "fritadeira", "cafeteira", "nespresso", "dolce", "gusto",
    "liquidificador", "batedeira", "microondas", "forno", "eletrico",
    "sanduicheira", "grill", "panela", "pressao", "eletrica", "pipoqueira",
    "torradeira", "chaleira", "processador", "alimentos", "mixer", "espremedor",
    "purificador", "agua", "bebedouro", "adega", "cervejeira", "churrasqueira",
    # Linha Branca e Casa
    "geladeira", "refrigerador", "freezer", "fogao", "cooktop", "coifa",
    "depurador", "lava", "loucas", "lavadora", "roupas", "secadora",
    "tanquinho", "centrifuga", "aspirador", "robo", "vaporetto", "ferro",
    "passar", "vaporizador", "ventilador", "circulador", "climatizador",
    "condicionado", "split", "inverter", "aquecedor", "umidificador",
    "desumidificador", "luminaria", "lampada", "fechadura", "digital",
    # TV, Áudio e Vídeo
    "televisao", "smartv", "oled", "qled", "nanocell", "crystal", "uhd",
    "projetor", "soundbar", "home", "theater", "caixa", "som", "jbl",
    "boombox", "charge", "flip", "partybox", "extreme", "alexa", "echo",
    "fire", "stick", "chromecast", "roku", "aparelho",
    # Celulares, Tablets e Wearables
    "iphone", "samsung", "galaxy", "xiaomi", "redmi", "poco", "motorola",
    "moto", "edge", "realme", "asus", "zenfone", "infinix", "celular",
    "smartphone", "ipad", "tablet", "tab", "apple", "watch", "smartwatch",
    "garmin", "amazfit", "miband", "airpods", "earbuds", "buds",
    # Games e Consoles
    "playstation", "ps5", "ps4", "dualsense", "xbox", "series", "nintendo",
    "switch", "steam", "deck", "rog", "ally", "controle", "joystick",
    "volante", "logitech", "thrustmaster",
    # Informática e Hardware
    "notebook", "macbook", "ultrabook", "chromebook", "computador", "desktop",
    "monitor", "gamer", "curvo", "ultrawide", "placa", "video", "geforce",
    "rtx", "gtx", "radeon", "processador", "ryzen", "intel", "core",
    "placa", "mae", "memoria", "ram", "ddr4", "ddr5", "ssd", "nvme",
    "kingston", "corsair", "crucial", "sandisk", "seagate", "western",
    "gabinete", "fonte", "water", "cooler", "air", "teclado", "mecanico",
    "mouse", "mousepad", "headset", "fone", "ouvido", "bluetooth", "hyperx",
    "razer", "redragon", "steelseries", "webcam", "microfone", "impressora",
    "multifuncional", "epson", "ecotank", "hp", "brother", "canon", "roteador",
    "mesh", "tp-link", "cadeira", "escritorio", "mesa",
    # Bebidas, Mercado e Suplementos
    "cerveja", "heineken", "stella", "artois", "budweiser", "corona", "spaten",
    "amstel", "brahma", "duplo", "malte", "original", "antarctica", "becks",
    "patagonia", "eisenbahn", "colorado", "chopp", "whisky", "johnnie",
    "walker", "jack", "daniels", "chivas", "old", "parr", "buchanans",
    "ballantines", "gin", "tanqueray", "beefeater", "bombay", "vodka",
    "absolut", "smirnoff", "ciroc", "grey", "goose", "vinho", "espumante",
    "energetico", "redbull", "monster", "baly", "refrigerante", "coca",
    "cola", "guarana", "cafe", "pilao", "melitta", "tres", "coracoes",
    "lor", "starbucks", "whey", "protein", "isolado", "concentrado",
    "creatina", "monohidratada", "max", "titanium", "integralmedica",
    "growth", "dark", "lab", "black", "skull", "dux", "yopro", "barra",
    "proteina", "pre", "treino", "glutamina", "colageno", "vitamina",
    "chocolate", "lacta", "nestle", "garoto", "ferrero", "rocher", "nutella",
    "lindt", "milka", "kitkat", "bis", " bombom", "azeite", "fralda", "pampers",
    "huggies", "sabao", "omo", "downy", "amaciante",
    # Moda, Esporte e Ferramentas
    "tenis", "nike", "adidas", "puma", "asics", "mizuno", "olympikus",
    "fila", "vans", "converse", "all", "star", "new", "balance", "under",
    "armour", "camiseta", "moletom", "jaqueta", "mochila", "mala", "viagem",
    "garrafa", "termica", "copo", "stanley", "kouda", "pacco", "bicicleta",
    "esteira", " perfume", "importado", "hidratante", "protetor", "solar",
    "shampoo", "condicionador", "secador", "cabelo", "chapinha", "prancha",
    "modelador", "barbeador", "aparador", "philips", "oneblade", "wahl",
    "furadeira", "parafusadeira", "bosch", "makita", "dewalt", "black",
    "decker", "vonder", "wap", "lavadora", "alta", "pressao", "karcher",
    # Marcas de Eletro
    "mondial", "philco", "britania", "arno", "oster", "cadence", "mallory",
    "electrolux", "brastemp", "consul", "panasonic", "midea", "springer",
    "lg", "tcl", "aoc", "hisense", "toshiba", "multilaser", "positivo",
    "dell", "lenovo", "acer", "vaio", "gigabyte", "msi", "galax", "zotac",
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
    "eyrfryer": "air fryer",
    "erfryer": "air fryer",
    "fritadera": "fritadeira",
    "ifone": "iphone",
    "ipone": "iphone",
    "iphon": "iphone",
    "ayfone": "iphone",
    "aifone": "iphone",
    "sansung": "samsung",
    "sansumg": "samsung",
    "samsumg": "samsung",
    "samzung": "samsung",
    "xiomi": "xiaomi",
    "xiami": "xiaomi",
    "xiaome": "xiaomi",
    "xaomi": "xiaomi",
    "xaiomi": "xiaomi",
    "motorolla": "motorola",
    "pleisteixon": "playstation",
    "pleystation": "playstation",
    "playstatiom": "playstation",
    "plaistation": "playstation",
    "notebuk": "notebook",
    "notbook": "notebook",
    "notbuk": "notebook",
    "notebool": "notebook",
    "heinekem": "heineken",
    "heinek": "heineken",
    "haineken": "heineken",
    "reneken": "heineken",
    "cerveija": "cerveja",
    "serveja": "cerveja",
    "geladera": "geladeira",
    "jeladeira": "geladeira",
    "liquidficador": "liquidificador",
    "liquitificador": "liquidificador",
    "microonda": "microondas",
    "televizao": "televisao",
    "monito": "monitor",
    "munitor": "monitor",
    "headcet": "headset",
    "redset": "headset",
    "foni": "fone",
    "blutooth": "bluetooth",
    "bluetoth": "bluetooth",
    "blutu": "bluetooth",
    "churasqueira": "churrasqueira",
    "churrasquera": "churrasqueira",
    "ventilado": "ventilador",
    "cafetera": "cafeteira",
    "criatina": "creatina",
    "wei": "whey",
    "wey": "whey",
    "iopro": "yopro",
}


def normalize_text(text: str) -> str:
    """Remove acentos e converte para minúsculas."""
    nfkd = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def phonetic_skeleton(word: str) -> str:
    """
    Cria esqueleto fonético para aproximar erros ortográficos comuns em PT-BR/EN:
    Ex: 'ayirfrier' -> 'airfrier', 'airfryer' -> 'airfrier' (100% de match fonético!).
    """
    w = normalize_text(word)
    w = w.replace("ph", "f").replace("y", "i").replace("w", "v").replace("k", "c")
    w = w.replace("ch", "x").replace("sh", "x").replace("ç", "s").replace("z", "s")
    w = re.sub(r"([a-z])\1+", r"\1", w)
    w = re.sub(r"ai+", "ai", w)
    w = re.sub(r"ei+", "ei", w)
    return w


def fuzzy_word_similarity(word1: str, word2: str) -> float:
    """Calcula a similaridade combinando escrita literal e fonética."""
    w1, w2 = normalize_text(word1), normalize_text(word2)
    if w1 == w2:
        return 1.0
    raw_ratio = SequenceMatcher(None, w1, w2).ratio()
    p1, p2 = phonetic_skeleton(w1), phonetic_skeleton(w2)
    if p1 == p2 and len(p1) >= 3:
        return 0.96
    phonetic_ratio = SequenceMatcher(None, p1, p2).ratio()
    return max(raw_ratio, phonetic_ratio * 0.96)


def correct_query_local(query: str) -> str:
    """
    Corrige erros de digitação na busca do usuário (ex: 'ayirfrier' -> 'air fryer',
    'ifone 15' -> 'iphone 15') usando mapa direto + similaridade fonética/fuzzy.
    """
    norm_q = normalize_text(query).strip()
    if not norm_q:
        return query.strip()

    # Trata variações de Air Fryer escritas juntas ou separadas
    norm_q = re.sub(
        r"\b(?:a[yi]+r|ar|e[yi]*r)\s*(?:fr[iy]+er|fra[iy]+er|frier|fry)\b",
        "air fryer",
        norm_q,
    )

    tokens = norm_q.split()
    corrected: list[str] = []

    for token in tokens:
        clean_t = re.sub(r"\W+", "", token)
        if not clean_t or any(ch.isdigit() for ch in clean_t) or len(clean_t) < 3:
            corrected.append(token)
            continue

        if clean_t in DIRECT_TYPO_MAP:
            corrected.append(DIRECT_TYPO_MAP[clean_t])
            continue

        if clean_t in ECOMMERCE_VOCABULARY:
            corrected.append(clean_t)
            continue

        best_candidate = clean_t
        best_score = 0.0
        for vocab_word in ECOMMERCE_VOCABULARY:
            score = fuzzy_word_similarity(clean_t, vocab_word)
            if score > best_score:
                best_score = score
                best_candidate = vocab_word

        if best_score >= 0.77:
            corrected.append("air fryer" if best_candidate == "airfryer" else best_candidate)
        else:
            corrected.append(token)

    return " ".join(corrected)


async def fetch_online_suggestion(query: str) -> str | None:
    """
    Consulta APIs públicas de Autocomplete (Google / DuckDuckGo) como fallback
    para descobrir termos comerciais ou marcas digitadas com erro.
    """
    url = "https://suggestqueries.google.com/complete/search"
    params = {"client": "firefox", "hl": "pt-BR", "q": query}
    try:
        async with httpx.AsyncClient(timeout=2.5) as client:
            resp = await client.get(url, params=params)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and len(data) > 1 and isinstance(data[1], list) and data[1]:
                    first_suggestion = str(data[1][0]).strip()
                    if first_suggestion and first_suggestion.lower() != query.lower():
                        return first_suggestion
    except Exception:
        pass
    return None

