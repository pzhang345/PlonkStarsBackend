@echo off
setlocal

rem Always run from the Backend/ directory, regardless of caller's cwd.
cd /d "%~dp0"

set CONTAINER_NAME=plonkstars-test-db
set COMPOSE_FILE=tests\docker-compose.test.yml

rem Make sure Docker Desktop / the Docker daemon is actually up.
docker info >nul 2>&1
if errorlevel 1 (
    echo Docker does not appear to be running. Start Docker and try again.
    exit /b 1
)

rem Reuse a running container, restart a stopped one, or start a fresh one.
for /f "delims=" %%i in ('docker ps --filter "name=^%CONTAINER_NAME%$" --format "{{.Names}}"') do set RUNNING=%%i
if defined RUNNING (
    echo Reusing already-running %CONTAINER_NAME% container.
) else (
    for /f "delims=" %%i in ('docker ps -a --filter "name=^%CONTAINER_NAME%$" --format "{{.Names}}"') do set EXISTING=%%i
    if defined EXISTING (
        echo Starting existing %CONTAINER_NAME% container...
        docker start %CONTAINER_NAME% >nul
    ) else (
        echo Creating %CONTAINER_NAME% container via docker compose...
        docker compose -f %COMPOSE_FILE% up -d --wait
    )
)

rem Poll pg_isready until Postgres accepts connections, or give up.
set /a TRIES=0
:wait_loop
docker exec %CONTAINER_NAME% pg_isready -U plonktest -d plonkstars_test >nul 2>&1
if not errorlevel 1 goto ready
set /a TRIES+=1
if %TRIES% GEQ 30 (
    echo Timed out waiting for %CONTAINER_NAME% to become ready.
    exit /b 1
)
timeout /t 1 >nul
goto wait_loop

:ready
rem Run pytest through the venv interpreter, forwarding any extra args.
.venv\Scripts\python.exe -m pytest %*
set PYTEST_EXIT=%ERRORLEVEL%

echo.
echo Test DB left running. Stop it with:
echo   docker compose -f %COMPOSE_FILE% down

exit /b %PYTEST_EXIT%
