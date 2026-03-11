@echo off
CHCP 65001 >nul 2>&1
setlocal

echo ============================================================
echo  Insurance Sorting - Web Dashboard
echo ============================================================
echo.

:: Resolve project root
set "PROJECT_DIR=%~dp0.."
pushd "%PROJECT_DIR%"
set "PROJECT_DIR=%CD%"
popd

:: Check venv exists
if not exist "%~dp0venv\Scripts\python.exe" (
    echo ERROR: Virtual environment not found.
    echo Run setup.bat first to set up the environment.
    echo.
    goto :fail
)

:: Activate venv and start web dashboard
echo Starting web dashboard on http://localhost:5000 ...
echo Press Ctrl+C to stop.
echo.

cd /d "%PROJECT_DIR%"
"%~dp0venv\Scripts\python.exe" run.py web --port 5000

if errorlevel 1 (
    echo.
    echo ERROR: Web dashboard exited with an error.
    goto :fail
)

goto :end

:fail
echo.
echo Press any key to close this window...
pause >nul
exit /b 1

:end
exit /b 0
