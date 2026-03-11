@echo off
CHCP 65001 >nul 2>&1
setlocal EnableDelayedExpansion

echo ============================================================
echo  Insurance Sorting - Windows Service Installer
echo ============================================================
echo.
echo  This script installs the web dashboard and folder watcher
echo  as Windows services using NSSM (Non-Sucking Service Manager).
echo  Services will auto-start on boot and restart on failure.
echo.
echo  Requires: Administrator privileges and NSSM in PATH.
echo ============================================================
echo.

:: ---- Check admin privileges ----
net session >nul 2>&1
if errorlevel 1 (
    echo ERROR: This script must be run as Administrator.
    echo Right-click the script and select "Run as administrator".
    echo.
    goto :fail
)

:: ---- Resolve project root ----
set "PROJECT_DIR=%~dp0.."
pushd "%PROJECT_DIR%"
set "PROJECT_DIR=%CD%"
popd

:: ---- Check NSSM ----
echo [1/5] Checking for NSSM...
where nssm >nul 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: NSSM is not installed or not in PATH.
    echo.
    echo Install NSSM (Non-Sucking Service Manager):
    echo   - Scoop:  scoop install nssm
    echo   - Manual: https://nssm.cc/download
    echo.
    echo After installing, make sure nssm.exe is in your PATH.
    goto :fail
)
echo   NSSM found.
echo.

:: ---- Check venv ----
echo [2/5] Checking virtual environment...
if not exist "%~dp0venv\Scripts\python.exe" (
    echo ERROR: Virtual environment not found.
    echo Run setup.bat first before installing services.
    goto :fail
)
set "PYTHON_EXE=%~dp0venv\Scripts\python.exe"
echo   Found: %PYTHON_EXE%
echo.

:: ---- Set watch folder ----
set "WATCH_FOLDER=%~1"
if "%WATCH_FOLDER%"=="" (
    set "WATCH_FOLDER=%PROJECT_DIR%\scans"
)
echo   Watch folder: %WATCH_FOLDER%
echo.

:: ---- Install Web Dashboard Service ----
echo [3/5] Installing InsuranceSortingWeb service...

:: Remove existing service if present
nssm status InsuranceSortingWeb >nul 2>&1
if not errorlevel 1 (
    echo   Removing existing InsuranceSortingWeb service...
    nssm stop InsuranceSortingWeb >nul 2>&1
    nssm remove InsuranceSortingWeb confirm >nul 2>&1
)

nssm install InsuranceSortingWeb "%PYTHON_EXE%" "run.py web --host 0.0.0.0 --port 5000"
if errorlevel 1 (
    echo ERROR: Failed to install InsuranceSortingWeb service.
    goto :fail
)

nssm set InsuranceSortingWeb AppDirectory "%PROJECT_DIR%"
nssm set InsuranceSortingWeb DisplayName "Insurance Sorting - Web Dashboard"
nssm set InsuranceSortingWeb Description "CPG Insurance Requisition Sorting System - Web Dashboard on port 5000"
nssm set InsuranceSortingWeb Start SERVICE_AUTO_START
nssm set InsuranceSortingWeb AppStdout "%PROJECT_DIR%\logs\web-service.log"
nssm set InsuranceSortingWeb AppStderr "%PROJECT_DIR%\logs\web-service-error.log"
nssm set InsuranceSortingWeb AppStdoutCreationDisposition 4
nssm set InsuranceSortingWeb AppStderrCreationDisposition 4
nssm set InsuranceSortingWeb AppRotateFiles 1
nssm set InsuranceSortingWeb AppRotateBytes 10485760
nssm set InsuranceSortingWeb AppRestartDelay 5000
nssm set InsuranceSortingWeb AppExit Default Restart

echo   InsuranceSortingWeb service installed.
echo.

:: ---- Install Watcher Service ----
echo [4/5] Installing InsuranceSortingWatcher service...

nssm status InsuranceSortingWatcher >nul 2>&1
if not errorlevel 1 (
    echo   Removing existing InsuranceSortingWatcher service...
    nssm stop InsuranceSortingWatcher >nul 2>&1
    nssm remove InsuranceSortingWatcher confirm >nul 2>&1
)

nssm install InsuranceSortingWatcher "%PYTHON_EXE%" "run.py watch \"%WATCH_FOLDER%\""
if errorlevel 1 (
    echo ERROR: Failed to install InsuranceSortingWatcher service.
    goto :fail
)

nssm set InsuranceSortingWatcher AppDirectory "%PROJECT_DIR%"
nssm set InsuranceSortingWatcher DisplayName "Insurance Sorting - Folder Watcher"
nssm set InsuranceSortingWatcher Description "CPG Insurance Requisition Sorting System - Watches scan folder for new files"
nssm set InsuranceSortingWatcher Start SERVICE_AUTO_START
nssm set InsuranceSortingWatcher AppStdout "%PROJECT_DIR%\logs\watcher-service.log"
nssm set InsuranceSortingWatcher AppStderr "%PROJECT_DIR%\logs\watcher-service-error.log"
nssm set InsuranceSortingWatcher AppStdoutCreationDisposition 4
nssm set InsuranceSortingWatcher AppStderrCreationDisposition 4
nssm set InsuranceSortingWatcher AppRotateFiles 1
nssm set InsuranceSortingWatcher AppRotateBytes 10485760
nssm set InsuranceSortingWatcher AppRestartDelay 5000
nssm set InsuranceSortingWatcher AppExit Default Restart
nssm set InsuranceSortingWatcher DependOnService InsuranceSortingWeb

echo   InsuranceSortingWatcher service installed.
echo.

:: ---- Create logs directory ----
if not exist "%PROJECT_DIR%\logs" mkdir "%PROJECT_DIR%\logs"

:: ---- Start services ----
echo [5/5] Starting services...
nssm start InsuranceSortingWeb
timeout /t 3 /nobreak >nul
nssm start InsuranceSortingWatcher

echo.
echo ============================================================
echo  Services Installed Successfully
echo ============================================================
echo.
echo  InsuranceSortingWeb      - Web dashboard on port 5000
echo  InsuranceSortingWatcher  - Watching: %WATCH_FOLDER%
echo.
echo  Both services are set to auto-start on boot and restart
echo  on failure.
echo.
echo  Management commands:
echo    nssm status InsuranceSortingWeb
echo    nssm stop InsuranceSortingWeb
echo    nssm start InsuranceSortingWeb
echo    nssm restart InsuranceSortingWeb
echo.
echo  View logs:
echo    %PROJECT_DIR%\logs\web-service.log
echo    %PROJECT_DIR%\logs\watcher-service.log
echo.
echo  To uninstall services:
echo    nssm remove InsuranceSortingWeb confirm
echo    nssm remove InsuranceSortingWatcher confirm
echo.
echo ============================================================
goto :end

:fail
echo.
echo ============================================================
echo  Service installation FAILED. Fix the errors above.
echo ============================================================
echo.
pause
exit /b 1

:end
pause
exit /b 0
