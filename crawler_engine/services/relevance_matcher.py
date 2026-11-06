import re
from crawler_engine.domain.models import MatchEvaluation, SearchCriteria
from crawler_engine.utils.text_normalizer import (
    expand_synonyms,
    fuzzy_similarity,
    normalize_text,
    stem_word,
    tokenize,
)

DEFAULT_STOP_WORDS = {
    "de", "da", "do", "das", "dos", "para", "com", "sem",
    "em", "no", "na", "nos", "nas", "o", "a", "os", "as", "e", "um", "uma",
}

DEFAULT_ACCESSORY_KEYWORDS = {
    "controle", "dualsense", "capa", "capinha", "pelicula", "case", "estojo",
    "suporte", "adesivo", "skin", "cabo", "fonte", "carregador", "base",
    "cooler", "chaveiro", "mousepad", "almofada", "parafuso", "peca",
    "reposicao", "adaptador", "conversor", "painel", "rack", "estante",
    "home", "bancada", "bolsa", "mochila", "maleta", "protetor", "filtro",
    "cabide", "decoracao", "enfeite", "poster", "quadro", "boneco",
    "camiseta", "caneca", "livro", "manual", "caixa", "embalagem",
    "pulseira", "alca", "aro", "lente", "tampa", "botoes", "gatilho",
    "portal", "reprodutor", "vr", "vr2", "camera", "headset", "volante",
    "pickguard", "escudo", "encordoamento", "tarraxa", "miniatura",
    "jogo", "jogos", "game", "games", "midia", "dlc", "gift", "card",
    "cartao", "assinatura", "joycon", "dock", "grip", "troco", "procuro",
    "compro", "aluguel", "locacao", "conta",
}

DEFAULT_USED_KEYWORDS = {
    "usado", "usada", "seminovo", "seminova", "recondicionado",
    "recondicionada", "vitrine", "reembalado", "defeito",
}

DEFAULT_VARIANT_MODIFIERS = {
    "pro", "max", "plus", "ultra", "ti", "super", "fe", "lite", "mini", "se",
}


