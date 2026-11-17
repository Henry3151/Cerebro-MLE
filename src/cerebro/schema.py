"""Estrutura de uma arquitetura (o que o LLM devolve) e a validação de consistência.

O LLM nunca escreve Mermaid. Ele devolve este JSON; o Python valida e desenha.
"""
from __future__ import annotations

import re
import unicodedata
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator


class Kind(str, Enum):
    datastore = "datastore"   # banco, tabela, bucket, fila persistida, registry
    process = "process"       # etapa de processamento / job / transformação
    decision = "decision"     # gate, validação, roteamento, política
    model = "model"           # treino, modelo, inferência
    service = "service"       # API, serviço, aplicação
    monitor = "monitor"       # métricas, alertas, dashboards, observabilidade
    external = "external"     # sistema externo, usuário, fonte de terceiros
    document = "document"     # relatório, documento, model card, runbook


KIND_HELP = {
    "datastore": "banco, tabela, bucket, data lake, registry",
    "process": "job, transformação, pipeline, etapa",
    "decision": "gate de qualidade, validação, política, roteamento",
    "model": "treino, modelo, inferência",
    "service": "API, aplicação, serviço",
    "monitor": "métricas, alertas, dashboards",
    "external": "usuário, sistema externo, fonte de terceiros",
    "document": "relatório, model card, runbook",
}

_KIND_ALIASES = {
    "database": "datastore", "db": "datastore", "storage": "datastore", "store": "datastore",
    "data": "datastore", "table": "datastore", "queue": "datastore", "registry": "datastore",
    "job": "process", "pipeline": "process", "step": "process", "transform": "process", "etl": "process",
    "gate": "decision", "check": "decision", "validation": "decision", "policy": "decision",
    "ml": "model", "training": "model", "inference": "model",
    "api": "service", "app": "service", "application": "service",
    "monitoring": "monitor", "alert": "monitor", "dashboard": "monitor", "observability": "monitor",
    "user": "external", "source": "external", "system": "external",
    "doc": "document", "report": "document",
}


def slugify(text: str) -> str:
    """'Feature Store (online)' -> 'feature_store_online'."""
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower()
    if not text:
        text = "x"
    if text[0].isdigit():
        text = f"n{text}"
    return text[:40]


class Stage(BaseModel):
    id: str = Field(description="identificador curto em snake_case")
    title: str = Field(description="nome da etapa, ex.: Qualidade, Modelo, Drift")


class Component(BaseModel):
    id: str = Field(description="identificador único em snake_case")
    label: str = Field(description="texto do bloco no mapa (curto)")
    kind: Kind
    stage: str = Field(description="id da etapa a que pertence")
    tools: list[str] = Field(default_factory=list, description="ferramentas sugeridas")

    @field_validator("kind", mode="before")
    @classmethod
    def _kind_alias(cls, v: Any) -> Any:
        if isinstance(v, str):
            k = v.strip().lower()
            return _KIND_ALIASES.get(k, k)
        return v


class Edge(BaseModel):
    source: str
    target: str
    label: str = ""
    dashed: bool = False


class RoadmapStep(BaseModel):
    title: str
    components: list[str] = Field(default_factory=list, description="ids dos componentes construídos neste passo")
    why: str = Field(default="", description="por que este passo vem agora")
    done_when: str = Field(default="", description="critério de pronto")
    sources: list[str] = Field(default_factory=list, description="etiquetas do contexto usadas, ex.: A2, P1")


