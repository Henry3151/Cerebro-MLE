@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Atualizando a base do Cerebro MLE (so arquivos novos ou alterados)...
.venv\Scripts\cerebro repos
.venv\Scripts\cerebro ingest
.venv\Scripts\cerebro status
pause
