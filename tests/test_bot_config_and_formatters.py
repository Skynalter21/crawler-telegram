from pathlib import Path
from app.config import load_settings
from app.formatters import (
    clean_store_url,
    format_brl,
    format_chat_id_message,
    format_crawler_promotion_message,
    format_sample_promotion_message,
    format_status_message,
    format_terms_list_message,
    select_best_offer_and_image,
)
from app.spell_corrector import correct_query_local
from app.terms_store import TermsStore


def test_spell_corrector_typos() -> None:
    assert correct_query_local("ayirfrier") == "air fryer"
    assert correct_query_local("airfrier mondial") == "air fryer mondial"
    assert correct_query_local("ifone 15 128gb") == "iphone 15 128gb"
    assert correct_query_local("sansung s23") == "samsung s23"
    assert correct_query_local("geladera frost") == "geladeira frost"
    assert correct_query_local("cerveija heinekem") == "cerveja heineken"
    assert correct_query_local("notebuk gamer") == "notebook gamer"
    assert correct_query_local("liquidficador") == "liquidificador"
    assert correct_query_local("criatina") == "creatina"


def test_load_and_save_settings(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "TELEGRAM_BOT_TOKEN=123456:ABCDEF\n"
        "TELEGRAM_CHAT_ID=-100987654321\n"
        "SCHEDULE_INTERVAL_MINUTES=30\n"
        "AUTO_SEND_ENABLED=true\n",
        encoding="utf-8",
    )

    settings = load_settings(env_path=env_file)
    assert settings.is_token_configured is True
    assert settings.chat_id == -100987654321
    assert settings.schedule_interval_minutes == 30
    assert settings.auto_send_enabled is True

    settings.save_to_env("SCHEDULE_INTERVAL_MINUTES", "15", env_path=env_file)
    reloaded = load_settings(env_path=env_file)
    assert reloaded.schedule_interval_minutes == 15


def test_terms_store_rotation_and_crud(tmp_path: Path) -> None:
    store = TermsStore(file_path=tmp_path / "terms.json")
    initial = store.list_terms()
    assert len(initial) == 3

    first = store.get_next_term()
    second = store.get_next_term()
    assert first == initial[0]
    assert second == initial[1]
    assert store.peek_next_term() == initial[2]

    added, updated = store.add_term("cerveja heineken")
    assert added is True
    assert "cerveja heineken" in updated

    added_dup, _ = store.add_term("CERVEJA HEINEKEN")
    assert added_dup is False

    removed, remaining = store.remove_term("1")
    assert removed == initial[0]
    assert initial[0] not in remaining


def test_formatters_output_valid_strings() -> None:
    assert format_brl(1999.9) == "R$ 1.999,90"
    assert format_brl(60.8, include_symbol=False) == "60,80"
    promo = format_sample_promotion_message(is_manual_test=True)
    assert "🔥" in promo
    assert "🎯" in promo

    clean_amz = clean_store_url(
        "https://www.amazon.com.br/Nintendo-Switch-2/dp/B0F3GWXLTS/ref=asc?tag=123&msclkid=abc"
    )
    assert clean_amz == "https://www.amazon.com.br/dp/B0F3GWXLTS"

    chat_msg = format_chat_id_message(-100123, "Grupo Amigos <Top>", "supergroup", -100123)
    assert "-100123" in chat_msg
    assert "&lt;Top&gt;" in chat_msg

    status_msg = format_status_message(
        -100123, 45, True, "06/11/2026 às 15:30:00", "http://localhost:8000", terms_count=3, next_term="ps5"
    )
    assert "45 min" in status_msg
    assert "🟢 Ativo" in status_msg
    assert "ps5" in status_msg

    terms_msg = format_terms_list_message(["ps5", "rtx 4060"], "rtx 4060")
    assert "rtx 4060" in terms_msg
    assert "próximo envio" in terms_msg


def test_console_filters_out_games_and_broken_bing_links() -> None:
    mock_data = {
        "query": "switch 2",
        "total": 4,
        "stores": ["KaBuM!", "Mercado Livre", "Amazon"],
        "results": [
            {
                "title": "Jogo The Legend Of Zelda Tears Of The Kingdom Edition Nintendo Switch 2",
                "price": 999.99,
                "store": "KaBuM!",
                "source": "bing_shopping",
                "url": "https://www.bing.com/shop/productpage?q=switch 2",
                "image": "https://th.bing.com/zelda.jpg",
                "is_used": False,
            },
            {
                "title": "Console Hibrida Nintendo Switch 2",
                "price": 3562.22,
                "store": "Mercado Livre",
                "source": "search_engine",
                "url": "https://www.mercadolivre.com.br/console-nintendo-switch-2/p/MLB2026260042",
                "image": "https://http2.mlstatic.com/switch2.jpg",
                "is_used": False,
            },
            {
                "title": "Console Nintendo Switch 2 - Modelo Internacional",
                "price": 3989.0,
                "store": "Amazon",
                "source": "amazon_br",
                "url": "https://www.amazon.com.br/dp/B0F3GWXLTS",
                "image": "https://m.media-amazon.com/switch2.jpg",
                "is_used": False,
            },
            {
                "title": "Console Nintendo Switch 2 Nacional",
                "price": 4499.0,
                "store": "KaBuM!",
                "source": "kabum",
                "url": "https://www.kabum.com.br/produto/999/switch-2",
                "image": "https://images.kabum.com.br/switch2.jpg",
                "is_used": False,
            },
        ],
    }

    best, img = select_best_offer_and_image(mock_data)
    assert best is not None
    assert "Jogo" not in best["title"]
    assert best["price"] == 3562.22
    assert best["store"] == "Mercado Livre"

    msg = format_crawler_promotion_message(mock_data, short_url="https://tinyurl.com/2cqm5zua")
    assert "🔥 <b>Console Hibrida Nintendo Switch 2</b>" in msg
    assert "R$ 3.562,22" in msg
    assert "https://tinyurl.com/2cqm5zua" in msg
    assert "link.bing" not in msg
