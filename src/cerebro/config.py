"""Leitura do config.yaml com valores padrão e caminhos resolvidos a partir da raiz do projeto."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class RetrievalConfig(BaseModel):
    k_default: int = 8
    max_per_file: int = 2


class ChunkingConfig(BaseModel):
    chunk_chars: int = 1200
    overlap_chars: int = 200


class PathsConfig(BaseModel):
    index_dir: str = "data/index"
    outputs_dir: str = "outputs"
    patterns_dir: str = "library/patterns"


class SourceConfig(BaseModel):
    name: str
    path: str
    type: str  # aula | nota | projeto
    private: bool = False
    include: list[str] = Field(default_factory=lambda: ["*.pdf", "*.md", "*.txt"])
    exclude: list[str] = Field(default_factory=list)


class Settings(BaseModel):
    root: Path = Path(".")
    retrieval: RetrievalConfig = RetrievalConfig()
    chunking: ChunkingConfig = ChunkingConfig()
    paths: PathsConfig = PathsConfig()
    sources: list[SourceConfig] = Field(default_factory=list)
    repos: list[str] = Field(default_factory=list)

    def resolve(self, relative: str | Path) -> Path:
        p = Path(relative)
        return p if p.is_absolute() else (self.root / p)

    @property
    def index_dir(self) -> Path:
        return self.resolve(self.paths.index_dir)

    @property
    def outputs_dir(self) -> Path:
        return self.resolve(self.paths.outputs_dir)

    @property
    def patterns_dir(self) -> Path:
        return self.resolve(self.paths.patterns_dir)


def find_root(start: Path | None = None) -> Path:
    """Sobe a partir de `start` (ou do diretório atual) até achar um config.yaml."""
    env = os.environ.get("CEREBRO_ROOT")
    if env:
        return Path(env).resolve()
    cur = (start or Path.cwd()).resolve()
    for candidate in [cur, *cur.parents]:
        if (candidate / "config.yaml").exists():
            return candidate
    return cur


def load_settings(root: Path | None = None, overrides: dict[str, Any] | None = None) -> Settings:
    root = (root or find_root()).resolve()
    data: dict[str, Any] = {}
    cfg = root / "config.yaml"
    if cfg.exists():
        data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
    if overrides:
        for key, value in overrides.items():
            if isinstance(value, dict):
                data.setdefault(key, {}).update(value)
            else:
                data[key] = value
    data["root"] = root
    return Settings(**data)
