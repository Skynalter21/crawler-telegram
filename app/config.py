from dataclasses import dataclass
from pathlib import Path
import os
from dotenv import load_dotenv, set_key

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"


@dataclass
class BotSettings:
    """Configurações centralizadas do Bot do Telegram."""

    bot_token: str
    chat_id: int | None
    schedule_interval_minutes: int
    auto_send_enabled: bool
    crawler_api_url: str

    @property
    def is_token_configured(self) -> bool:
        return bool(
            self.bot_token
            and self.bot_token.strip()
            and self.bot_token.strip() != "SEU_TOKEN_AQUI"
        )

    def save_to_env(self, key: str, value: str, env_path: Path = ENV_FILE) -> None:
        """Persiste uma alteração de configuração diretamente no arquivo .env."""
        if not env_path.exists():
            env_path.write_text("", encoding="utf-8")
        set_key(str(env_path), key, str(value), quote_mode="never")


def _parse_chat_id(raw_value: str | None) -> int | None:
    if not raw_value or not raw_value.strip():
        return None
    try:
        return int(raw_value.strip())
    except ValueError:
        return None


def _parse_positive_int(raw_value: str | None, default: int = 60) -> int:
    if not raw_value or not raw_value.strip():
        return default
    try:
        val = int(raw_value.strip())
        return max(1, val)
    except ValueError:
        return default


def _parse_bool(raw_value: str | None, default: bool = True) -> bool:
    if raw_value is None or not raw_value.strip():
        return default
    return raw_value.strip().lower() in ("true", "1", "yes", "sim", "on")


def load_settings(env_path: Path = ENV_FILE) -> BotSettings:
    """Carrega as configurações do arquivo .env e variáveis de ambiente."""
    load_dotenv(dotenv_path=env_path, override=True)

    return BotSettings(
        bot_token=os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
        chat_id=_parse_chat_id(os.getenv("TELEGRAM_CHAT_ID")),
        schedule_interval_minutes=_parse_positive_int(
            os.getenv("TELEGRAM_SCHEDULE_INTERVAL")
            or os.getenv("SCHEDULE_INTERVAL_MINUTES"),
            default=60,
        ),
        auto_send_enabled=_parse_bool(os.getenv("AUTO_SEND_ENABLED"), default=True),
        crawler_api_url=os.getenv("CRAWLER_API_URL", "http://localhost:8000").rstrip("/"),
    )

