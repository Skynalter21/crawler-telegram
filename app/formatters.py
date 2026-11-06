import html
import re
from statistics import median
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse


UNWANTED_OFFER_WORDS = {
    "jogo", "jogos", "game", "games", "midia", "dlc", "gift", "card",
    "cartao", "assinatura", "joycon", "dock", "grip", "troco", "procuro",
    "compro", "aluguel", "locacao", "conta", "capa", "capinha", "pelicula",
    "case", "estojo", "suporte", "adesivo", "skin", "cabo", "fonte",
    "carregador", "bolsa", "mochila", "maleta", "protetor", "caixa",
    "embalagem", "manual", "defeito", "sucata", "pecas", "reposicao",
}

CONSOLE_QUERY_KEYWORDS = {"switch", "nintendo", "ps5", "ps4", "playstation", "xbox"}

GAME_TITLE_INDICATORS = {
    "zelda", "mario", "pokemon", "ocarina", "crossing", "kirby", "metroid",
    "splatoon", "donkey", "smash", "fifa", "fc25", "fc26", "gta", "spiderman",
    "god of war", "horizon", "gran turismo", "resident evil", "final fantasy",
    "elden ring", "cyberpunk", "minecraft", "sonic", "call of duty",
}

TRACKING_QUERY_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "msclkid", "matt_tool", "matt_word", "matt_source", "matt_campaign",
    "matt_campaign_id", "matt_ad_group", "matt_match_type", "matt_network",
    "matt_device", "matt_keyword", "tag", "linkCode", "hvadid", "hvnetw",
    "hvqmt", "hvbmt", "hvdev", "hvlocint", "hvlocphy", "hvtargid",
}


def format_brl(value: float | int | None, include_symbol: bool = True) -> str:
    """Formata um valor numérico como moeda Real (R$ 1.234,56 ou 1.234,56)."""
    if value is None:
        return "—"
    formatted = f"{float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {formatted}" if include_symbol else formatted


def is_valid_store_url(url: str) -> bool:
    """
    Verifica se a URL aponta para uma página real de loja/produto
    e não para páginas internas quebradas do Bing/Yahoo.
    """
    if not url or not url.startswith("http"):
        return False
    low = url.lower()
    if "bing.com/shop" in low or "bing.com/search" in low or "search.yahoo.com" in low:
        return False
    return True


def clean_store_url(url: str) -> str:
    """
    Limpa parâmetros de rastreamento gigantes e corrige espaços/aspas na URL
    para garantir que o link abra perfeitamente em qualquer navegador/celular.
    """
    if not url:
        return ""
    raw = url.strip().replace(" ", "%20").replace('"', "%22")

    # Link canônico curto para Amazon Brasil
    m_amz = re.search(r"amazon\.com\.br/(?:[^/]+/)?dp/([A-Z0-9]{10})", raw)
    if m_amz:
        return f"https://www.amazon.com.br/dp/{m_amz.group(1)}"

    try:
        parsed = urlparse(raw)
        filtered_qs = [
            (k, v)
            for k, v in parse_qsl(parsed.query, keep_blank_values=False)
            if k not in TRACKING_QUERY_PARAMS
        ]
        new_query = urlencode(filtered_qs, doseq=True)
        cleaned = urlunparse(
            (parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, "")
        )
        return cleaned
    except Exception:
        return raw