class Architecture(BaseModel):
    title: str
    summary: str = ""
    stages: list[Stage]
    components: list[Component]
    edges: list[Edge]
    roadmap: list[RoadmapStep] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _normalize_ids(cls, data: Any) -> Any:
        """Converte todos os ids para snake_case e reescreve as referências a eles."""
        if not isinstance(data, dict):
            return data
        data = dict(data)
        stage_map: dict[str, str] = {}
        stages = []
        for st in data.get("stages") or []:
            if isinstance(st, dict):
                st = dict(st)
                raw = str(st.get("id") or st.get("title") or "etapa")
                st["id"] = stage_map.setdefault(raw, slugify(raw))
                stage_map.setdefault(str(st.get("title", raw)), st["id"])
                st.setdefault("title", raw)
            stages.append(st)
        data["stages"] = stages

        comp_map: dict[str, str] = {}
        comps = []
        for c in data.get("components") or []:
            if isinstance(c, dict):
                c = dict(c)
                raw = str(c.get("id") or c.get("label") or "componente")
                c["id"] = comp_map.setdefault(raw, slugify(raw))
                if c.get("label"):
                    comp_map.setdefault(str(c["label"]), c["id"])
                else:
                    c["label"] = raw
                if "stage" in c:
                    st_raw = str(c["stage"])
                    c["stage"] = stage_map.get(st_raw, slugify(st_raw))
                if isinstance(c.get("tools"), str):
                    c["tools"] = [t.strip() for t in c["tools"].split(",") if t.strip()]
            comps.append(c)
        data["components"] = comps

        def _ref(x: Any) -> Any:
            return comp_map.get(str(x), slugify(str(x))) if x is not None else x

        edges = []
        for e in data.get("edges") or []:
            if isinstance(e, dict):
                e = dict(e)
                e["source"] = _ref(e.get("source", e.get("from")))
                e["target"] = _ref(e.get("target", e.get("to")))
                e.pop("from", None)
                e.pop("to", None)
                if e.get("label") is None:
                    e["label"] = ""
            edges.append(e)
        data["edges"] = edges

        steps = []
        for s in data.get("roadmap") or []:
            if isinstance(s, dict):
                s = dict(s)
                s["components"] = [_ref(x) for x in (s.get("components") or [])]
            steps.append(s)
        data["roadmap"] = steps
        return data

    # ---- consultas úteis -------------------------------------------------
    def component(self, cid: str) -> Component | None:
        return next((c for c in self.components if c.id == cid), None)

    def components_in(self, stage_id: str) -> list[Component]:
        return [c for c in self.components if c.stage == stage_id]


class CheckResult(BaseModel):
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


LIMITS = {"min_components": 3, "max_components": 40, "max_stages": 8}


def check(arch: Architecture) -> CheckResult:
    """Regras de consistência que o Pydantic sozinho não garante."""
    r = CheckResult()
    stage_ids = [s.id for s in arch.stages]
    comp_ids = [c.id for c in arch.components]

    for kind, ids in (("etapa", stage_ids), ("componente", comp_ids)):
        dup = sorted({i for i in ids if ids.count(i) > 1})
        if dup:
            r.errors.append(f"ids de {kind} repetidos: {', '.join(dup)}")

    if not arch.stages:
        r.errors.append("a arquitetura precisa de pelo menos 1 etapa")
    if len(arch.stages) > LIMITS["max_stages"]:
        r.errors.append(f"etapas demais ({len(arch.stages)}); use no máximo {LIMITS['max_stages']}")
    n = len(arch.components)
    if n < LIMITS["min_components"]:
        r.errors.append(f"componentes de menos ({n}); use pelo menos {LIMITS['min_components']}")
    if n > LIMITS["max_components"]:
        r.errors.append(f"componentes demais ({n}); use no máximo {LIMITS['max_components']}")

    for c in arch.components:
        if c.stage not in stage_ids:
            r.errors.append(f"componente '{c.id}' aponta para etapa inexistente '{c.stage}'")
    for s in arch.stages:
        if not arch.components_in(s.id):
            r.warnings.append(f"etapa '{s.id}' não tem componentes")

    seen_edges = set()
    for e in arch.edges:
        for end in (e.source, e.target):
            if end not in comp_ids:
                r.errors.append(f"ligação {e.source} -> {e.target} usa componente inexistente '{end}'")
        if e.source == e.target:
            r.errors.append(f"ligação de '{e.source}' para ele mesmo")
        key = (e.source, e.target)
        if key in seen_edges:
            r.warnings.append(f"ligação repetida {e.source} -> {e.target}")
        seen_edges.add(key)

    linked = {e.source for e in arch.edges} | {e.target for e in arch.edges}
    isolated = [c.id for c in arch.components if c.id not in linked]
    if isolated and len(arch.components) > 1:
        r.warnings.append(f"componentes sem nenhuma ligação: {', '.join(isolated)}")

    for i, step in enumerate(arch.roadmap, 1):
        unknown = [x for x in step.components if x not in comp_ids]
        if unknown:
            r.warnings.append(f"passo {i} do roteiro cita componentes inexistentes: {', '.join(unknown)}")
    if not arch.roadmap:
        r.warnings.append("roteiro de desenvolvimento vazio")
    return r


