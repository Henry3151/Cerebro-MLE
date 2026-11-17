"""Biblioteca de arquiteturas modelo: padrões validados que servem de exemplo para novos mapas."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from cerebro.knowledge.search import BM25, tokenize
from cerebro.schema import Architecture, CheckResult, parse


@dataclass
class Pattern:
    id: str
    name: str
    when_to_use: str
    tags: list[str]
    origin: str
    phases: list[str]
    architecture: Architecture
    path: Path

    def card(self) -> dict:
        return {"id": self.id, "nome": self.name, "quando_usar": self.when_to_use, "tags": self.tags,
                "origem": self.origin, "fases": self.phases,
                "componentes": len(self.architecture.components)}


class PatternLibrary:
    def __init__(self, directory: Path):
        self.dir = directory
        self.patterns: list[Pattern] = []
        self.problems: dict[str, CheckResult] = {}
        self._bm25: BM25 | None = None

    def load(self) -> PatternLibrary:
        self.patterns, self.problems = [], {}
        for f in sorted(self.dir.glob("*.json")):
            data = json.loads(f.read_text(encoding="utf-8"))
            arch, result = parse(data.get("architecture", {}))
            if arch is None or not result.ok:
                self.problems[f.name] = result
                continue
            self.patterns.append(Pattern(
                id=data.get("id", f.stem), name=data.get("name", f.stem),
                when_to_use=data.get("when_to_use", ""), tags=data.get("tags", []),
                origin=data.get("origin", ""), phases=data.get("phases", []), architecture=arch, path=f,
            ))
        self._bm25 = None
        return self

    def get(self, pid: str) -> Pattern | None:
        return next((p for p in self.patterns if p.id == pid), None)

    def suggest(self, problem: str, k: int = 3) -> list[tuple[Pattern, float]]:
        if not self.patterns:
            return []
        if self._bm25 is None:
            docs = []
            for p in self.patterns:
                a = p.architecture
                text = " ".join([p.name, p.name, p.when_to_use, " ".join(p.tags) * 2, a.title, a.summary,
                                 " ".join(c.label + " " + " ".join(c.tools) for c in a.components)])
                docs.append(tokenize(text))
            self._bm25 = BM25(docs)
        scores = self._bm25.scores(tokenize(problem))
        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:k]
        return [(self.patterns[i], round(s, 2)) for i, s in ranked]

    def save(self, pid: str, name: str, when_to_use: str, tags: list[str], origin: str,
             arch: Architecture, phases: list[str] | None = None) -> Path:
        data = {"id": pid, "name": name, "when_to_use": when_to_use, "tags": tags, "origin": origin,
                "phases": phases or [], "architecture": arch.model_dump(mode="json")}
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self.dir / f"{pid}.json"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self.load()
        return path
