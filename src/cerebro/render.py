"""Transforma uma Architecture em Mermaid, Markdown e HTML autocontido.

O desenho é 100% determinístico: a mesma arquitetura gera sempre o mesmo diagrama válido.
"""
from __future__ import annotations

import html
import json
import re
from importlib import resources

from cerebro.schema import Architecture, Kind

# Formas do Mermaid por tipo de componente (abre, fecha)
SHAPES: dict[Kind, tuple[str, str]] = {
    Kind.datastore: ('[("', '")]'),
    Kind.process: ('["', '"]'),
    Kind.decision: ('{"', '"}'),
    Kind.model: ('[["', '"]]'),
    Kind.service: ('("', '")'),
    Kind.monitor: ('{{"', '"}}'),
    Kind.external: ('(["', '"])'),
    Kind.document: ('[/"', '"/]'),
}

KIND_LEGEND = {
    Kind.datastore: "dados / armazenamento",
    Kind.process: "processamento",
    Kind.decision: "gate / decisão",
    Kind.model: "modelo",
    Kind.service: "serviço / API",
    Kind.monitor: "monitoramento",
    Kind.external: "externo",
    Kind.document: "documento",
}


def _node_id(cid: str) -> str:
    # prefixo evita colisão com palavras reservadas do Mermaid (end, graph, style...)
    return f"c_{cid}"


def _stage_id(sid: str) -> str:
    return f"s_{sid}"


def _text(label: str, max_len: int = 80) -> str:
    """Escapa o texto para dentro de aspas no Mermaid; '\\n' vira quebra de linha."""
    label = (label or "").strip()
    if len(label) > max_len:
        label = label[: max_len - 1] + "…"
    label = label.replace('"', "#quot;").replace("<", "#lt;").replace(">", "#gt;")
    label = re.sub(r"\s*\\n\s*|\s*\n\s*", "<br/>", label)
    return label


def to_mermaid(arch: Architecture, direction: str = "LR", show_tools: bool = False) -> str:
    lines = [f"flowchart {direction}"]
    for i, st in enumerate(arch.stages, 1):
        comps = arch.components_in(st.id)
        if not comps:
            continue
        lines.append(f'    subgraph {_stage_id(st.id)}["{i} · {_text(st.title, 50)}"]')
        for c in comps:
            label = c.label
            if show_tools and c.tools:
                label = f"{label}\\n{', '.join(c.tools[:3])}"
            open_, close = SHAPES[c.kind]
            lines.append(f"        {_node_id(c.id)}{open_}{_text(label)}{close}")
        lines.append("    end")
    for e in arch.edges:
        arrow = "-.->" if e.dashed else "-->"
        src, dst = _node_id(e.source), _node_id(e.target)
        if e.label:
            lines.append(f'    {src} {arrow}|"{_text(e.label, 40)}"| {dst}')
        else:
            lines.append(f"    {src} {arrow} {dst}")
    return "\n".join(lines)


def _source_lines(arch: Architecture, sources: dict[str, str] | None) -> list[str]:
    if not sources:
        return []
    used = []
    for step in arch.roadmap:
        for tag in step.sources:
            if tag in sources and tag not in used:
                used.append(tag)
    return [f"- **[{tag}]** {sources[tag]}" for tag in used]


def to_markdown(arch: Architecture, problem: str = "", sources: dict[str, str] | None = None,
                notes: list[str] | None = None) -> str:
    out = [f"# {arch.title}", ""]
    if problem:
        out += ["**Problema:** " + problem.strip(), ""]
    if arch.summary:
        out += [arch.summary.strip(), ""]
    out += ["## Mapa da arquitetura", "", "```mermaid", to_mermaid(arch), "```", ""]

    out += ["## Componentes", "", "| Etapa | Componente | Tipo | Ferramentas sugeridas |", "|---|---|---|---|"]
    for st in arch.stages:
        for c in arch.components_in(st.id):
            out.append(f"| {st.title} | {c.label.replace(chr(10), ' ')} | {KIND_LEGEND[c.kind]} | "
                       f"{', '.join(c.tools) or '—'} |")
    out.append("")

    if arch.roadmap:
        out += ["## Roteiro de desenvolvimento", ""]
        for i, step in enumerate(arch.roadmap, 1):
            labels = [arch.component(x).label for x in step.components if arch.component(x)]
            tags = f" `{' '.join('[' + t + ']' for t in step.sources)}`" if step.sources else ""
            out.append(f"{i}. **{step.title}**{tags}")
            if labels:
                out.append(f"    - Constrói: {', '.join(labels)}")
            if step.why:
                out.append(f"    - Por quê agora: {step.why}")
            if step.done_when:
                out.append(f"    - Pronto quando: {step.done_when}")
        out.append("")

    if arch.assumptions:
        out += ["## Premissas", ""] + [f"- {a}" for a in arch.assumptions] + [""]
    if arch.risks:
        out += ["## Riscos e pontos de atenção", ""] + [f"- {r}" for r in arch.risks] + [""]
    src = _source_lines(arch, sources)
    if src:
        out += ["## Fontes consultadas", ""] + src + [""]
    if notes:
        out += ["## Ajustes automáticos", ""] + [f"- {n}" for n in notes] + [""]
    return "\n".join(out)