def parse(data: dict[str, Any] | str) -> tuple[Architecture | None, CheckResult]:
    """Valida o JSON do LLM: estrutura (Pydantic) + consistência (check)."""
    import json

    result = CheckResult()
    if isinstance(data, str):
        try:
            data = json.loads(extract_json(data))
        except (ValueError, json.JSONDecodeError) as exc:
            result.errors.append(f"JSON inválido: {exc}")
            return None, result
    try:
        arch = Architecture.model_validate(data)
    except ValidationError as exc:
        for err in exc.errors()[:12]:
            loc = ".".join(str(x) for x in err["loc"])
            result.errors.append(f"campo '{loc}': {err['msg']}")
        return None, result
    return arch, check(arch)


def extract_json(text: str) -> str:
    """Tira cercas ```json e texto em volta, devolvendo o primeiro objeto JSON."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence:
        return fence.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("nenhum objeto JSON encontrado na resposta")
    return text[start : end + 1]


def autofix(arch: Architecture) -> tuple[Architecture, list[str]]:
    """Último recurso depois das tentativas do LLM: corrige o que dá para corrigir sem inventar."""
    notes: list[str] = []
    data = arch.model_dump()
    stage_ids = {s["id"] for s in data["stages"]}

    # ids de componentes repetidos: mantém o primeiro
    seen, comps = set(), []
    for c in data["components"]:
        if c["id"] in seen:
            notes.append(f"componente repetido '{c['id']}' removido")
            continue
        seen.add(c["id"])
        comps.append(c)
    data["components"] = comps

    orphan = [c for c in comps if c["stage"] not in stage_ids]
    if orphan:
        data["stages"].append({"id": "outros", "title": "Outros"})
        for c in orphan:
            c["stage"] = "outros"
        notes.append(f"{len(orphan)} componente(s) sem etapa válida movidos para 'Outros'")

    comp_ids = {c["id"] for c in comps}
    edges, seen_e = [], set()
    for e in data["edges"]:
        key = (e["source"], e["target"])
        if e["source"] not in comp_ids or e["target"] not in comp_ids or e["source"] == e["target"]:
            notes.append(f"ligação inválida {e['source']} -> {e['target']} removida")
            continue
        if key in seen_e:
            continue
        seen_e.add(key)
        edges.append(e)
    data["edges"] = edges

    for step in data["roadmap"]:
        step["components"] = [x for x in step["components"] if x in comp_ids]
    data["stages"] = [s for s in data["stages"] if any(c["stage"] == s["id"] for c in comps)]
    return Architecture.model_validate(data), notes


def llm_json_schema() -> dict[str, Any]:
    """Schema JSON sem $ref (mais fácil para modelos pequenos e para o modo 'format' do Ollama)."""
    schema = Architecture.model_json_schema()
    defs = schema.pop("$defs", {})

    def inline(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return inline(defs[node["$ref"].split("/")[-1]])
            return {k: inline(v) for k, v in node.items() if k not in ("title", "default")}
        if isinstance(node, list):
            return [inline(x) for x in node]
        return node

    return inline(schema)
