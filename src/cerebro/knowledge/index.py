"""Índice da base de conhecimento: ingestão incremental e busca."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path

from cerebro.config import Settings
from cerebro.knowledge.chunking import split_text
from cerebro.knowledge.loaders import describe, iter_files, read_file
from cerebro.knowledge.search import BM25, tokenize

TYPE_LABEL = {"aula": "Aula", "nota": "Nota", "projeto": "Projeto"}


@dataclass
class Hit:
    tag: str
    score: float
    text: str
    meta: dict

    def source_label(self) -> str:
        m = self.meta
        if m.get("type") == "aula":
            parts = [m.get("fase", ""), m.get("submodulo", ""), m.get("title", "")]
            label = " › ".join(p for p in parts if p)
        elif m.get("type") == "projeto":
            label = f"{m.get('repo', '')} › {m.get('file', '').split('/', 1)[-1]}"
        else:
            label = m.get("file", "")
        if m.get("page"):
            label += f" (p. {m['page']})"
        return f"{TYPE_LABEL.get(m.get('type'), m.get('type', ''))}: {label}"


class KnowledgeBase:
    def __init__(self, settings: Settings):
        self.s = settings
        self.dir = settings.index_dir
        self.chunks: list[dict] = []
        self._bm25: BM25 | None = None

    # ------------------------------------------------------------------ ingestão
    @property
    def _chunks_path(self) -> Path:
        return self.dir / "chunks.jsonl"

    @property
    def _manifest_path(self) -> Path:
        return self.dir / "manifest.json"

    def load(self) -> KnowledgeBase:
        self.chunks = []
        if self._chunks_path.exists():
            with self._chunks_path.open(encoding="utf-8") as fh:
                self.chunks = [json.loads(line) for line in fh if line.strip()]
        self._bm25 = None
        return self

    def ingest(self, rebuild: bool = False, log=print) -> dict:
        """Lê as fontes do config. Só reprocessa arquivos novos ou alterados."""
        self.dir.mkdir(parents=True, exist_ok=True)
        manifest: dict = {}
        if not rebuild and self._manifest_path.exists():
            manifest = json.loads(self._manifest_path.read_text(encoding="utf-8"))
            self.load()
        else:
            self.chunks = []

        seen: set[str] = set()
        added = updated = 0
        t0 = time.time()
        for src in self.s.sources:
            root = self.s.resolve(src.path)
            for path in iter_files(root, src.include, src.exclude, src.type):
                key = f"{src.type}:{path.relative_to(root).as_posix()}"
                seen.add(key)
                stat = path.stat()
                sig = f"{stat.st_size}:{int(stat.st_mtime)}"
                if manifest.get(key, {}).get("sig") == sig:
                    continue
                meta = describe(path, root, src.type)
                meta["private"] = src.private
                new_chunks = []
                for page in read_file(path, meta):
                    for j, text in enumerate(split_text(page.text, self.s.chunking.chunk_chars,
                                                        self.s.chunking.overlap_chars)):
                        cid = hashlib.sha1(f"{key}|{page.meta.get('page', 0)}|{j}".encode()).hexdigest()[:12]
                        new_chunks.append({"id": cid, "key": key, "text": text, "meta": page.meta})
                if key in manifest:
                    updated += 1
                    self.chunks = [c for c in self.chunks if c["key"] != key]
                else:
                    added += 1
                self.chunks.extend(new_chunks)
                manifest[key] = {"sig": sig, "chunks": len(new_chunks)}
                log(f"  + {key} ({len(new_chunks)} trechos)")

        removed = [k for k in manifest if k not in seen]
        if removed:
            self.chunks = [c for c in self.chunks if c["key"] not in removed]
            for k in removed:
                manifest.pop(k)

        tmp = self._chunks_path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for c in self.chunks:
                fh.write(json.dumps(c, ensure_ascii=False) + "\n")
        tmp.replace(self._chunks_path)
        self._manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
        self._bm25 = None
        return {"novos": added, "atualizados": updated, "removidos": len(removed),
                "arquivos": len(manifest), "trechos": len(self.chunks), "segundos": round(time.time() - t0, 1)}

    # ------------------------------------------------------------------ busca
    def _index(self) -> BM25:
        if self._bm25 is None:
            if not self.chunks:
                self.load()
            docs = []
            for c in self.chunks:
                m = c["meta"]
                head = " ".join([m.get("title", ""), m.get("submodulo", ""), m.get("repo", "")])
                docs.append(tokenize(head + " " + head + " " + c["text"]))  # título pesa mais
            self._bm25 = BM25(docs)
        return self._bm25

    def search(self, query: str, k: int = 8, fase: str | None = None, tipo: str | None = None,
               max_per_file: int = 2) -> list[Hit]:
        """Busca BM25. Sem filtro de tipo, mistura aulas (~60%) e projetos/notas para não
        deixar um tipo dominar o resultado."""
        if not self.chunks:
            self.load()
        if not self.chunks:
            return []
        scores = self._index().scores(tokenize(query))
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)

        def pick(allowed_types: set[str] | None, limit: int, taken: set[int]) -> list[tuple[int, float]]:
            out, per_file, seen_text = [], {}, set()
            for i, score in ranked:
                if i in taken:
                    continue
                c = self.chunks[i]
                m = c["meta"]
                if allowed_types and m.get("type") not in allowed_types:
                    continue
                if fase and fase.lower() not in (m.get("fase", "") or "").lower():
                    continue
                if per_file.get(c["key"], 0) >= max_per_file:
                    continue
                sig = c["text"][:200]
                if sig in seen_text:
                    continue
                seen_text.add(sig)
                per_file[c["key"]] = per_file.get(c["key"], 0) + 1
                out.append((i, score))
                if len(out) >= limit:
                    break
            return out

        if tipo:
            chosen = pick({tipo}, k, set())
        else:
            n_aula = max(1, round(k * 0.6))
            chosen = pick({"aula"}, n_aula, set())
            chosen += pick({"projeto", "nota"}, k - len(chosen), {i for i, _ in chosen})
            if len(chosen) < k:  # completa com o que sobrar
                chosen += pick(None, k - len(chosen), {i for i, _ in chosen})
        chosen.sort(key=lambda x: x[1], reverse=True)
        return [Hit(tag=f"F{n}", score=round(sc, 2), text=self.chunks[i]["text"], meta=self.chunks[i]["meta"])
                for n, (i, sc) in enumerate(chosen, 1)]

    def stats(self) -> dict:
        if not self.chunks:
            self.load()
        out: dict = {"trechos": len(self.chunks), "por_tipo": {}, "aulas": {}}
        files: dict[str, set] = {}
        for c in self.chunks:
            m = c["meta"]
            out["por_tipo"][m["type"]] = out["por_tipo"].get(m["type"], 0) + 1
            if m["type"] == "aula":
                fase = m.get("fase") or "(sem fase)"
                sub = m.get("submodulo") or "(raiz)"
                files.setdefault(f"{fase}|{sub}", set()).add(m["file"])
        for key, fs in sorted(files.items()):
            fase, sub = key.split("|")
            out["aulas"].setdefault(fase, {})[sub] = len(fs)
        if self._manifest_path.exists():
            out["atualizado_em"] = time.strftime("%d/%m/%Y %H:%M",
                                                 time.localtime(self._manifest_path.stat().st_mtime))
        return out
