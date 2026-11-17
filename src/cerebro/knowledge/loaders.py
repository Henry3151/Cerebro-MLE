"""Leitura de arquivos da base: PDF (por página), Markdown/TXT e código, com metadados de origem."""
from __future__ import annotations

import fnmatch
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader

TEXT_SUFFIXES = {".md", ".txt", ".yaml", ".yml", ".toml", ".py", ".cfg", ".ini", ".json"}
SECRET_HINTS = ("token", "login", "senha", "password", "secret", ".env")


@dataclass
class Page:
    """Um pedaço "natural" do arquivo: uma página de PDF ou o arquivo de texto inteiro."""
    text: str
    meta: dict = field(default_factory=dict)


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


_WATERMARK = re.compile(r"PDF exclusivo para[^\n]*(\n\s*[^\s@]+@[^\s]+)?", re.IGNORECASE)
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def clean_text(text: str) -> str:
    text = nfc(text or "")
    text = _WATERMARK.sub(" ", text)                                  # marca d'água com nome/RM/e-mail do aluno
    text = _EMAIL.sub(" ", text)                                      # nenhum e-mail entra no índice
    text = re.sub(r"P[áa]gina\s+\d+\s+de\s+\d+", " ", text)          # cabeçalho dos PDFs das aulas
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)                       # hifenização no fim da linha
    text = re.sub(r"[ \t\u00a0]+", " ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def looks_secret(path: Path) -> bool:
    name = path.name.lower()
    return any(h in name for h in SECRET_HINTS)


def describe(path: Path, source_root: Path, source_type: str) -> dict:
    """Metadados a partir da posição do arquivo: fase / submódulo / aula para as aulas, repo para projetos."""
    rel = path.relative_to(source_root)
    parts = [nfc(p) for p in rel.parts]
    meta = {"type": source_type, "file": "/".join(parts), "title": nfc(path.stem)}
    if source_type == "aula":
        meta["fase"] = parts[0] if len(parts) > 1 else ""
        meta["submodulo"] = parts[1] if len(parts) > 2 else ""
    elif source_type == "projeto":
        meta["repo"] = parts[0] if len(parts) > 1 else ""
    return meta


def read_file(path: Path, meta: dict) -> list[Page]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        reader = PdfReader(str(path))
        pages = []
        for i, page in enumerate(reader.pages, 1):
            text = clean_text(page.extract_text() or "")
            if len(text) >= 150:
                pages.append(Page(text, {**meta, "page": i}))
        return pages
    if suffix in TEXT_SUFFIXES or path.name in ("Dockerfile", "Makefile"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        text = clean_text(text)
        return [Page(text, dict(meta))] if len(text) >= 40 else []
    return []


def _match(rel: str, patterns: list[str]) -> bool:
    name = rel.rsplit("/", 1)[-1]
    for p in patterns:
        if fnmatch.fnmatch(rel, p) or fnmatch.fnmatch(name, p):
            return True
        if p.startswith("**/") and fnmatch.fnmatch(rel, p[3:]):
            return True
    return False


def iter_files(root: Path, include: list[str], exclude: list[str], source_type: str):
    """Arquivos de uma fonte, respeitando include/exclude. Em repositórios, os padrões valem dentro de cada repo."""
    if not root.exists():
        return
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name.startswith(".") or path.name == "LEIA-ME.md":
            continue
        if looks_secret(path):
            continue
        rel = "/".join(path.relative_to(root).parts)
        inner = rel.split("/", 1)[1] if source_type == "projeto" and "/" in rel else rel
        if exclude and (_match(rel, exclude) or _match(inner, exclude)):
            continue
        if include and not (_match(rel, include) or _match(inner, include)):
            continue
        if path.stat().st_size > 30_000_000:
            continue
        yield path
