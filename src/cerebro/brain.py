"""Camada de serviço do Cérebro: tudo o que o servidor MCP e a linha de comando fazem passa por aqui."""
from __future__ import annotations

import datetime as dt
import html
import json
import os
import sys
import webbrowser
from pathlib import Path
from typing import Any

from cerebro.config import Settings, load_settings
from cerebro.knowledge import Hit, KnowledgeBase
from cerebro.patterns import PatternLibrary
from cerebro.render import to_html, to_json, to_markdown, to_mermaid
from cerebro.schema import KIND_HELP, LIMITS, autofix, llm_json_schema, parse, slugify

RULES = f"""\
COMO MONTAR A ARQUITETURA (JSON)

Estrutura: title, summary, stages[], components[], edges[], roadmap[], assumptions[], risks[].

- stages: 3 a 6 etapas, na ordem do fluxo (ex.: Ingestão, Qualidade, Modelo, Serviço, Monitoramento).
  Cada etapa: {{"id": "snake_case", "title": "Nome"}}.
- components: 8 a 25 blocos. Cada um: {{"id", "label", "kind", "stage", "tools"}}.
  label curto (até ~40 caracteres); use "\\n" para quebrar linha.
  kind (define a forma no mapa):
{chr(10).join(f"    - {k}: {v}" for k, v in KIND_HELP.items())}
  tools: ferramentas concretas sugeridas (ex.: ["Airflow"], ["FastAPI", "Docker"]).
- edges: ligações {{"source", "target", "label", "dashed"}} usando ids de componentes.
  label curto e opcional (ex.: "inválido", "promove"). dashed=true para fluxos de controle,
  auditoria ou retroalimentação (ex.: retreino, configuração).
  Todo componente deve ter pelo menos uma ligação.
- roadmap: 5 a 10 passos na ORDEM em que devem ser construídos (dependências primeiro).
  Cada passo: {{"title", "components": [ids], "why", "done_when", "sources": [etiquetas]}}.
  done_when = critério de pronto verificável. sources = etiquetas devolvidas por
  buscar_conhecimento (ex.: "F-3fa2c1") ou "P-<id do padrão>" quando vier da biblioteca.
- assumptions: premissas que você assumiu. risks: riscos e pontos de atenção.

Boas práticas:
- Comece pelo padrão mais parecido da biblioteca e ADAPTE ao problema; não copie.
- Prefira ferramentas que aparecem nas aulas e nos projetos do Henrique.
- Inclua qualidade de dados, rastreabilidade (MLflow/registry) e monitoramento sempre que fizer sentido.
- Escreva tudo em português.
Limites: no máximo {LIMITS['max_stages']} etapas e {LIMITS['max_components']} componentes.
"""

WORKFLOW = """\
Você é o Cérebro MLE, arquiteto de Machine Learning Engineering do Henrique.
Para transformar um problema em mapa de arquitetura:
1. sugerir_padroes(problema) e, para o mais parecido, obter_padrao(id).
2. buscar_conhecimento 2 a 4 vezes, com termos específicos (ferramentas, conceitos, etapas),
   para fundamentar as escolhas nas aulas e nos projetos.
3. regras_da_arquitetura (uma vez por conversa) e monte o JSON.
4. gerar_mapa(arquitetura, problema). Se voltar com erros, corrija e chame de novo.
5. Responda com: resumo em 3 linhas, o roteiro numerado, as fontes mais importantes e o caminho do
   arquivo HTML gerado. Se alguma parte não estiver coberta pelo material, diga isso claramente.
"""