class RelevanceProductMatcher:
    """
    Serviço dedicado exclusivamente à análise semântica e filtragem de relevância
    dos títulos dos produtos em relação ao termo buscado (SRP).
    """

    def __init__(
        self,
        stop_words: set[str] | None = None,
        accessory_keywords: set[str] | None = None,
        used_keywords: set[str] | None = None,
        variant_modifiers: set[str] | None = None,
    ) -> None:
        self.stop_words = stop_words or DEFAULT_STOP_WORDS
        self.accessory_keywords = accessory_keywords or DEFAULT_ACCESSORY_KEYWORDS
        self.used_keywords = used_keywords or DEFAULT_USED_KEYWORDS
        self.variant_modifiers = variant_modifiers or DEFAULT_VARIANT_MODIFIERS

    def evaluate(self, title: str, criteria: SearchCriteria) -> MatchEvaluation:
        norm_title = normalize_text(title)
        title_tokens = expand_synonyms(tokenize(title))
        query_tokens = expand_synonyms(tokenize(criteria.query))

        title_stems = {stem_word(t) for t in title_tokens}
        query_word_set = set(query_tokens)

        meaningful_tokens = [
            t for t in query_tokens if (len(t) >= 2 or t.isdigit()) and t not in self.stop_words
        ]
        if not meaningful_tokens:
            return MatchEvaluation(False, 0, False)

        # 1. Detecta se o título indica produto usado/seminovo/recondicionado
        has_used_kw = bool(set(title_tokens) & self.used_keywords) or (
            "semi" in title_tokens and "novo" in title_tokens
        )
        if not criteria.include_used and not (query_word_set & self.used_keywords):
            if has_used_kw:
                return MatchEvaluation(False, 0, False, True)

        # 2. Filtra acessórios não solicitados na busca (ignorando brindes listados após "+")
        unwanted_accessories = self.accessory_keywords - query_word_set
        main_title_part = re.split(r"\s+\+\s+", norm_title)[0]
        main_tokens = expand_synonyms(tokenize(main_title_part))
        if set(main_tokens) & unwanted_accessories:
            return MatchEvaluation(False, 0, False)

        # 3. Bloqueia anúncios de compatibilidade ("para <termo>") quando não há "para" na busca
        expanded_title_str = " ".join(title_tokens)
        if "para" not in query_word_set:
            first_token = meaningful_tokens[0]
            compat_pattern = rf"\b(para|compativel|p)\s+(?:\w+\s+){{0,2}}{re.escape(first_token)}\b"
            if re.search(compat_pattern, norm_title) or re.search(compat_pattern, expanded_title_str):
                return MatchEvaluation(False, 0, False)

        # 4. Verifica conflito de voltagem explícita (110V/127V vs 220V)
        title_token_set = set(title_tokens)
        if "220v" in query_word_set and ("110v" in title_token_set or "127v" in title_token_set) and "220v" not in title_token_set and "bivolt" not in title_token_set:
            return MatchEvaluation(False, 0, False)
        if ("110v" in query_word_set or "127v" in query_word_set) and "220v" in title_token_set and "110v" not in title_token_set and "127v" not in title_token_set and "bivolt" not in title_token_set:
            return MatchEvaluation(False, 0, False)

        # 5. Verifica presença dos tokens relevantes
        # Para buscas curtas (<= 5 termos), exige 100% dos termos.
        # Para buscas longas copiadas de títulos (>= 6 termos com especificações como 60W, 4,5L),
        # exige o termo principal + pelo menos 70% dos tokens.
        matched_count = 0
        for idx, token in enumerate(meaningful_tokens):
            stem = stem_word(token)
            token_found = (
                token in title_tokens
                or stem in title_stems
                or (token == "airfryer" and "fritadeira" in title_tokens)
                or (len(token) >= 5 and any(w.startswith(stem) for w in title_tokens))
                or (
                    len(token) >= 4
                    and not any(ch.isdigit() for ch in token)
                    and any(
                        not any(ch.isdigit() for ch in w) and fuzzy_similarity(token, w) >= 0.78
                        for w in title_tokens
                    )
                )
            )
            if token_found:
                matched_count += 1
            elif idx == 0 or len(meaningful_tokens) <= 5:
                return MatchEvaluation(False, 0, False)

        match_ratio = matched_count / len(meaningful_tokens)
        if match_ratio < 0.65:
            return MatchEvaluation(False, 0, False)

        # 6. Adjacência de modelos numéricos e bloqueio de anúncios multi-SKU
        for i in range(len(meaningful_tokens) - 1):
            t1, t2 = meaningful_tokens[i], meaningful_tokens[i + 1]
            if t1.isdigit() or t2.isdigit():
                pos1 = [idx for idx, w in enumerate(title_tokens) if stem_word(w) == stem_word(t1)]
                pos2 = [idx for idx, w in enumerate(title_tokens) if stem_word(w) == stem_word(t2)]
                if not pos1 or not pos2:
                    if len(meaningful_tokens) <= 5:
                        return MatchEvaluation(False, 0, False)
                    continue
                min_dist = min(abs(p1 - p2) for p1 in pos1 for p2 in pos2)
                if min_dist > 2:
                    return MatchEvaluation(False, 0, False)

                if not t1.isdigit() and t2.isdigit():
                    for p in pos1:
                        if p + 1 < len(title_tokens):
                            next_w = title_tokens[p + 1]
                            if next_w.isdigit() and next_w != t2:
                                return MatchEvaluation(False, 0, False)

        # 7. Verifica variantes de modelo (Pro, Max, Ti, Plus, FE, Lite)
        unrequested_variants = self.variant_modifiers - query_word_set
        has_unrequested_variant = bool(set(title_tokens) & unrequested_variants)
        is_exact_model = not has_unrequested_variant

        # 8. Pontuação de relevância (0 a 100)
        score = int(50 + (match_ratio * 25))
        clean_phrase = " ".join(stem_word(t) for t in meaningful_tokens)
        clean_title_phrase = " ".join(stem_word(t) for t in title_tokens)
        if clean_phrase in clean_title_phrase:
            score += 15

        first_stem = stem_word(meaningful_tokens[0])
        first_positions = [idx for idx, w in enumerate(title_tokens) if stem_word(w) == first_stem]
        if first_positions and first_positions[0] <= 2:
            score += 15
        elif first_positions and first_positions[0] > 6:
            score -= 25

        if has_unrequested_variant:
            score -= 15

        clamped_score = max(0, min(100, score))
        return MatchEvaluation(clamped_score >= 50, clamped_score, is_exact_model, has_used_kw)

