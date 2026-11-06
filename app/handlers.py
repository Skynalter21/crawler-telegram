import html
import logging
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from app.config import BotSettings
from app.crawler_client import CrawlerClient, CrawlerClientError
from app.formatters import (
    format_brl,
    format_chat_id_message,
    format_status_message,
    format_terms_list_message,
    select_best_offer_and_image,
)
from app.scheduler import (
    get_next_run_formatted,
    send_next_rotation_offer,
    send_promotion_card,
    sync_periodic_job,
)
from app.spell_corrector import correct_query_local
from app.terms_store import TermsStore

logger = logging.getLogger(__name__)


def _get_settings(context: ContextTypes.DEFAULT_TYPE) -> BotSettings:
    return context.application.bot_data["settings"]


def _get_terms_store(context: ContextTypes.DEFAULT_TYPE) -> TermsStore:
    store = context.application.bot_data.get("terms_store")
    if store is None:
        store = TermsStore()
        context.application.bot_data["terms_store"] = store
    return store


async def start_or_help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Responde aos comandos /start, /ajuda e /help."""
    if not update.effective_chat or not update.message:
        return

    chat = update.effective_chat
    settings = _get_settings(context)

    is_linked = settings.chat_id == chat.id
    link_hint = (
        "✅ <b>Este grupo já está vinculado aos envios automáticos!</b>"
        if is_linked
        else f"👉 <b>Quer que eu poste promoções neste chat?</b> Envie <code>/vincular</code> (Chat ID atual: <code>{chat.id}</code>)"
    )

    text = (
        "🤖 <b>Olá! Eu sou o Bot Caçador de Promoções do Grupo!</b>\n\n"
        f"{link_hint}\n\n"
        "🛒 <b>Comandos de Promoções e Lista do Grupo:</b>\n"
        "• <code>/buscar &lt;produto&gt;</code> — Busca o menor preço agora nas 13 lojas\n"
        "• <code>/lista</code> — Vê os produtos cadastrados no ciclo automático\n"
        "• <code>/adicionar &lt;produto&gt;</code> — Cadastra um produto no ciclo automático\n"
        "• <code>/remover &lt;nº ou nome&gt;</code> — Remove um produto da lista\n"
        "• <code>/ofertas</code> ou <code>/teste</code> — Dispara a próxima promoção da fila agora\n"
        "• <code>/alerta &lt;produto&gt; &lt;preço&gt;</code> — Compara com sua meta e adiciona na lista\n\n"
        "⚙️ <b>Comandos de Configuração e Controle:</b>\n"
        "• <code>/status</code> — Exibe configurações, intervalo e próximo envio\n"
        "• <code>/intervalo &lt;min&gt;</code> — Altera o tempo entre postagens (ex: <code>/intervalo 30</code>)\n"
        "• <code>/pausar</code> / <code>/retomar</code> — Pausa ou retoma as mensagens periódicas\n"
        "• <code>/id</code> / <code>/vincular</code> — Mostra o ID ou vincula este grupo"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mostra o ID do chat/grupo atual (/id)."""
    if not update.effective_chat or not update.message:
        return

    chat = update.effective_chat
    settings = _get_settings(context)

    text = format_chat_id_message(
        chat_id=chat.id,
        chat_title=chat.title or chat.full_name,
        chat_type=chat.type,
        linked_chat_id=settings.chat_id,
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def vincular_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Vincula o chat/grupo atual como destino das mensagens automáticas e salva no .env."""
    if not update.effective_chat or not update.message:
        return

    chat = update.effective_chat
    settings = _get_settings(context)

    settings.chat_id = chat.id
    settings.auto_send_enabled = True
    settings.save_to_env("TELEGRAM_CHAT_ID", str(chat.id))
    settings.save_to_env("AUTO_SEND_ENABLED", "true")

    sync_periodic_job(context.application, settings)
    next_run = get_next_run_formatted(context.application) or "Em breve"

    safe_title = html.escape(chat.title or chat.full_name or "Chat Atual")
    await update.message.reply_text(
        f"✅ <b>Grupo vinculado com sucesso!</b>\n\n"
        f"• <b>Destino:</b> {safe_title} (<code>{chat.id}</code>)\n"
        f"• <b>Intervalo atual:</b> a cada <b>{settings.schedule_interval_minutes} min</b>\n"
        f"• <b>Próximo envio automático:</b> <code>{next_run}</code>\n\n"
        f"💡 <i>Use <code>/lista</code> para ver os produtos monitorados ou <code>/ofertas</code> para mandar uma promoção agora!</i>",
        parse_mode=ParseMode.HTML,
    )


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Exibe o painel de status e agendamento atual (/status)."""
    if not update.message:
        return

    settings = _get_settings(context)
    terms_store = _get_terms_store(context)
    terms = terms_store.list_terms()
    next_term = terms_store.peek_next_term()
    next_run = get_next_run_formatted(context.application)

    text = format_status_message(
        chat_id=settings.chat_id,
        interval_minutes=settings.schedule_interval_minutes,
        auto_send_enabled=settings.auto_send_enabled,
        next_run_str=next_run,
        crawler_api_url=settings.crawler_api_url,
        terms_count=len(terms),
        next_term=next_term,
    )
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)


