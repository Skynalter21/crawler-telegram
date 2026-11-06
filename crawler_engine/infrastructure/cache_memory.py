import time
from datetime import datetime
from typing import Any


class InMemorySearchCache:
    """
    Implementação em memória do repositório de cache de buscas com Time-To-Live (TTL).
    Cumpre o contrato SearchCacheRepository (DIP).
    """

    def __init__(self, ttl_seconds: float = 600.0) -> None:
        self.ttl_seconds = ttl_seconds
        self._store: dict[tuple[str, bool, bool], tuple[float, str, dict[str, Any]]] = {}

    def get(self, key: tuple[str, bool, bool]) -> tuple[str, dict[str, Any]] | None:
        if key not in self._store:
            return None
        saved_ts, saved_time_str, payload = self._store[key]
        if time.time() - saved_ts >= self.ttl_seconds:
            del self._store[key]
            return None
        return saved_time_str, payload

    def set(self, key: tuple[str, bool, bool], payload: dict[str, Any]) -> str:
        now_ts = time.time()
        now_str = datetime.now().strftime("%H:%M:%S")
        self._store[key] = (now_ts, now_str, payload)
        return now_str

