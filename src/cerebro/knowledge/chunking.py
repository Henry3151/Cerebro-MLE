"""Divisão de texto em trechos com sobreposição, respeitando parágrafos sempre que possível."""
from __future__ import annotations

import re


def split_text(text: str, size: int = 1200, overlap: int = 200) -> list[str]:
    text = text.strip()
    if len(text) <= size:
        return [text] if text else []
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    pieces: list[str] = []
    for p in paragraphs:  # parágrafos gigantes são cortados por frase
        if len(p) <= size:
            pieces.append(p)
            continue
        sentences = re.split(r"(?<=[.!?;:])\s+", p)
        buf = ""
        for s in sentences:
            while len(s) > size:  # frase sem pontuação maior que o trecho
                pieces.append(s[:size])
                s = s[size - overlap:]
            if len(buf) + len(s) + 1 > size and buf:
                pieces.append(buf)
                buf = ""
            buf = f"{buf} {s}".strip()
        if buf:
            pieces.append(buf)

    chunks: list[str] = []
    cur = ""
    for piece in pieces:
        if len(cur) + len(piece) + 2 > size and cur:
            chunks.append(cur)
            tail = cur[-overlap:] if overlap else ""
            cut = tail.find(" ")
            cur = (tail[cut + 1:] if cut != -1 else tail) + "\n\n" + piece
        else:
            cur = f"{cur}\n\n{piece}" if cur else piece
    if cur:
        chunks.append(cur)
    return [c.strip() for c in chunks if c.strip()]
