import asyncio
import logging
import os
import sys
import httpx
from telegram import BotCommand
from telegram.ext import Application, ApplicationBuilder, ContextTypes

from app.config import ENV_FILE, load_settings
from app.handlers import register_handlers
from app.scheduler import sync_periodic_job
from app.terms_store import TermsStore

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("bot.main")


BOT_COMMANDS = [
    BotCommand("buscar", "Busca o menor preço de um produto nas 13 lojas"),
    BotCommand("lista", "Vê os produtos cadastrados no ciclo automático"),
    BotCommand("adicionar", "Cadastra um produto na lista (ex: /adicionar ps5)"),
    BotCommand("remover", "Remove um produto da lista (ex: /remover 1)"),
    BotCommand("ofertas", "Busca e envia a próxima promoção da fila agora"),
    BotCommand("alerta", "Testa meta de preço e adiciona na lista"),
    BotCommand("status", "Mostra status, intervalo e próximo envio"),
    BotCommand("intervalo", "Muda o intervalo em minutos (ex: /intervalo 30)"),
    BotCommand("pausar", "Pausa os envios automáticos periódicos"),
    BotCommand("retomar", "Retoma os envios automáticos periódicos"),
    BotCommand("ajuda", "Mostra todos os comandos disponíveis"),
]


async def _handle_render_http_request(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> None:
    """
    Mini servidor HTTP assíncrono para responder ao Health Check do Render Free Web Service
    e do UptimeRobot / cron-job.org na variável de ambiente PORT.
    """
    try:
        await asyncio.wait_for(reader.read(1024), timeout=5.0)
        body = b'{"status":"ok","service":"telegram-promo-bot"}'
        response = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: application/json\r\n"
            + f"Content-Length: {len(body)}\r\n".encode("ascii")
            + b"Connection: close\r\n\r\n"
            + body
        )
        writer.write(response)
        await writer.drain()
    except Exception:
        pass
    finally:
        writer.close()


async def _render_keep_alive_callback(_context: ContextTypes.DEFAULT_TYPE) -> None:
    """Faz ping periódico na URL externa do Render (se configurada) para evitar hibernação."""
    external_url = os.getenv("RENDER_EXTERNAL_URL", "").rstrip("/")
    if not external_url:
        return
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.get(f"{external_url}/health")
    except Exception:
        pass


async def post_init(application: Application) -> None:
    """Executado automaticamente após inicializar a conexão com o Telegram."""
    settings = application.bot_data["settings"]
    terms_store: TermsStore = application.bot_data["terms_store"]
    me = await application.bot.get_me()
    await application.bot.set_my_commands(BOT_COMMANDS)

    # Se a variável PORT estiver definida (padrão do Render Web Service), sobe o Health Check HTTP
    render_port = os.getenv("PORT")
    if render_port:
        port_num = int(render_port)
        server = await asyncio.start_server(
            _handle_render_http_request, host="0.0.0.0", port=port_num
        )
        application.bot_data["http_server"] = server
        logger.info("🌐 Servidor HTTP Health Check ativo na porta %d (Render Mode)", port_num)

    if os.getenv("RENDER_EXTERNAL_URL") and application.job_queue:
        application.job_queue.run_repeating(
            callback=_render_keep_alive_callback,
            interval=600,
            first=300,
            name="render_keep_alive_job",
        )

    logger.info("============================================================")
    logger.info("🤖 Bot conectado com sucesso: @%s (ID: %s)", me.username, me.id)
    logger.info("🛒 Produtos na fila automática: %s", terms_store.list_terms())
    if settings.chat_id:
        logger.info(
            "📢 Grupo vinculado: %s (a cada %d min)",
            settings.chat_id,
            settings.schedule_interval_minutes,
        )
    else:
        logger.info(
            "📢 Nenhum grupo vinculado ainda! Adicione @%s no grupo e envie /vincular",
            me.username,
        )
    logger.info("============================================================")

    sync_periodic_job(application, settings)


def print_setup_instructions() -> None:
    print(
        "\n"
        "======================================================================\n"
        "⚠️  TOKEN DO BOT AINDA NÃO CONFIGURADO NO ARQUIVO .env\n"
        "======================================================================\n"
        f"Edite o arquivo {ENV_FILE} e preencha TELEGRAM_BOT_TOKEN.\n"
        "======================================================================\n"
    )


def main() -> int:
    settings = load_settings()
    if not settings.is_token_configured:
        print_setup_instructions()
        return 1

    application = (
        ApplicationBuilder()
        .token(settings.bot_token)
        .post_init(post_init)
        .build()
    )
    application.bot_data["settings"] = settings
    application.bot_data["terms_store"] = TermsStore()

    register_handlers(application)

    logger.info("Iniciando escuta de mensagens do Telegram (Ctrl+C para parar)...")
    application.run_polling(drop_pending_updates=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
