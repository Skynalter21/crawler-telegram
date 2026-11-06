import json
from pathlib import Path

from app.config import BASE_DIR

DEFAULT_TERMS_FILE = BASE_DIR / "data" / "monitored_terms.json"

DEFAULT_INITIAL_TERMS = [
    "ps5",
    "rtx 4060",
    "iphone 15 128gb",
]


class TermsStore:
    """
    Gerencia a lista de termos/produtos cadastrados pelo grupo para rotação
    nos envios automáticos periódicos.
    """

    def __init__(self, file_path: Path = DEFAULT_TERMS_FILE) -> None:
        self.file_path = file_path
        self._ensure_file()

    def _ensure_file(self) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.file_path.exists():
            self._save_data({"terms": list(DEFAULT_INITIAL_TERMS), "next_index": 0})

    def _load_data(self) -> dict:
        self._ensure_file()
        try:
            raw = json.loads(self.file_path.read_text(encoding="utf-8"))
            terms = [str(t).strip() for t in raw.get("terms", []) if str(t).strip()]
            next_index = int(raw.get("next_index", 0))
            return {"terms": terms, "next_index": next_index}
        except Exception:
            return {"terms": list(DEFAULT_INITIAL_TERMS), "next_index": 0}

    def _save_data(self, data: dict) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.file_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def list_terms(self) -> list[str]:
        return self._load_data()["terms"]

    def peek_next_term(self) -> str | None:
        data = self._load_data()
        terms = data["terms"]
        if not terms:
            return None
        idx = data["next_index"] % len(terms)
        return terms[idx]

    def get_next_term(self) -> str | None:
        """Retorna o próximo termo da fila e avança o ponteiro de rotação."""
        data = self._load_data()
        terms = data["terms"]
        if not terms:
            return None
        idx = data["next_index"] % len(terms)
        chosen = terms[idx]
        data["next_index"] = (idx + 1) % len(terms)
        self._save_data(data)
        return chosen

    def add_term(self, term: str) -> tuple[bool, list[str]]:
        """
        Adiciona um novo produto/termo na rotação (se ainda não existir).
        Retorna (adicionado_com_sucesso, lista_atualizada).
        """
        cleaned = " ".join(term.strip().split())
        if not cleaned:
            return False, self.list_terms()

        data = self._load_data()
        terms: list[str] = data["terms"]
        if any(t.lower() == cleaned.lower() for t in terms):
            return False, terms

        terms.append(cleaned)
        data["terms"] = terms
        self._save_data(data)
        return True, terms

    def remove_term(self, identifier: str) -> tuple[str | None, list[str]]:
        """
        Remove um termo pelo número na lista (1, 2, 3...) ou pelo nome exato.
        Retorna (termo_removido_ou_None, lista_atualizada).
        """
        cleaned = identifier.strip()
        data = self._load_data()
        terms: list[str] = data["terms"]
        if not terms or not cleaned:
            return None, terms

        removed: str | None = None
        if cleaned.isdigit():
            pos = int(cleaned) - 1
            if 0 <= pos < len(terms):
                removed = terms.pop(pos)
        else:
            for i, existing in enumerate(terms):
                if existing.lower() == cleaned.lower():
                    removed = terms.pop(i)
                    break

        if removed is not None:
            data["terms"] = terms
            data["next_index"] = 0 if not terms else (data["next_index"] % len(terms))
            self._save_data(data)

        return removed, terms