def _is_relevant_main_product(offer: dict[str, Any], query: str) -> bool:
    """
    Garante que jogos, acessórios, capas ou anúncios de troca ('Troco X por Y')
    não sejam escolhidos quando o usuário buscou o produto principal (ex: Console).
    """
    url = str(offer.get("url") or "").strip()
    if not is_valid_store_url(url):
        return False

    if "/jogos-de-video-game/" in url.lower():
        if "jogo" not in query.lower() and "game" not in query.lower():
            return False

    title_low = str(offer.get("title") or "").lower()
    query_words = set(re.findall(r"\w+", query.lower()))

    # Analisa a parte principal do título (antes de '+' para permitir bundles 'Console + Jogo')
    main_part = re.split(r"\s+\+\s+", title_low)[0]
    main_words = set(re.findall(r"\w+", main_part))

    unwanted = UNWANTED_OFFER_WORDS - query_words
    if main_words & unwanted:
        # Se tem 'console' explícito no começo e a palavra indesejada era 'jogo'/'jogos' num bundle, permite apenas se começar com console
        if not (main_part.startswith("console") and not (main_words & (unwanted - {"jogo", "jogos", "assinatura"}))):
            return False

    # Se a busca é por um console (ex: 'switch 2', 'ps5') sem pedir jogo:
    if (query_words & CONSOLE_QUERY_KEYWORDS) and not (query_words & {"jogo", "jogos", "game", "games"}):
        if "console" not in main_words:
            for game_kw in GAME_TITLE_INDICATORS:
                if game_kw in main_part and game_kw not in query.lower():
                    return False
            # Títulos como "The Legend of ... Edition Nintendo Switch 2" sem a palavra "Console"
            if "edition" in main_words and not main_part.startswith(("nintendo", "switch", "playstation", "ps5", "xbox", "console")):
                return False

    return True


