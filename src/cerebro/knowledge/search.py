"""Busca BM25 em português, sem dependências externas.

Por que BM25 e não embeddings: roda instantaneamente em qualquer PC, não precisa de modelo e funciona
muito bem com termos técnicos (Airflow, PSI, Feature Store). Quem interpreta a pergunta é o LLM,
que pode reformular a busca com outros termos.
"""
from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter

STOPWORDS = {"a", "à", "ao", "aos", "as", "às", "até", "com", "como", "da", "das", "de", "dela", "dele", "deles", "do", "dos", "e", "é", "ela", "elas", "ele", "eles", "em", "entre", "era", "essa", "esse", "esta", "este", "eu", "foi", "for", "há", "isso", "isto", "já", "la", "lhe", "mais", "mas", "me", "mesmo", "meu", "minha", "muito", "na", "nas", "nem", "no", "nos", "nós", "o", "os", "ou", "para", "pela", "pelas", "pelo", "pelos", "por", "qual", "quando", "que", "quem", "se", "sem", "ser", "seu", "seus", "sua", "suas", "são", "só", "também", "te", "tem", "um", "uma", "umas", "uns", "você", "vocês", "sobre", "ainda", "após", "cada", "onde", "pode", "podem", "deve", "devem", "forma", "vez", "the", "of", "and", "to", "in", "is", "on", "with", "by", "an", "be", "are", "this", "that", "it", "or", "from", "at"}

_TOKEN = re.compile(r"[a-z0-9][a-z0-9_+#.-]*[a-z0-9+#]|[a-z0-9]")


def _strip_accents(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def _stem(tok: str) -> str:
    """Radical leve para português: junta plural e algumas flexões comuns."""
    if len(tok) <= 4 or any(c.isdigit() for c in tok):
        return tok
    for suf in ("acoes", "coes", "mente", "idades", "idade", "ismos", "ismo", "istas", "ista",
                "ados", "adas", "ado", "ada", "oes", "aes", "ais", "eis", "res", "ns", "s"):
        if tok.endswith(suf) and len(tok) - len(suf) >= 4:
            if suf == "acoes":
                return tok[: -len(suf)] + "acao"
            if suf == "coes":
                return tok[: -len(suf)] + "cao"
            if suf in ("oes", "aes"):
                return tok[: -len(suf)] + "ao"
            if suf == "ais":
                return tok[: -len(suf)] + "al"
            if suf == "eis":
                return tok[: -len(suf)] + "el"
            if suf == "ns":
                return tok[: -len(suf)] + "m"
            return tok[: -len(suf)]
    return tok


def tokenize(text: str) -> list[str]:
    text = _strip_accents(text.lower())
    out = []
    for tok in _TOKEN.findall(text):
        tok = tok.strip(".-")
        if not tok or tok in STOPWORDS or len(tok) < 2:
            continue
        out.append(_stem(tok))
    return out


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.4, b: float = 0.75):
        self.k1, self.b = k1, b
        self.tf = [Counter(d) for d in docs]
        self.len = [len(d) for d in docs]
        self.avg = (sum(self.len) / len(self.len)) if self.len else 0.0
        df: Counter = Counter()
        for d in self.tf:
            df.update(d.keys())
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.postings: dict[str, list[int]] = {}
        for i, d in enumerate(self.tf):
            for t in d:
                self.postings.setdefault(t, []).append(i)

    def scores(self, query: list[str]) -> dict[int, float]:
        out: dict[int, float] = {}
        for t in set(query):
            idf = self.idf.get(t)
            if idf is None:
                continue
            for i in self.postings[t]:
                f = self.tf[i][t]
                denom = f + self.k1 * (1 - self.b + self.b * self.len[i] / (self.avg or 1))
                out[i] = out.get(i, 0.0) + idf * f * (self.k1 + 1) / denom
        return out
