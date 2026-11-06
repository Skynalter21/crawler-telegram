import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


class SQLiteWatchlistRepository:
    """
    Repositório concreto de persistência em SQLite para alertas de preço (Watchlist).
    Cumpre o contrato WatchlistRepository (Dependency Inversion Principle).
    """

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or (Path(__file__).resolve().parents[2] / "watchlist.db")
        self.init_schema()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_schema(self) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS watchlist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    query TEXT NOT NULL,
                    product_title TEXT NOT NULL,
                    target_price REAL NOT NULL,
                    current_price REAL NOT NULL,
                    lowest_seen_price REAL NOT NULL,
                    store TEXT NOT NULL,
                    url TEXT NOT NULL,
                    image TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    last_checked_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def list_all(self) -> list[dict[str, Any]]:
        self.init_schema()
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM watchlist ORDER BY (current_price <= target_price) DESC, id DESC"
            ).fetchall()
        items: list[dict[str, Any]] = []
        for r in rows:
            d = dict(r)
            d["target_reached"] = d["current_price"] <= d["target_price"]
            items.append(d)
        return items

    def add(
        self,
        query: str,
        product_title: str,
        target_price: float,
        current_price: float,
        store: str,
        url: str,
        image: str = "",
    ) -> dict[str, Any]:
        self.init_schema()
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        lowest = min(current_price, target_price) if current_price <= 0 else current_price
        with self._get_conn() as conn:
            cur = conn.execute(
                """
                INSERT INTO watchlist (
                    query, product_title, target_price, current_price,
                    lowest_seen_price, store, url, image, created_at, last_checked_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    query.strip(),
                    product_title.strip(),
                    round(float(target_price), 2),
                    round(float(current_price), 2),
                    round(float(lowest), 2),
                    store.strip(),
                    url.strip(),
                    image.strip(),
                    now,
                    now,
                ),
            )
            conn.commit()
            item_id = cur.lastrowid
            row = conn.execute("SELECT * FROM watchlist WHERE id = ?", (item_id,)).fetchone()
        d = dict(row)
        d["target_reached"] = d["current_price"] <= d["target_price"]
        return d

    def update_price(
        self,
        item_id: int,
        new_price: float,
        store: str,
        url: str,
        product_title: str,
        image: str,
    ) -> None:
        self.init_schema()
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        with self._get_conn() as conn:
            row = conn.execute(
                "SELECT lowest_seen_price FROM watchlist WHERE id = ?", (item_id,)
            ).fetchone()
            if not row:
                return
            lowest_seen = min(float(row["lowest_seen_price"]), float(new_price))
            conn.execute(
                """
                UPDATE watchlist
                SET current_price = ?, lowest_seen_price = ?, store = ?,
                    url = ?, product_title = ?, image = ?, last_checked_at = ?
                WHERE id = ?
                """,
                (
                    round(float(new_price), 2),
                    round(lowest_seen, 2),
                    store,
                    url,
                    product_title,
                    image,
                    now,
                    item_id,
                ),
            )
            conn.commit()

    def delete(self, item_id: int) -> bool:
        self.init_schema()
        with self._get_conn() as conn:
            cur = conn.execute("DELETE FROM watchlist WHERE id = ?", (item_id,))
            conn.commit()
            return cur.rowcount > 0