def _filter_Consistent_price_pool(offers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Remove outliers de preço (ex: jogos/acessórios muito mais baratos que o produto
    principal ou anúncios com preço 3x acima do mercado) para não distorcer a escolha nem a média.
    """
    if len(offers) < 3:
        return offers

    prices = [float(o["price"]) for o in offers if float(o.get("price", 0)) > 0]
    if not prices:
        return offers

    med = median(prices)
    # Filtra itens que custam menos de 55% da mediana (acessórios/jogos) ou mais de 220% da mediana
    consistent = [
        o for o in offers
        if (med * 0.55) <= float(o.get("price", 0)) <= (med * 2.20)
    ]
    return consistent or offers


def select_best_offer_and_image(search_data: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    """
    Seleciona a melhor oferta real e consistente (priorizando produto Novo de varejo,
    com link direto funcional e sem misturar jogos/acessórios com consoles).
    """
    query = str(search_data.get("query") or "")
    raw_results: list[dict[str, Any]] = search_data.get("results") or []
    if not raw_results:
        return None, ""

    valid_results = [r for r in raw_results if _is_relevant_main_product(r, query)]
    if not valid_results:
        valid_results = [r for r in raw_results if is_valid_store_url(str(r.get("url", "")))]
    if not valid_results:
        return None, ""

    # Remove outliers estatísticos (ex: jogo de R$ 999 no meio de consoles de R$ 3.800)
    consistent_results = _filter_Consistent_price_pool(valid_results)

    new_offers = [r for r in consistent_results if not r.get("is_used")]
    retail_new_offers = [
        r
        for r in new_offers
        if str(r.get("source", "")).lower() not in ("olx", "enjoei", "facebook_marketplace")
    ]

    chosen_pool = _filter_Consistent_price_pool(retail_new_offers or new_offers or consistent_results)
    best_offer = chosen_pool[0]

    image_url = str(best_offer.get("image") or "").strip()
    if not image_url:
        for candidate in chosen_pool + consistent_results:
            img = str(candidate.get("image") or "").strip()
            if img.startswith("http"):
                image_url = img
                break

    return best_offer, image_url


def format_crawler_promotion_message(
    search_data: dict[str, Any],
    header_title: str = "",
    short_url: str | None = None,
) -> str:
    """
    Formata a legenda da promoção no estilo visual limpo de canal de ofertas,
    calculando a economia apenas sobre ofertas equivalentes do mesmo produto
    e exibindo um link real que abre diretamente.
    """
    query = str(search_data.get("query", ""))
    best_offer, _ = select_best_offer_and_image(search_data)

    if not best_offer:
        return (
            f"🔎 <b>{html.escape(query)}</b>\n\n"
            f"⚠️ Nenhuma oferta compatível encontrada no momento."
        )

    is_used = bool(best_offer.get("is_used"))
    title = html.escape(str(best_offer.get("title", query)).strip())
    store = html.escape(str(best_offer.get("store", "Loja")).strip())
    price = float(best_offer.get("price", 0))
    raw_url = str(best_offer.get("url", "")).strip()
    cleaned_url = clean_store_url(raw_url)
    final_url = short_url or cleaned_url

    # Calcula preço médio/referência apenas entre ofertas consistentes da mesma condição (Novo vs Usado)
    raw_results: list[dict[str, Any]] = search_data.get("results") or []
    valid_same_condition = [
        r for r in raw_results
        if _is_relevant_main_product(r, query) and bool(r.get("is_used")) == is_used
    ]
    consistent_pool = _filter_Consistent_price_pool(valid_same_condition)
    pool_prices = [float(r["price"]) for r in consistent_pool if float(r.get("price", 0)) > 0]

    reference_price = 0.0
    if len(pool_prices) >= 2:
        avg_consistent = sum(pool_prices) / len(pool_prices)
        med_consistent = median(pool_prices)
        reference_price = max(avg_consistent, med_consistent)

    diff_pct = (
        round(((reference_price - price) / reference_price) * 100)
        if reference_price > price > 0
        else 0
    )

    lines: list[str] = []
    if header_title:
        lines.append(header_title)
        lines.append("")

    lines.append(f"🔥 <b>{title}</b>")
    lines.append("")

    condition_note = f"seminovo na <b>{store}</b>" if is_used else f"menor preço na <b>{store}</b>"
    lines.append(f"⚠️ {condition_note}")

    if 4 <= diff_pct <= 55:
        lines.append(f"⚠️ economia de <b>{diff_pct}%</b> abaixo da média do mercado")
    else:
        total_stores = len(search_data.get("stores") or [])
        if total_stores > 1:
            lines.append(f"⚠️ comparado em {total_stores} lojas em tempo real")

    price_str = format_brl(price, include_symbol=False)
    if 4 <= diff_pct <= 55 and reference_price > price:
        ref_str = format_brl(reference_price, include_symbol=False)
        lines.append(f"🟢 de <s>{ref_str}</s> por <b>R$ {price_str}</b>")
    else:
        lines.append(f"🟢 por <b>R$ {price_str}</b>")

    lines.append("")

    safe_url = html.escape(final_url)
    lines.append(f"🎯 <a href=\"{safe_url}\">{safe_url}</a>")

    return "\n".join(lines)


def format_terms_list_message(terms: list[str], next_term: str | None) -> str:
    """Formata a lista de termos/produtos monitorados pelo grupo."""
    if not terms:
        return (
            "📋 <b>Lista de Produtos do Grupo Vazia!</b>\n\n"
            "Adicione produtos para o bot buscar automaticamente de tempos em tempos:\n"
            "• <code>/adicionar ps5</code>\n"
            "• <code>/adicionar rtx 4060</code>\n"
            "• <code>/adicionar cerveja heineken</code>"
        )

    lines = ["📋 <b>Produtos Monitorados no Ciclo Automático:</b>\n"]
    for i, term in enumerate(terms, start=1):
        is_next = next_term is not None and term.lower() == next_term.lower()
        pointer = " 👈 <i>(próximo envio)</i>" if is_next else ""
        lines.append(f"<b>{i}.</b> <code>{html.escape(term)}</code>{pointer}")

    lines.extend(
        [
            "",
            "🛠️ <b>Como editar a lista pelo grupo:</b>",
            "• <code>/adicionar &lt;produto&gt;</code> — Adiciona novo item na fila",
            "• <code>/remover &lt;número ou nome&gt;</code> — Remove um item (ex: <code>/remover 2</code>)",
            "• <code>/ofertas</code> — Dispara o próximo item da fila agora mesmo",
        ]
    )
    return "\n".join(lines)


def format_sample_promotion_message(is_manual_test: bool = False) -> str:
    """Fallback caso o Crawler esteja desligado no momento do teste."""
    return (
        "🔥 <b>12 un. YoPRO 15g Proteína 250ml chocolate</b>\n\n"
        "⚠️ menor preço na <b>Amazon</b>\n"
        "⚠️ economia de <b>38%</b> abaixo da média do mercado\n"
        "🟢 de <s>98,29</s> por <b>R$ 60,80</b>\n\n"
        "🎯 <a href=\"https://www.amazon.com.br\">https://www.amazon.com.br</a>"
    )


def format_chat_id_message(
    chat_id: int,
    chat_title: str | None,
    chat_type: str,
    linked_chat_id: int | None,
) -> str:
    """Formata os dados de identificação do chat/grupo atual."""
    safe_title = html.escape(chat_title or "Chat Privado")
    is_linked = linked_chat_id == chat_id
    status_badge = (
        "✅ <b>Este chat JÁ ESTÁ vinculado aos envios automáticos!</b>"
        if is_linked
        else "💡 <i>Para ativar o envio periódico neste grupo, digite:</i> <code>/vincular</code>"
    )

    return (
        f"🆔 <b>Identificação deste Chat</b>\n\n"
        f"• <b>Nome:</b> {safe_title}\n"
        f"• <b>Tipo:</b> <code>{html.escape(chat_type)}</code>\n"
        f"• <b>Chat ID:</b> <code>{chat_id}</code>\n\n"
        f"📋 Configurado no <code>.env</code>:\n"
        f"<code>TELEGRAM_CHAT_ID={chat_id}</code>\n\n"
        f"{status_badge}"
    )


def format_status_message(
    chat_id: int | None,
    interval_minutes: int,
    auto_send_enabled: bool,
    next_run_str: str | None,
    crawler_api_url: str,
    terms_count: int = 0,
    next_term: str | None = None,
) -> str:
    """Formata o painel de status atual do bot."""
    chat_str = (
        f"<code>{chat_id}</code>"
        if chat_id is not None
        else "⚠️ <i>Não vinculado (use /vincular no grupo)</i>"
    )
    state_str = (
        "🟢 Ativo"
        if (auto_send_enabled and chat_id is not None)
        else "🔴 Pausado / Aguardando vínculo"
    )
    next_str = next_run_str or "—"
    next_term_str = f"<code>{html.escape(next_term)}</code>" if next_term else "<i>Lista vazia</i>"

    return (
        f"⚙️ <b>Painel de Configuração do Bot</b>\n\n"
        f"• <b>Status do Agendador:</b> {state_str}\n"
        f"• <b>Grupo Vinculado (Chat ID):</b> {chat_str}\n"
        f"• <b>Intervalo de Envio:</b> a cada <b>{interval_minutes} min</b>\n"
        f"• <b>Próximo Disparo:</b> <code>{html.escape(next_str)}</code>\n"
        f"• <b>Produtos na Fila:</b> <b>{terms_count}</b> (Próximo: {next_term_str})\n"
        f"• <b>API do Crawler:</b> <code>{html.escape(crawler_api_url)}</code>\n\n"
        f"🛠️ <b>Comandos de Controle Rápido:</b>\n"
        f"• <code>/lista</code> — Ver produtos cadastrados no ciclo automático\n"
        f"• <code>/adicionar &lt;produto&gt;</code> — Cadastrar produto no ciclo\n"
        f"• <code>/ofertas</code> ou <code>/teste</code> — Buscar e postar a próxima oferta agora\n"
        f"• <code>/intervalo 30</code> — Muda o tempo entre envios (em minutos)\n"
        f"• <code>/pausar</code> ou <code>/retomar</code> — Pausa/retoma o envio automático"
    )
