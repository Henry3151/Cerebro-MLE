import os
import time

from cerebro.knowledge import KnowledgeBase
from cerebro.knowledge.chunking import split_text
from cerebro.knowledge.loaders import clean_text
from cerebro.knowledge.search import BM25, tokenize


def test_split_text_respects_size_and_overlap():
    text = "\n\n".join(f"Parágrafo {i}. " + "palavra " * 60 for i in range(10))
    chunks = split_text(text, size=600, overlap=100)
    assert len(chunks) > 3
    assert all(len(c) <= 750 for c in chunks)


def test_tokenize_removes_accents_stopwords_and_plural():
    toks = tokenize("As orquestrações de pipelines com o Airflow")
    assert "airflow" in toks and "de" not in toks
    assert tokenize("orquestração")[0] == tokenize("orquestrações")[0]


def test_bm25_ranks_relevant_document_first():
    docs = [tokenize(t) for t in ["deploy na AWS com SageMaker", "drift de dados e PSI", "Airflow DAG de retreino"]]
    scores = BM25(docs).scores(tokenize("retreino com Airflow"))
    assert max(scores, key=scores.get) == 2


def test_clean_text_removes_watermark_and_emails():
    out = clean_text("Texto\nPDF exclusivo para Fulano - rm1\nfulano@x.com\nPágina 3 de 9\nfim")
    assert "Fulano" not in out and "@" not in out and "Página" not in out and "fim" in out


def test_ingest_search_and_incremental_updates(settings, project):
    kb = KnowledgeBase(settings)
    r = kb.ingest(log=lambda *_: None)
    assert r["arquivos"] == 2                      # PDF + nota; o arquivo "token" é ignorado
    assert not any("token" in c["key"] for c in kb.chunks)
    assert not any("rm000000" in c["text"] or "@" in c["text"] for c in kb.chunks)

    hits = kb.search("retreino Airflow", k=3)
    assert hits and hits[0].meta["type"] == "aula"
    assert hits[0].meta["fase"] == "fase3_cloud_mlops" and hits[0].meta["submodulo"].startswith("03")
    assert "p." in hits[0].source_label()

    assert kb.ingest(log=lambda *_: None)["novos"] == 0          # nada mudou

    nota = project / "data/notas/kafka.md"
    nota.write_text(nota.read_text(encoding="utf-8") + "\nNovo parágrafo sobre Flink.", encoding="utf-8")
    future = time.time() + 5
    os.utime(nota, (future, future))
    assert kb.ingest(log=lambda *_: None)["atualizados"] == 1

    nota.unlink()
    assert kb.ingest(log=lambda *_: None)["removidos"] == 1
    assert not kb.search("Kafka", tipo="nota")


def test_stats_groups_by_phase_and_submodule(settings):
    kb = KnowledgeBase(settings)
    kb.ingest(log=lambda *_: None)
    st = kb.stats()
    assert st["aulas"]["fase3_cloud_mlops"]["03 - Pipeline de Treino"] == 1
