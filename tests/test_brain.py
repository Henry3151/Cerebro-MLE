import json
import sys
from pathlib import Path

from cerebro.brain import Brain, schema_text
from cerebro.cli import main as cli_main
from cerebro.patterns import PatternLibrary

ROOT = Path(__file__).resolve().parents[1]


def test_every_library_pattern_is_valid():
    lib = PatternLibrary(ROOT / "library/patterns").load()
    assert not lib.problems, lib.problems
    assert len(lib.patterns) >= 9


def test_pattern_suggestions_make_sense():
    lib = PatternLibrary(ROOT / "library/patterns").load()
    cases = {
        "detectar fraude em pagamentos em tempo real com kafka": "fraude_tempo_real_streaming",
        "monitorar drift de um modelo de crédito em produção": "monitoramento_drift_credito",
        "chatbot que responde perguntas sobre documentos internos com LLM": "rag_llm_assistente",
        "data lake com camadas bronze prata ouro e athena": "lakehouse_batch_medalhao",
        "recomendar produtos para usuários de e-commerce": "recomendacao_embeddings",
    }
    for problem, expected in cases.items():
        assert lib.suggest(problem, 1)[0][0].id == expected, problem


def test_generate_writes_outputs_and_resolves_sources(settings, pattern_data):
    b = Brain(settings)
    b.reindex()
    hits = b.search("Airflow retreino", k=2)
    arch = pattern_data["architecture"]
    arch["roadmap"][0]["sources"] = [hits[0].tag, "P-monitoramento_drift_credito"]
    r = b.generate(arch, "monitorar modelo de crédito")
    assert r["ok"], r
    md = Path(r["markdown"]).read_text(encoding="utf-8")
    assert hits[0].source_label() in md and "Padrão:" in md
    assert Path(r["html"]).exists() and Path(r["galeria"]).exists()
    assert "flowchart LR" in r["mermaid"]
    # as etiquetas sobrevivem a um novo processo (servidor reiniciado)
    assert hits[0].tag in json.loads((settings.index_dir / "fontes_citadas.json").read_text(encoding="utf-8"))


def test_generate_returns_errors_for_invalid_architecture(settings, pattern_data):
    arch = pattern_data["architecture"]
    arch["edges"].append({"source": "nao_existe", "target": "treino"})
    r = Brain(settings).generate(arch)
    assert not r["ok"] and any("nao_existe" in e for e in r["erros"])


def test_schema_text_mentions_kinds_and_limits():
    text = schema_text()
    assert "datastore" in text and "roadmap" in text and "Schema JSON" in text


def test_install_claude_merges_config_and_keeps_backup(tmp_path, project, monkeypatch):
    monkeypatch.chdir(project)
    cfg = tmp_path / "claude_desktop_config.json"
    cfg.write_text(json.dumps({"mcpServers": {"outro": {"command": "x"}}, "tema": "escuro"}), encoding="utf-8")
    assert cli_main(["install-claude", "--config", str(cfg)]) == 0
    data = json.loads(cfg.read_text(encoding="utf-8"))
    assert set(data["mcpServers"]) == {"outro", "cerebro-mle"} and data["tema"] == "escuro"
    entry = data["mcpServers"]["cerebro-mle"]
    assert entry["command"] == sys.executable and entry["env"]["CEREBRO_ROOT"] == str(project.resolve())
    assert cfg.with_suffix(".json.bak").exists()
