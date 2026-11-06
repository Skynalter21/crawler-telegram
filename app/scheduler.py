import logging
from typing import Any
from telegram import Bot
from telegram.constants import ParseMode
from telegram.ext import Application, ContextTypes

from app.config import BotSettings
from app.crawler_client import CrawlerClient, CrawlerClientError
from app.formatters import (
    clean_store_url,
    format_crawler_promotion_message,
    select_best_offer_and_image,
)
from app.terms_store import TermsStore

logger = logging.getLogger(__name__)

PERIODIC_JOB_NAME = "periodic_group_promotion_job"


async def send_promotion_card(
    bot: Bot,
    chat_id: int,
    crawler: CrawlerClient,
    search_data: dict[str, Any],
    header_title: str = "",
) -> None:
    """
    Envia o card de promoção no grupo do Telegram com a FOTO grande do produto no topo
    e a legenda limpa embaixo (estilo canal de promoções), com fallback para texto se não houver foto.
    """
    best_offer, image_url = select_best_offer_and_image(search_data)
    short_url: str | None = None
    if best_offer and best_offer.get("url"):
        cleaned = clean_store_url(str(best_offer["url"]))
        short_url = await crawler.shorten_url(cleaned)

    caption_html = format_crawler_promotion_message(
        search_data=search_data,
        header_title=header_title,
        short_url=short_url,
    )

    if image_url:
        image_bytes = await crawler.fetch_image_bytes(image_url)
        try:
            if image_bytes:
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=image_bytes,
                    caption=caption_html,
                    parse_mode=ParseMode.HTML,
                )
                return
            else:
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=image_url,
                    caption=caption_html,
                    parse_mode=ParseMode.HTML,
                )
                return
        except Exception as exc:
            logger.warning("Falha ao enviar foto (%s), enviando como texto: %s", image_url, exc)

    await bot.send_message(
        chat_id=chat_id,
        text=caption_html,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )


async def send_next_rotation_offer(
    bot: Bot,
    chat_id: int,
    settings: BotSettings,
    terms_store: TermsStore,
    header_title: str = "",
) -> None:
    """
    Pega o próximo termo da fila de rotação do grupo, consulta o Crawler
    e envia o card com foto + oferta no Telegram.
    """
    next_term = terms_store.get_next_term()
    if not next_term:
        await bot.send_message(
            chat_id=chat_id,
            text=(
                "📋 <b>A fila de produtos do grupo está vazia!</b>\n"
                "Use <code>/adicionar &lt;produto&gt;</code> para cadastrar itens no ciclo automático."
            ),
            parse_mode=ParseMode.HTML,
        )
        return

    crawler = CrawlerClient(base_url=settings.crawler_api_url)
    logger.info("Buscando promoção no Crawler para o termo '%s'...", next_term)
    search_data = await crawler.search_product(query=next_term)
    await send_promotion_card(
        bot=bot,
        chat_id=chat_id,
        crawler=crawler,
        search_data=search_data,
        header_title=header_title,
    )


async def periodic_promotion_callback(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Callback executado periodicamente pelo JobQueue para enviar promoção ao grupo."""
    settings: BotSettings = context.application.bot_data.get("settings")
    terms_store: TermsStore = context.application.bot_data.get("terms_store") or TermsStore()
    if not settings or not settings.auto_send_enabled or settings.chat_id is None:
        return

    try:
        await send_next_rotation_offer(
            bot=context.bot,
            chat_id=settings.chat_id,
            settings=settings,
            terms_store=terms_store,
        )
        logger.info("Promoção periódica enviada com sucesso para chat_id=%s", settings.chat_id)
    except CrawlerClientError as exc:
        logger.error("Erro do Crawler no envio periódico: %s", exc)
    except Exception as exc:
        logger.error("Erro inesperado no envio periódico para chat_id=%s: %s", settings.chat_id, exc)


def sync_periodic_job(application: Application, settings: BotSettings) -> None:
    """
    Sincroniza o JobQueue com as configurações atuais (cria, atualiza o intervalo
    ou remove o job caso esteja pausado ou sem chat_id vinculado).
    """
    job_queue = application.job_queue
    if job_queue is None:
        logger.warning("JobQueue não está disponível na Application.")
        return

    existing_jobs = job_queue.get_jobs_by_name(PERIODIC_JOB_NAME)
    for job in existing_jobs:
        job.schedule_removal()

    if not settings.auto_send_enabled:
        logger.info("Envio automático está PAUSADO (AUTO_SEND_ENABLED=false).")
        return

    if settings.chat_id is None:
        logger.info(
            "Aguardando vínculo de grupo (TELEGRAM_CHAT_ID vazio). "
            "Adicione o bot no grupo e envie /vincular."
        )
        return

    interval_seconds = max(60, settings.schedule_interval_minutes * 60)
    job_queue.run_repeating(
        callback=periodic_promotion_callback,
        interval=interval_seconds,
        first=interval_seconds,
        name=PERIODIC_JOB_NAME,
        chat_id=settings.chat_id,
    )
    logger.info(
        "Agendador periódico ativo: enviando para chat_id=%s a cada %d minuto(s).",
        settings.chat_id,
        settings.schedule_interval_minutes,
    )


def get_next_run_formatted(application: Application) -> str | None:
    """Retorna o horário estimado do próximo disparo periódico, se houver job ativo."""
    if application.job_queue is None:
        return None
    jobs = application.job_queue.get_jobs_by_name(PERIODIC_JOB_NAME)
    for job in jobs:
        if not job.removed and job.next_t is not None:
            local_dt = job.next_t.astimezone()
            return local_dt.strftime("%d/%m/%Y às %H:%M:%S")
    return None
