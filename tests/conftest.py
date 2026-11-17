import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def make_pdf(path: Path, pages: list[str]) -> None:
    """Gera um PDF simples com texto (sem dependências), uma string por página."""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>"]
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(len(pages)))
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>")
    font_id = 3 + 2 * len(pages)
    for i, text in enumerate(pages):
        lines = []
        for j, line in enumerate(text.split("\n")):
            safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            lines.append(f"BT /F1 11 Tf 40 {780 - 14 * j} Td ({safe}) Tj ET")
        stream = "\n".join(lines).encode("latin-1", "replace")
        objs.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                    f"/Resources << /Font << /F1 {font_id} 0 R >> >> /Contents {4 + 2 * i} 0 R >>")
        objs.append(f"<< /Length {len(stream)} >>\nstream\n{stream.decode('latin-1')}\nendstream")
    objs.append("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    out = b"%PDF-1.4\n"
    offsets = []
    for n, body in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{n} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    path.write_bytes(out)


@pytest.fixture()
def project(tmp_path: Path) -> Path:
    """Projeto mínimo em pasta temporária: config, padrões reais e uma base pequena."""
    root = tmp_path / "proj"
    root.mkdir()
    shutil.copy(ROOT / "config.yaml", root / "config.yaml")
    shutil.copytree(ROOT / "library", root / "library")
    aula = root / "data/aulas/fase3_cloud_mlops/03 - Pipeline de Treino"
    aula.mkdir(parents=True)
    filler = " ".join(["Conteúdo complementar da aula sobre pipelines de machine learning."] * 4)
    make_pdf(aula / "Aula 05 - Orquestracao com Airflow.pdf", [
        "Orquestracao de Pipelines com Airflow\nUma DAG do Airflow agenda o retreino do modelo.\n"
        "O operador executa tarefas de ingestao, treino e validacao.\n" + filler,
        "Quality gate: o modelo novo so e promovido se superar o atual.\n"
        "PDF exclusivo para Fulano de Tal - rm000000\nfulano@exemplo.com\n" + filler,
    ])
    (aula / "token secreto.txt").write_text("abc123 " * 50, encoding="utf-8")
    notas = root / "data/notas"
    notas.mkdir(parents=True)
    (notas / "kafka.md").write_text("# Kafka\n\nKafka recebe eventos em tempo real; consumidores calculam "
                                     "features em janela para o modelo de fraude.\n" * 3, encoding="utf-8")
    (root / "data/repos").mkdir(parents=True)
    return root


@pytest.fixture()
def settings(project: Path):
    from cerebro.config import load_settings

    return load_settings(project)


@pytest.fixture()
def pattern_data() -> dict:
    return json.loads((ROOT / "library/patterns/monitoramento_drift_credito.json").read_text(encoding="utf-8"))
