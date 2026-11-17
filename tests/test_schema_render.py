import copy

from cerebro.render import to_html, to_markdown, to_mermaid
from cerebro.schema import Kind, autofix, extract_json, llm_json_schema, parse, slugify

MINI = {
    "title": "Mini",
    "stages": [{"id": "Dados", "title": "Dados"}, {"id": "modelo", "title": "Modelo"}],
    "components": [
        {"id": "Fonte de Dados", "label": "Fonte \"bruta\"", "kind": "database", "stage": "Dados"},
        {"id": "end", "label": "Treino <XGBoost>", "kind": "model", "stage": "modelo", "tools": "XGBoost, MLflow"},
        {"id": "api", "label": "API", "kind": "api", "stage": "modelo"},
    ],
    "edges": [{"from": "Fonte de Dados", "to": "end", "label": "lote"},
              {"source": "end", "target": "api", "dashed": True}],
    "roadmap": [{"title": "Começar", "components": ["Fonte de Dados"], "sources": ["F-abc123"]}],
}


def test_ids_are_normalized_and_references_follow():
    arch, res = parse(MINI)
    assert res.ok, res.errors
    ids = [c.id for c in arch.components]
    assert ids == ["fonte_de_dados", "end", "api"]
    assert arch.edges[0].source == "fonte_de_dados" and arch.edges[0].target == "end"
    assert arch.components[0].kind is Kind.datastore and arch.components[2].kind is Kind.service
    assert arch.components[1].tools == ["XGBoost", "MLflow"]
    assert arch.roadmap[0].components == ["fonte_de_dados"]


def test_detects_dangling_edges_unknown_stage_and_duplicates():
    bad = copy.deepcopy(MINI)
    bad["edges"].append({"source": "api", "target": "fantasma"})
    bad["components"].append({"id": "api", "label": "API 2", "kind": "service", "stage": "inexistente"})
    _arch, res = parse(bad)
    assert not res.ok
    text = " ".join(res.errors)
    assert "fantasma" in text and "repetidos" in text and "inexistente" in text


def test_autofix_repairs_what_it_can():
    bad = copy.deepcopy(MINI)
    bad["edges"].append({"source": "api", "target": "fantasma"})
    bad["components"].append({"id": "monitor", "label": "Monitor", "kind": "monitor", "stage": "sumiu"})
    bad["edges"].append({"source": "api", "target": "monitor"})
    arch, _ = parse(bad)
    fixed, notes = autofix(arch)
    _, res = parse(fixed.model_dump())
    assert res.ok and notes
    assert any(s.id == "outros" for s in fixed.stages)


def test_invalid_json_text_is_reported():
    arch, res = parse("isto não é json")
    assert arch is None and not res.ok


def test_extract_json_from_fenced_block():
    assert extract_json('texto\n```json\n{"a": 1}\n```\nfim') == '{"a": 1}'


def test_slugify():
    assert slugify("Ação de Retreino (v2)") == "acao_de_retreino_v2"
    assert slugify("123 etapa").startswith("n123")


def test_mermaid_shapes_escaping_and_reserved_words():
    arch, _ = parse(MINI)
    mer = to_mermaid(arch)
    assert mer.startswith("flowchart LR")
    assert 'subgraph s_dados["1 · Dados"]' in mer
    assert 'c_fonte_de_dados[("Fonte #quot;bruta#quot;")]' in mer
    assert 'c_end[["Treino #lt;XGBoost#gt;"]]' in mer       # 'end' prefixado, '<>' escapados
    assert 'c_fonte_de_dados -->|"lote"| c_end' in mer
    assert "c_end -.-> c_api" in mer


def test_markdown_and_html_include_roadmap_and_sources():
    arch, _ = parse(MINI)
    md = to_markdown(arch, "problema x", {"F-abc123": "Aula: fase3 › Airflow (p. 2)"})
    assert "```mermaid" in md and "Roteiro de desenvolvimento" in md and "Aula: fase3 › Airflow (p. 2)" in md
    html = to_html(arch, "problema x", {"F-abc123": "Aula: fase3 › Airflow (p. 2)"})
    assert "<pre class=\"mermaid\">" in html and "mermaid.initialize" in html and "Fontes consultadas" in html


def test_schema_for_llm_has_no_refs():
    schema = llm_json_schema()
    assert "$ref" not in str(schema) and "components" in schema["properties"]