async def lista_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Mostra os termos/produtos cadastrados no ciclo automático do grupo (/lista)."""
    if not update.message:
        return

    terms_store = _get_terms_store(context)
    terms = terms_store.list_terms()
    next_term = terms_store.peek_next_term()

    await update.message.reply_text(
        format_terms_list_message(terms=terms, next_term=next_term),
        parse_mode=ParseMode.HTML,
    )


async def adicionar_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Adiciona um produto à fila de buscas periódicas do grupo (/adicionar <produto>)."""
    if not update.message:
        return

    raw_term = " ".join(context.args).strip()
    if not raw_term:
        await update.message.reply_text(
            "➕ Informe o nome do produto para adicionar na fila automática!\n"
            "Exemplo: <code>/adicionar rtx 4060</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    term = correct_query_local(raw_term)
    correction_note = (
        f"\n✨ <i>(Corrigido automaticamente de <code>{html.escape(raw_term)}</code> para <code>{html.escape(term)}</code>)</i>"
        if term.lower() != raw_term.lower()
        else ""
    )

    terms_store = _get_terms_store(context)
    added, terms = terms_store.add_term(term)
    next_term = terms_store.peek_next_term()
    safe_term = html.escape(term)

    if not added:
        await update.message.reply_text(
            f"ℹ️ O produto <code>{safe_term}</code> já está na lista do grupo!{correction_note}\n\n"
            + format_terms_list_message(terms=terms, next_term=next_term),
            parse_mode=ParseMode.HTML,
        )
        return

    await update.message.reply_text(
        f"✅ <b>Produto adicionado ao ciclo automático:</b> <code>{safe_term}</code>!{correction_note}\n\n"
        + format_terms_list_message(terms=terms, next_term=next_term),
        parse_mode=ParseMode.HTML,
    )


async def remover_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove um produto da fila automática pelo número ou nome (/remover <id_ou_nome>)."""
    if not update.message:
        return

    identifier = " ".join(context.args).strip()
    if not identifier:
        await update.message.reply_text(
            "🗑️ Informe o número ou o nome do produto para remover da lista.\n"
            "Exemplo: <code>/remover 1</code> ou <code>/remover ps5</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    terms_store = _get_terms_store(context)
    removed, terms = terms_store.remove_term(identifier)
    next_term = terms_store.peek_next_term()

    if removed is None:
        await update.message.reply_text(
            f"⚠️ Não encontrei <code>{html.escape(identifier)}</code> na lista.\n\n"
            + format_terms_list_message(terms=terms, next_term=next_term),
            parse_mode=ParseMode.HTML,
        )
        return

    await update.message.reply_text(
        f"🗑️ <b>Removido da lista:</b> <code>{html.escape(removed)}</code>\n\n"
        + format_terms_list_message(terms=terms, next_term=next_term),
        parse_mode=ParseMode.HTML,
    )


async def teste_or_ofertas_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Busca imediatamente o próximo produto da fila no Crawler e envia o card com foto no grupo
    (/ofertas ou /teste).
    """
    if not update.effective_chat or not update.message:
        return

    settings = _get_settings(context)
    terms_store = _get_terms_store(context)
    target_chat_id = settings.chat_id or update.effective_chat.id
    next_term = terms_store.peek_next_term()

    if not next_term:
        await update.message.reply_text(
            "📋 A lista de produtos está vazia! Adicione um produto primeiro:\n"
            "<code>/adicionar ps5</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    wait_msg = await update.message.reply_text(
        f"🔎 <i>Buscando a melhor promoção de <b>{html.escape(next_term)}</b>...</i>",
        parse_mode=ParseMode.HTML,
    )

    try:
        await send_next_rotation_offer(
            bot=context.bot,
            chat_id=target_chat_id,
            settings=settings,
            terms_store=terms_store,
        )
        await wait_msg.delete()
    except CrawlerClientError as exc:
        await wait_msg.edit_text(
            f"⚠️ <b>Erro ao consultar o Crawler:</b>\n<code>{html.escape(str(exc))}</code>",
            parse_mode=ParseMode.HTML,
        )


async def buscar_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Executa uma busca ao vivo no Crawler e envia o card com foto (/buscar <produto>)."""
    if not update.effective_chat or not update.message:
        return

    query = " ".join(context.args).strip()
    if not query:
        await update.message.reply_text(
            "🔎 Digite o nome do produto após o comando!\n"
            "Exemplo: <code>/buscar playstation 5</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    settings = _get_settings(context)
    safe_query = html.escape(query)
    wait_msg = await update.message.reply_text(
        f"🔎 <i>Buscando menor preço para <b>{safe_query}</b>...</i>",
        parse_mode=ParseMode.HTML,
    )

    crawler = CrawlerClient(base_url=settings.crawler_api_url)
    try:
        search_data = await crawler.search_product(query=query)
        await send_promotion_card(
            bot=context.bot,
            chat_id=update.effective_chat.id,
            crawler=crawler,
            search_data=search_data,
        )
        await wait_msg.delete()
    except CrawlerClientError as exc:
        await wait_msg.edit_text(
            f"⚠️ <b>Erro ao consultar o Crawler:</b>\n<code>{html.escape(str(exc))}</code>",
            parse_mode=ParseMode.HTML,
        )


async def alerta_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Compara o preço atual de um produto no Crawler com a meta desejada e adiciona
    o produto ao ciclo de monitoramento do grupo (/alerta <produto> <preco>).
    """
    if not update.effective_chat or not update.message:
        return

    if len(context.args) < 2:
        await update.message.reply_text(
            "🔔 <b>Como criar um alerta de preço:</b>\n"
            "Digite <code>/alerta &lt;produto&gt; &lt;preço_meta&gt;</code>\n"
            "Exemplo: <code>/alerta iphone 15 4200</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    raw_price = context.args[-1].replace("R$", "").replace(".", "").replace(",", ".")
    try:
        target_price = float(raw_price)
        if target_price <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "⚠️ O último valor deve ser o preço desejado em reais. Exemplo:\n"
            "<code>/alerta rtx 4060 1850</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    product_query = " ".join(context.args[:-1]).strip()
    settings = _get_settings(context)
    terms_store = _get_terms_store(context)
    terms_store.add_term(product_query)

    wait_msg = await update.message.reply_text(
        f"🎯 <i>Checando preço atual de <b>{html.escape(product_query)}</b>...</i>",
        parse_mode=ParseMode.HTML,
    )

    crawler = CrawlerClient(base_url=settings.crawler_api_url)
    try:
        search_data = await crawler.search_product(query=product_query)
        best_offer, _ = select_best_offer_and_image(search_data)
        if not best_offer:
            await wait_msg.edit_text(
                f"📌 Adicionei <code>{html.escape(product_query)}</code> na lista do grupo, "
                "mas nenhuma oferta foi encontrada agora.",
                parse_mode=ParseMode.HTML,
            )
            return

        current_price = float(best_offer["price"])
        reached = current_price <= target_price
        status_banner = (
            f"🎯 <b>META ATINGIDA! (Meta: {format_brl(target_price)})</b>"
            if reached
            else f"🔔 <b>Monitorado no grupo (Meta: {format_brl(target_price)})</b>"
        )
        await send_promotion_card(
            bot=context.bot,
            chat_id=update.effective_chat.id,
            crawler=crawler,
            search_data=search_data,
            header_title=status_banner,
        )
        await wait_msg.delete()
    except CrawlerClientError as exc:
        await wait_msg.edit_text(
            f"⚠️ <b>Erro ao consultar o Crawler:</b>\n<code>{html.escape(str(exc))}</code>",
            parse_mode=ParseMode.HTML,
        )


async def intervalo_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Altera o intervalo em minutos do envio periódico (/intervalo <minutos>)."""
    if not update.message:
        return

    settings = _get_settings(context)
    if not context.args:
        await update.message.reply_text(
            f"⏱️ O intervalo atual é de <b>{settings.schedule_interval_minutes} minutos</b>.\n"
            f"Para alterar, informe os minutos. Exemplo:\n"
            f"<code>/intervalo 30</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    try:
        minutes = int(context.args[0])
        if minutes < 1:
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "⚠️ Informe um número inteiro de minutos maior ou igual a 1. Exemplo: <code>/intervalo 15</code>",
            parse_mode=ParseMode.HTML,
        )
        return

    settings.schedule_interval_minutes = minutes
    settings.save_to_env("SCHEDULE_INTERVAL_MINUTES", str(minutes))
    sync_periodic_job(context.application, settings)
    next_run = get_next_run_formatted(context.application) or "Aguardando vínculo (/vincular)"

    await update.message.reply_text(
        f"✅ <b>Intervalo atualizado para {minutes} minuto(s)!</b>\n"
        f"• <b>Próximo disparo:</b> <code>{next_run}</code>",
        parse_mode=ParseMode.HTML,
    )


async def pausar_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Pausa o envio periódico de mensagens (/pausar)."""
    if not update.message:
        return

    settings = _get_settings(context)
    settings.auto_send_enabled = False
    settings.save_to_env("AUTO_SEND_ENABLED", "false")
    sync_periodic_job(context.application, settings)

    await update.message.reply_text(
        "⏸️ <b>Envio automático pausado!</b>\n"
        "Para voltar a enviar periodicamente, digite <code>/retomar</code>.",
        parse_mode=ParseMode.HTML,
    )


async def retomar_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Retoma o envio periódico de mensagens (/retomar)."""
    if not update.message:
        return

    settings = _get_settings(context)
    settings.auto_send_enabled = True
    settings.save_to_env("AUTO_SEND_ENABLED", "true")
    sync_periodic_job(context.application, settings)
    next_run = get_next_run_formatted(context.application)

    if settings.chat_id is None:
        await update.message.reply_text(
            "▶️ Envio automático ativado, mas nenhum grupo foi vinculado ainda.\n"
            "Digite <code>/vincular</code> dentro do grupo desejado!",
            parse_mode=ParseMode.HTML,
        )
        return

    await update.message.reply_text(
        f"▶️ <b>Envio automático retomado!</b>\n"
        f"• <b>Intervalo:</b> a cada {settings.schedule_interval_minutes} min\n"
        f"• <b>Próximo envio:</b> <code>{next_run or 'Em breve'}</code>",
        parse_mode=ParseMode.HTML,
    )


async def on_bot_added_to_group(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Detecta quando o bot é adicionado a um grupo e já informa o Chat ID automaticamente."""
    if not update.effective_chat or not update.message:
        return

    for member in update.message.new_chat_members:
        if member.id == context.bot.id:
            chat = update.effective_chat
            logger.info(
                "🎉 Bot adicionado ao grupo '%s'! CHAT_ID = %s",
                chat.title,
                chat.id,
            )
            await update.message.reply_text(
                f"👋 <b>Obrigado por me adicionar ao grupo {html.escape(chat.title or '')}!</b>\n\n"
                f"🆔 O ID deste grupo é: <code>{chat.id}</code>\n\n"
                f"👉 Digite <code>/vincular</code> agora mesmo para eu configurar este grupo automaticamente nos meus envios periódicos!",
                parse_mode=ParseMode.HTML,
            )


def register_handlers(application: Application) -> None:
    """Registra todos os handlers de comandos e eventos na Application."""
    application.add_handler(CommandHandler(["start", "ajuda", "help"], start_or_help_command))
    application.add_handler(CommandHandler("id", id_command))
    application.add_handler(CommandHandler("vincular", vincular_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler(["teste", "ofertas"], teste_or_ofertas_command))
    application.add_handler(CommandHandler("intervalo", intervalo_command))
    application.add_handler(CommandHandler("pausar", pausar_command))
    application.add_handler(CommandHandler("retomar", retomar_command))

    # Gerenciamento da lista de produtos do grupo + buscas no Crawler
    application.add_handler(CommandHandler(["lista", "produtos", "termos"], lista_command))
    application.add_handler(CommandHandler(["adicionar", "add"], adicionar_command))
    application.add_handler(CommandHandler(["remover", "del"], remover_command))
    application.add_handler(CommandHandler("buscar", buscar_command))
    application.add_handler(CommandHandler("alerta", alerta_command))

    # Evento automático quando o bot entra no grupo
    application.add_handler(
        MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_bot_added_to_group)
    )