class Brain:
    def __init__(self, settings: Settings | None = None):
        self.s = settings or load_settings()
        self.kb = KnowledgeBase(self.s).load()
        self.lib = PatternLibrary(self.s.patterns_dir).load()
        self._sources_path = self.s.index_dir / "fontes_citadas.json"
        self.sources: dict[str, str] = {}
        if self._sources_path.exists():
            try:
                self.sources = json.loads(self._sources_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                self.sources = {}

    # ------------------------------------------------------------------ conhecimento
    def search(self, query: str, k: int | None = None, fase: str | None = None,
               tipo: str | None = None) -> list[Hit]:
        hits = self.kb.search(query, k or self.s.retrieval.k_default, fase=fase, tipo=tipo,
                              max_per_file=self.s.retrieval.max_per_file)
        for h in hits:
            h.tag = "F-" + _chunk_tag(h)
            self.sources[h.tag] = h.source_label()
        self._save_sources()
        return hits

    def search_text(self, query: str, k: int | None = None, fase: str | None = None,
                    tipo: str | None = None, max_chars: int = 900) -> str:
        hits = self.search(query, k, fase, tipo)
        if not hits:
            if not self.kb.chunks:
                return "A base está vazia. Rode 'cerebro ingest' (ou a ferramenta reindexar)."
            return f"Nada encontrado para: {query}. Tente outros termos (nome da ferramenta, sinônimos)."
        out = [f"{len(hits)} trechos para: {query}\n"]
        for h in hits:
            text = h.text if len(h.text) <= max_chars else h.text[:max_chars] + " […]"
            out.append(f"[{h.tag}] {h.source_label()}  (relevância {h.score})\n{text}\n")
        return "\n".join(out)

    def _save_sources(self) -> None:
        self._sources_path.parent.mkdir(parents=True, exist_ok=True)
        self._sources_path.write_text(json.dumps(self.sources, ensure_ascii=False, indent=1), encoding="utf-8")

    # ------------------------------------------------------------------ padrões
    def suggest_text(self, problem: str, k: int = 3) -> str:
        found = self.lib.suggest(problem, k)
        if not found:
            return "Nenhum padrão parecido na biblioteca. Monte a arquitetura a partir das regras e das aulas."
        lines = ["Padrões mais parecidos (use obter_padrao para ver o JSON completo):\n"]
        for p, score in found:
            lines.append(f"- {p.id} (relevância {score}): {p.name}\n  Quando usar: {p.when_to_use}\n"
                         f"  Origem: {p.origin}")
        return "\n".join(lines)

    def pattern_json(self, pid: str) -> str:
        p = self.lib.get(pid)
        if not p:
            ids = ", ".join(x.id for x in self.lib.patterns)
            return f"Padrão '{pid}' não existe. Disponíveis: {ids}"
        self.sources[f"P-{p.id}"] = f"Padrão: {p.name} ({p.origin})"
        self._save_sources()
        return json.dumps({"id": p.id, "nome": p.name, "origem": p.origin,
                           "architecture": p.architecture.model_dump(mode="json")}, ensure_ascii=False)

    # ------------------------------------------------------------------ mapa
    def generate(self, architecture: dict | str, problem: str = "", open_browser: bool = False,
                 allow_autofix: bool = False) -> dict[str, Any]:
        arch, result = parse(architecture)
        notes: list[str] = []
        if arch is not None and not result.ok and allow_autofix:
            arch, notes = autofix(arch)
            from cerebro.schema import check
            result = check(arch)
        if arch is None or not result.ok:
            return {"ok": False, "erros": result.errors, "avisos": result.warnings,
                    "dica": "Corrija os erros e chame gerar_mapa de novo com o JSON completo."}

        stamp = dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
        folder = self.s.outputs_dir / f"{stamp}_{slugify(arch.title)}"
        folder.mkdir(parents=True, exist_ok=True)
        sources = dict(self.sources)
        for p in self.lib.patterns:
            sources.setdefault(f"P-{p.id}", f"Padrão: {p.name} ({p.origin})")
        (folder / "arquitetura.json").write_text(to_json(arch), encoding="utf-8")
        (folder / "mapa.md").write_text(to_markdown(arch, problem, sources, notes), encoding="utf-8")
        html_path = folder / "mapa.html"
        html_path.write_text(to_html(arch, problem, sources), encoding="utf-8")
        if problem:
            (folder / "problema.txt").write_text(problem, encoding="utf-8")
        gallery = self.update_gallery()
        if open_browser:
            open_file(html_path)
        return {"ok": True, "html": str(html_path.resolve()), "markdown": str((folder / "mapa.md").resolve()),
                "galeria": str(gallery.resolve()), "avisos": result.warnings + notes,
                "mermaid": to_mermaid(arch)}

    def update_gallery(self) -> Path:
        out = self.s.outputs_dir
        out.mkdir(parents=True, exist_ok=True)
        rows = []
        for folder in sorted((p for p in out.iterdir() if p.is_dir()), reverse=True):
            j = folder / "arquitetura.json"
            if not j.exists():
                continue
            try:
                data = json.loads(j.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            problem = (folder / "problema.txt").read_text(encoding="utf-8") if (folder / "problema.txt").exists() else ""
            when = folder.name[:16].replace("_", " ")
            rows.append(f"<li><a href='{html.escape(folder.name)}/mapa.html'>{html.escape(data.get('title', folder.name))}"
                        f"</a><div class='m'>{html.escape(when)} · {len(data.get('components', []))} componentes</div>"
                        f"<div class='p'>{html.escape(problem[:220])}</div></li>")
        page = ("<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><title>Cérebro MLE · mapas</title>"
                "<style>body{background:#16181d;color:#e6e6e6;font:15px system-ui,Segoe UI,sans-serif;margin:0}"
                "main{max-width:900px;margin:0 auto;padding:24px 16px}a{color:#e8436d;font-weight:600;text-decoration:none}"
                "li{list-style:none;border-bottom:1px solid #3a404b;padding:12px 0}.m{color:#9aa3ad;font-size:13px}"
                ".p{margin-top:4px}ul{padding:0}</style></head><body><main><h1>Cérebro MLE · mapas gerados</h1>"
                f"<ul>{''.join(rows) or '<li>Nenhum mapa ainda.</li>'}</ul></main></body></html>")
        path = out / "index.html"
        path.write_text(page, encoding="utf-8")
        return path

    # ------------------------------------------------------------------ status
    def status_text(self) -> str:
        st = self.kb.stats()
        lines = [f"Base: {st['trechos']} trechos  ·  atualizada em {st.get('atualizado_em', '—')}",
                 "Por tipo: " + ", ".join(f"{k}={v}" for k, v in st["por_tipo"].items())]
        for fase, subs in st["aulas"].items():
            lines.append(f"\n{fase}")
            for sub, n in subs.items():
                lines.append(f"  - {sub}: {n} arquivo(s)")
        lines.append(f"\nPadrões na biblioteca: {len(self.lib.patterns)}")
        for p in self.lib.patterns:
            lines.append(f"  - {p.id}: {p.name}")
        if self.lib.problems:
            lines.append("Padrões com erro: " + ", ".join(self.lib.problems))
        return "\n".join(lines)

    def reindex(self, rebuild: bool = False) -> dict:
        result = self.kb.ingest(rebuild=rebuild, log=lambda *_: None)
        self.lib.load()
        return result


def _chunk_tag(h: Hit) -> str:
    import hashlib
    key = f"{h.meta.get('file')}|{h.meta.get('page', 0)}|{h.text[:80]}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:6]


def open_file(path: Path) -> None:
    try:
        if sys.platform.startswith("win"):
            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            webbrowser.open(path.resolve().as_uri())
    except OSError:
        pass


def schema_text() -> str:
    return RULES + "\nSchema JSON:\n" + json.dumps(llm_json_schema(), ensure_ascii=False)
