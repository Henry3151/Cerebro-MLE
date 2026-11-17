@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ==================================================
echo   Cerebro MLE - instalacao
echo ==================================================

set PY=
where py >nul 2>nul && set PY=py -3
if "%PY%"=="" (where python >nul 2>nul && set PY=python)
if "%PY%"=="" (
  echo Python nao encontrado. Instale o Python 3.10 ou mais novo em https://www.python.org/downloads/
  echo Marque a opcao "Add python.exe to PATH" durante a instalacao.
  pause
  exit /b 1
)

%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)"
if errorlevel 1 (
  echo E preciso Python 3.10 ou mais novo.
  pause
  exit /b 1
)

if not exist .venv (
  echo [1/5] Criando ambiente virtual...
  %PY% -m venv .venv || goto erro
)
echo [2/5] Instalando dependencias...
.venv\Scripts\python -m pip install --upgrade pip -q
.venv\Scripts\python -m pip install -e . -q || goto erro

echo [3/5] Baixando seus repositorios do GitHub...
.venv\Scripts\cerebro repos

echo [4/5] Indexando aulas, notas e repositorios (pode levar alguns minutos)...
.venv\Scripts\cerebro ingest || goto erro
.venv\Scripts\cerebro patterns render >nul

echo [5/5] Conectando ao assistente de IA...
.venv\Scripts\cerebro install-mcp || goto erro

echo.
echo Pronto! Feche o assistente de IA por completo (tambem na bandeja do sistema) e abra de novo.
echo Depois, no assistente, peca por exemplo:
echo   "Cerebro, monte a arquitetura para detectar fraude em tempo real"
echo.
pause
exit /b 0

:erro
echo.
echo Algo deu errado. Copie a mensagem acima e mande para o suporte do projeto.
pause
exit /b 1
