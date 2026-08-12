@echo off
REM ============================================================================
REM  ProductChat - one-click local launcher (no Docker required)
REM  - Backend : FastAPI (uvicorn) on http://localhost:8000  (SQLite + embedded
REM              Qdrant, no Postgres/Qdrant/Redis servers needed)
REM  - Frontend: Vite dev server on http://localhost:3000
REM  First run sets everything up; later runs just start the two servers.
REM ============================================================================
setlocal
cd /d "%~dp0"

set "BACKEND=%~dp0backend"
set "FRONTEND=%~dp0frontend"
set "PYEXE=%BACKEND%\.venv\Scripts\python.exe"

echo(
echo === ProductChat launcher ===
echo(

REM ---- 1. Backend virtual environment ---------------------------------------
REM Rebuild the venv if it's missing OR broken (e.g. its base Python was
REM uninstalled/updated, which orphans the venv).
set "NEED_SETUP="
if not exist "%PYEXE%" set "NEED_SETUP=1"
if exist "%PYEXE%" ( "%PYEXE%" -c "import sys" >nul 2>&1 || set "NEED_SETUP=1" )

if defined NEED_SETUP (
    if exist "%BACKEND%\.venv" (
        echo [setup] Existing virtual environment is broken - rebuilding...
        rmdir /s /q "%BACKEND%\.venv"
    ) else (
        echo [setup] Creating Python virtual environment...
    )

    REM Find a usable base Python. Prefer the py launcher; otherwise look for a
    REM per-user python.org install. The Microsoft Store "python" alias is NOT
    REM a real interpreter, so it is deliberately not used here.
    set "BASEPY="
    where py >nul 2>&1 && set "BASEPY=py -3"
    if not defined BASEPY for /d %%d in ("%LOCALAPPDATA%\Programs\Python\Python3*") do if exist "%%d\python.exe" set "BASEPY=%%d\python.exe"

    if not defined BASEPY (
        echo [error] No Python interpreter found.
        echo         Install Python 3.12+ from https://www.python.org/downloads/
        echo         ^(tick "Add python.exe to PATH"^), then run this file again.
        echo(
        pause
        endlocal
        exit /b 1
    )

    echo [setup] Building virtual environment with: %BASEPY%
    %BASEPY% -m venv "%BACKEND%\.venv"
    echo [setup] Installing backend dependencies ^(this can take a few minutes^)...
    "%PYEXE%" -m pip install --upgrade pip
    "%PYEXE%" -m pip install -r "%BACKEND%\requirements-local.txt"
) else (
    echo [ok] Backend virtual environment present.
)

REM ---- 2. .env --------------------------------------------------------------
if not exist "%BACKEND%\.env" (
    echo [warn] backend\.env is missing - the app may not start correctly.
) else (
    echo [ok] backend\.env present.
)

REM ---- 3. Frontend dependencies ---------------------------------------------
if not exist "%FRONTEND%\node_modules" (
    echo [setup] Installing frontend dependencies ^(first run only^)...
    pushd "%FRONTEND%"
    call npm install
    popd
) else (
    echo [ok] Frontend dependencies present.
)

REM ---- 4. Launch both servers in their own windows --------------------------
echo(
echo [run] Starting backend  -> http://localhost:8000  (docs: /docs)
start "ProductChat Backend" /D "%BACKEND%" cmd /k .venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000

echo [run] Starting frontend -> http://localhost:3000
start "ProductChat Frontend" /D "%FRONTEND%" cmd /k npm run dev

REM ---- 5. Open the browser once the frontend has had time to boot -----------
timeout /t 8 /nobreak >nul
start "" "http://localhost:3000"

echo(
echo ============================================================
echo  ProductChat is starting in two new windows.
echo    Frontend : http://localhost:3000
echo    Backend  : http://localhost:8000/docs
echo(
echo  NOTE: set your Mistral API key in backend\.env (MISTRAL_API_KEY=)
echo        or on the Settings page, then load sample products from
echo        the Admin/Indexing page for the chat to return results.
echo  Close the two server windows to stop ProductChat.
echo ============================================================
echo(
pause
endlocal
