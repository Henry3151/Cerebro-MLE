"""Servidor MCP do Cérebro MLE para assistentes de IA compatíveis.

O LLM do assistente (com a assinatura do usuário) faz o raciocínio; o Cérebro guarda o conhecimento,
valida a arquitetura e desenha o mapa. Nenhuma API paga é usada.
"""
from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from cerebro.brain import RULES, WORKFLOW, Brain, schema_text

mcp = FastMCP("cerebro-mle", instructions=WORKFLOW)
_brain: Brain | None = None


def brain() -> Brain:
    global _brain
    if _brain is None:
        _brain = Brain()
    return _brain


@mcp.tool()
def buscar_conhecimento(consulta: str, quantidade: int = 8, fase: str = "", tipo: str = "") -> str:
    """Busca trechos nas aulas da pós (por fase e submódulo), nas notas e nos repositórios do Henrique.

    Use termos específicos: nomes de ferramentas, conceitos e etapas (ex.: "Airflow retreino DAG",
    "PSI drift monitoramento", "deploy SageMaker ECR"). Faça várias buscas curtas em vez de uma longa.
    Cada trecho vem com uma etiqueta (ex.: F-3fa2c1) para citar nas fontes do roteiro.

    Args:
        consulta: termos de busca.
        quantidade: número de trechos (padrão 8, máximo 15).
        fase: filtra por fase, ex.: "fase3" ou "fase2_big_data". Vazio = todas.
        tipo: "aula", "projeto" ou "nota". Vazio = mistura aulas e projetos.
    """
    return brain().search_text(consulta, min(max(quantidade, 1), 15), fase or None, tipo or None)


@mcp.tool()
def sugerir_padroes(problema: str, quantidade: int = 3) -> str:
    """Sugere as arquiteturas modelo da biblioteca mais parecidas com o problema descrito."""
    return brain().suggest_text(problema, quantidade)


@mcp.tool()
def obter_padrao(id_padrao: str) -> str:
    """Devolve o JSON completo de uma arquitetura modelo da biblioteca, para servir de exemplo."""
    return brain().pattern_json(id_padrao)


@mcp.tool()
def regras_da_arquitetura() -> str:
    """Regras e schema JSON que a arquitetura deve seguir para gerar_mapa aceitar. Leia antes de montar o JSON."""
    return schema_text()


@mcp.tool()
def gerar_mapa(arquitetura: dict[str, Any], problema: str = "", abrir_no_navegador: bool = True) -> str:
    """Valida a arquitetura, desenha o mapa (Mermaid) e salva HTML, Markdown e JSON na pasta outputs.

    Se houver erros, devolve a lista para você corrigir e chamar de novo com o JSON completo.

    Args:
        arquitetura: objeto JSON no formato descrito em regras_da_arquitetura.
        problema: o problema original do usuário, para registro.
        abrir_no_navegador: abre o mapa no navegador do computador quando der certo.
    """
    result = brain().generate(arquitetura, problema, open_browser=abrir_no_navegador)
    return json.dumps(result, ensure_ascii=False, indent=1)


@mcp.tool()
def salvar_como_padrao(arquitetura: dict[str, Any], id_padrao: str, nome: str, quando_usar: str,
                       tags: list[str], origem: str = "autoral") -> str:
    """Guarda uma arquitetura aprovada na biblioteca de padrões, para ser reaproveitada no futuro.
    Só use quando o Henrique pedir explicitamente."""
    from cerebro.schema import parse, slugify

    arch, result = parse(arquitetura)
    if arch is None or not result.ok:
        return json.dumps({"ok": False, "erros": result.errors}, ensure_ascii=False)
    path = brain().lib.save(slugify(id_padrao), nome, quando_usar, tags, origem, arch)
    return json.dumps({"ok": True, "arquivo": str(path)}, ensure_ascii=False)


@mcp.tool()
def status_da_base() -> str:
    """Mostra o que está indexado: fases, submódulos, quantidade de arquivos e padrões disponíveis."""
    return brain().status_text()


@mcp.tool()
def reindexar(do_zero: bool = False) -> str:
    """Relê as pastas de aulas, notas e repositórios. Use depois de adicionar PDFs de uma nova fase."""
    return json.dumps(brain().reindex(rebuild=do_zero), ensure_ascii=False)


@mcp.prompt(name="arquitetar")
def arquitetar(problema: str) -> str:
    """Fluxo completo: do problema ao mapa de arquitetura com roteiro."""
    return f"{WORKFLOW}\n{RULES}\nProblema do Henrique:\n{problema}"


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
