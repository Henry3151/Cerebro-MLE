"""Abre cada mapa.html num Chromium headless, confirma que o Mermaid desenhou sem erro e tira um print.

Uso (desenvolvimento): python scripts/check_render.py outputs [pasta_dos_prints]
Requer: pip install playwright  (e um Chromium disponível)
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

root = Path(sys.argv[1])
shots = Path(sys.argv[2]) if len(sys.argv) > 2 else None
files = sorted(root.rglob("mapa.html"))
failed = 0
with sync_playwright() as p:
    import os
    exe = os.environ.get("CHROME_PATH")
    browser = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch()
    page = browser.new_page(viewport={"width": 1500, "height": 1000})
    for f in files:
        errors = []
        page.on("pageerror", lambda e, errs=errors: errs.append(str(e)))
        page.goto(f.resolve().as_uri())
        page.wait_for_timeout(1500)
        svg = page.query_selector(".diagram svg")
        text = page.inner_text(".diagram")
        ok = svg is not None and "Syntax error" not in text and not errors
        failed += not ok
        print(("OK  " if ok else "ERRO"), f.parent.name, errors[:1])
        if shots and svg:
            shots.mkdir(parents=True, exist_ok=True)
            page.query_selector(".diagram").screenshot(path=str(shots / f"{f.parent.name}.png"))
    browser.close()
print(f"{len(files) - failed}/{len(files)} mapas renderizados")
sys.exit(1 if failed else 0)
