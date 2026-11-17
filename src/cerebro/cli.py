"""Linha de comando: cerebro <comando>."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from cerebro.config import load_settings


def _print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:  # terminal antigo do Windows
        print(text.encode("ascii", "replace").decode())


def cmd_ingest(args) -> int:
    from cerebro.knowledge import KnowledgeBase

    kb = KnowledgeBase(load_settings())
    _print("Indexando a base de conhecimento..." + (" (do zero)" if args.rebuild else ""))
    result = kb.ingest(rebuild=args.rebuild, log=_print if args.verbose else (lambda *_: None))
    _print(f"Pronto: {result['arquivos']} arquivos, {result['trechos']} trechos "
           f"(novos {result['novos']}, atualizados {result['atualizados']}, removidos {result['removidos']}) "
           f"em {result['segundos']} s.")
    return 0


def cmd_status(args) -> int:
    from cerebro.brain import Brain

    _print(Brain().status_text())
    return 0


def cmd_search(args) -> int:
    from cerebro.brain import Brain

    _print(Brain().search_text(" ".join(args.query), args.k, args.fase, args.tipo, max_chars=args.chars))
    return 0


def cmd_patterns(args) -> int:
    from cerebro.brain import Brain

    b = Brain()
    if args.action == "list":
        for p in b.lib.patterns:
            _print(f"{p.id:32} {p.name}")
    elif args.action == "validate":
        _print(f"{len(b.lib.patterns)} padrões válidos.")
        for name, res in b.lib.problems.items():
            _print(f"ERRO {name}: {res.errors}")
        return 1 if b.lib.problems else 0
    elif args.action == "render":
        for p in b.lib.patterns:
            r = b.generate(p.architecture.model_dump(mode="json"), f"Padrão da biblioteca: {p.name}")
            _print(f"{p.id}: {r.get('html')}")
        _print(f"Galeria: {b.update_gallery()}")
    return 0


def cmd_render(args) -> int:
    from cerebro.brain import Brain

    data = json.loads(Path(args.file).read_text(encoding="utf-8"))
    data = data.get("architecture", data)
    r = Brain().generate(data, args.problema or "", open_browser=args.abrir, allow_autofix=args.autofix)
    if not r["ok"]:
        _print("Arquitetura inválida:\n- " + "\n- ".join(r["erros"]))
        return 1
    _print(f"Mapa salvo em: {r['html']}")
    for w in r["avisos"]:
        _print(f"aviso: {w}")
    return 0


def cmd_gallery(args) -> int:
    from cerebro.brain import Brain, open_file

    path = Brain().update_gallery()
    _print(str(path))
    if args.abrir:
        open_file(path)
    return 0


def cmd_serve(args) -> int:
    from cerebro.mcp_server import main

    main()
    return 0


def cmd_repos(args) -> int:
    s = load_settings()
    target = s.resolve("data/repos")
    target.mkdir(parents=True, exist_ok=True)
    if not shutil.which("git"):
        _print("git não encontrado. Instale o Git for Windows: https://git-scm.com/download/win")
        return 1
    for url in s.repos:
        name = url.rstrip("/").split("/")[-1].removesuffix(".git")
        dest = target / name
        if (dest / ".git").exists():
            _print(f"atualizando {name}...")
            subprocess.run(["git", "-C", str(dest), "pull", "--ff-only", "--quiet"], check=False)
            continue
        _print(f"clonando {name}...")
        tmp = target / f".{name}.tmp"
        shutil.rmtree(tmp, ignore_errors=True)
        done = subprocess.run(["git", "clone", "--depth", "1", "--quiet", url, str(tmp)], check=False)
        if done.returncode != 0:
            _print(f"  não consegui clonar {url}")
            shutil.rmtree(tmp, ignore_errors=True)
            continue
        if dest.exists():  # cópia antiga sem git: substitui pela versão clonada
            shutil.rmtree(dest, ignore_errors=True)
        tmp.rename(dest)
    _print("Pronto. Rode 'cerebro ingest' para indexar as mudanças.")
    return 0


def desktop_config_path() -> Path:
    if sys.platform.startswith("win"):
        return Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming")) / "Claude" / "claude_desktop_config.json"
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/Claude/claude_desktop_config.json"
    return Path.home() / ".config/Claude/claude_desktop_config.json"


def cmd_install_mcp(args) -> int:
    root = load_settings().root
    entry = {
        "command": sys.executable,
        "args": ["-m", "cerebro.mcp_server"],
        "env": {"CEREBRO_ROOT": str(root), "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"},
    }
    path = Path(args.config) if args.config else desktop_config_path()
    config = {}
    if path.exists():
        try:
            config = json.loads(path.read_text(encoding="utf-8") or "{}")
        except json.JSONDecodeError:
            _print(f"Não consegui ler {path}: o JSON está inválido. Corrija ou apague o arquivo e rode de novo.")
            return 1
    config.setdefault("mcpServers", {})["cerebro-mle"] = entry
    if args.dry_run:
        _print(json.dumps(config, ensure_ascii=False, indent=2))
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_suffix(".json.bak")
        shutil.copy2(path, backup)
        _print(f"Backup da configuração anterior: {backup}")
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
    _print(f"Cérebro MLE registrado em {path}")
    _print("Feche o assistente de IA por completo (inclusive na bandeja do sistema) e abra de novo.")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="cerebro", description="Cérebro MLE: do problema ao mapa de arquitetura.")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("ingest", help="indexa aulas, notas e repositórios (incremental)")
    a.add_argument("--rebuild", action="store_true", help="refaz o índice do zero")
    a.add_argument("-v", "--verbose", action="store_true")
    a.set_defaults(fn=cmd_ingest)

    a = sub.add_parser("status", help="mostra o que está indexado")
    a.set_defaults(fn=cmd_status)

    a = sub.add_parser("search", help="testa a busca na base")
    a.add_argument("query", nargs="+")
    a.add_argument("-k", type=int, default=8)
    a.add_argument("--fase")
    a.add_argument("--tipo", choices=["aula", "projeto", "nota"])
    a.add_argument("--chars", type=int, default=300, help="caracteres de cada trecho no terminal")
    a.set_defaults(fn=cmd_search)

    a = sub.add_parser("patterns", help="biblioteca de arquiteturas modelo")
    a.add_argument("action", choices=["list", "validate", "render"])
    a.set_defaults(fn=cmd_patterns)

    a = sub.add_parser("render", help="gera o mapa a partir de um JSON de arquitetura")
    a.add_argument("file")
    a.add_argument("--problema")
    a.add_argument("--abrir", action="store_true", help="abre o HTML no navegador")
    a.add_argument("--autofix", action="store_true", help="corrige automaticamente o que for possível")
    a.set_defaults(fn=cmd_render)

    a = sub.add_parser("galeria", help="atualiza a página com todos os mapas gerados")
    a.add_argument("--abrir", action="store_true")
    a.set_defaults(fn=cmd_gallery)

    a = sub.add_parser("repos", help="clona ou atualiza os repositórios do config.yaml")
    a.set_defaults(fn=cmd_repos)

    a = sub.add_parser("serve", help="inicia o servidor MCP (usado pelo assistente de IA)")
    a.set_defaults(fn=cmd_serve)

    a = sub.add_parser("install-mcp", help="registra o Cérebro no assistente de IA desktop")
    a.add_argument("--dry-run", action="store_true", help="só mostra a configuração, sem gravar")
    a.add_argument("--config", help="caminho alternativo do arquivo de configuração MCP do app")
    a.set_defaults(fn=cmd_install_mcp)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