def _mermaid_js() -> str:
    try:
        return resources.files("cerebro.assets").joinpath("mermaid.min.js").read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError):
        return ""


_HTML = """<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root {{ --bg:#16181d; --panel:#1f232b; --text:#e6e6e6; --muted:#9aa3ad; --line:#3a404b; --accent:#e8436d; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--text); font:15px/1.55 system-ui,Segoe UI,Roboto,sans-serif; }}
main {{ max-width:1400px; margin:0 auto; padding:24px 16px 48px; }}
h1 {{ font-size:24px; margin:0 0 4px; }} h2 {{ font-size:18px; margin:28px 0 10px; border-bottom:1px solid var(--line); padding-bottom:6px; }}
.muted {{ color:var(--muted); }}
.diagram {{ background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:16px; overflow:auto; }}
table {{ border-collapse:collapse; width:100%; font-size:14px; }}
th,td {{ border-bottom:1px solid var(--line); text-align:left; padding:6px 8px; vertical-align:top; }}
ol li {{ margin-bottom:10px; }} .tag {{ color:var(--accent); font-size:12px; }}
</style></head><body><main>
<h1>{title}</h1>
<p class="muted">{problem}</p>
<p>{summary}</p>
<h2>Mapa da arquitetura</h2>
<div class="diagram"><pre class="mermaid">{mermaid}</pre></div>
<h2>Roteiro de desenvolvimento</h2>
<ol>{roadmap}</ol>
<h2>Componentes</h2>
<table><tr><th>Etapa</th><th>Componente</th><th>Tipo</th><th>Ferramentas</th></tr>{components}</table>
{extras}
</main>
{script}
<script>mermaid.initialize({{ startOnLoad:true, theme:'dark', securityLevel:'strict',
 flowchart:{{ curve:'basis', htmlLabels:true }} }});</script>
</body></html>"""


def to_html(arch: Architecture, problem: str = "", sources: dict[str, str] | None = None) -> str:
    e = html.escape
    roadmap = []
    for step in arch.roadmap:
        labels = [arch.component(x).label for x in step.components if arch.component(x)]
        tags = " ".join(f"[{t}]" for t in step.sources)
        parts = [f"<b>{e(step.title)}</b> <span class='tag'>{e(tags)}</span>"]
        if labels:
            parts.append(f"<div class='muted'>Constrói: {e(', '.join(labels))}</div>")
        if step.why:
            parts.append(f"<div>Por quê agora: {e(step.why)}</div>")
        if step.done_when:
            parts.append(f"<div>Pronto quando: {e(step.done_when)}</div>")
        roadmap.append("<li>" + "".join(parts) + "</li>")
    comps = []
    for st in arch.stages:
        for c in arch.components_in(st.id):
            comps.append(f"<tr><td>{e(st.title)}</td><td>{e(c.label)}</td><td>{e(KIND_LEGEND[c.kind])}</td>"
                         f"<td>{e(', '.join(c.tools) or '—')}</td></tr>")
    extras = []
    if arch.assumptions:
        extras.append("<h2>Premissas</h2><ul>" + "".join(f"<li>{e(a)}</li>" for a in arch.assumptions) + "</ul>")
    if arch.risks:
        extras.append("<h2>Riscos e pontos de atenção</h2><ul>"
                      + "".join(f"<li>{e(r)}</li>" for r in arch.risks) + "</ul>")
    src = _source_lines(arch, sources)
    if src:
        items = [re.sub(r"\*\*(.+?)\*\*", r"\1", s[2:]) for s in src]
        extras.append("<h2>Fontes consultadas</h2><ul>" + "".join(f"<li>{e(i)}</li>" for i in items) + "</ul>")
    js = _mermaid_js()
    script = (f"<script>{js}</script>" if js else
              '<script src="https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js"></script>')
    return _HTML.format(
        title=e(arch.title), problem=e(problem), summary=e(arch.summary), mermaid=e(to_mermaid(arch)),
        roadmap="".join(roadmap), components="".join(comps), extras="".join(extras), script=script,
    )


def to_json(arch: Architecture) -> str:
    return json.dumps(arch.model_dump(mode="json"), ensure_ascii=False, indent=2)
