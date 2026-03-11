@echo off
CHCP 65001 >nul 2>&1
setlocal

echo ============================================================
echo  Insurance Sorting - Folder Watcher
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

:: Determine watch folder
set "WATCH_FOLDER=%~1"
if "%WATCH_FOLDER%"=="" (
    set "WATCH_FOLDER=%PROJECT_DIR%\scans"
)

:: Verify folder exists
if not exist "%WATCH_FOLDER%" (
    echo WARNING: Watch folder does not exist: %WATCH_FOLDER%
    echo Creating it now...
    mkdir "%WATCH_FOLDER%"
    if errorlevel 1 (
        echo ERROR: Could not create folder: %WATCH_FOLDER%
        goto :fail
    )
)

echo Watching folder: %WATCH_FOLDER%
echo New scanned files will be processed automatically.
echo Press Ctrl+C to stop.
echo.

cd /d "%PROJECT_DIR%"
"%~dp0venv\Scripts\python.exe" run.py watch "%WATCH_FOLDER%"

if errorlevel 1 (
    echo.
    echo ERROR: Folder watcher exited with an error.
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
