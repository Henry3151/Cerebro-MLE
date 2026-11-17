"""Teste ponta a ponta: um cliente MCP real conversa com o servidor por stdio, como o Claude Desktop faz."""
import asyncio
import json
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

EXPECTED_TOOLS = {"buscar_conhecimento", "sugerir_padroes", "obter_padrao", "regras_da_arquitetura",
                  "gerar_mapa", "salvar_como_padrao", "status_da_base", "reindexar"}


def test_mcp_server_end_to_end(project):
    async def run():
        params = StdioServerParameters(command=sys.executable, args=["-m", "cerebro.mcp_server"],
                                       env={**os.environ, "CEREBRO_ROOT": str(project)})
        async with stdio_client(params) as (r, w), ClientSession(r, w) as s:
            await s.initialize()
            tools = {t.name for t in (await s.list_tools()).tools}
            assert EXPECTED_TOOLS <= tools

            await s.call_tool("reindexar", {})
            found = (await s.call_tool("buscar_conhecimento", {"consulta": "Airflow retreino"})).content[0].text
            assert "[F-" in found and "fase3_cloud_mlops" in found
            tag = found.split("[", 1)[1].split("]", 1)[0]

            pat = json.loads((await s.call_tool("obter_padrao", {"id_padrao": "classificacao_tabular_api"}))
                             .content[0].text)
            arch = pat["architecture"]
            arch["roadmap"][0]["sources"] = [tag]
            res = json.loads((await s.call_tool("gerar_mapa", {"arquitetura": arch, "problema": "churn",
                                                               "abrir_no_navegador": False})).content[0].text)
            assert res["ok"] and res["html"].endswith("mapa.html")

    asyncio.run(run())
