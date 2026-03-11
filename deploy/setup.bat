@echo off
CHCP 65001 >nul 2>&1
setlocal EnableDelayedExpansion

echo ============================================================
echo  Insurance Requisition Sorting System - Setup
echo ============================================================
echo.

:: ---- Resolve project root (one level up from deploy\) ----
set "PROJECT_DIR=%~dp0.."
pushd "%PROJECT_DIR%"
set "PROJECT_DIR=%CD%"
popd

echo Project directory: %PROJECT_DIR%
echo.

:: ---- Check Python 3.10+ ----
echo [1/6] Checking Python...
where python >nul 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: Python is not installed or not in PATH.
    echo.
    echo Install Python 3.10 or later from https://www.python.org/downloads/
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    goto :fail
)

for /f "tokens=*" %%v in ('python --version 2^>^&1') do set "PYVER=%%v"
echo   Found: %PYVER%

:: Parse major.minor version
for /f "tokens=2 delims= " %%a in ("%PYVER%") do set "PYVER_NUM=%%a"
for /f "tokens=1,2 delims=." %%a in ("%PYVER_NUM%") do (
    set "PY_MAJOR=%%a"
    set "PY_MINOR=%%b"
)

if !PY_MAJOR! LSS 3 (
    echo ERROR: Python 3.10+ is required. Found version %PYVER_NUM%.
    goto :fail
)
if !PY_MAJOR! EQU 3 if !PY_MINOR! LSS 10 (
    echo ERROR: Python 3.10+ is required. Found version %PYVER_NUM%.
    echo Install from https://www.python.org/downloads/
    goto :fail
)
echo   OK - Python %PYVER_NUM% meets the 3.10+ requirement.
echo.

:: ---- Check Tesseract OCR ----
echo [2/6] Checking Tesseract OCR...
set "TESS_FOUND="

:: Check PATH first
where tesseract >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=*" %%t in ('where tesseract') do (
        if not defined TESS_FOUND set "TESS_FOUND=%%t"
    )
)

:: Check common install locations
if not defined TESS_FOUND (
    if exist "C:\Program Files\Tesseract-OCR\tesseract.exe" (
        set "TESS_FOUND=C:\Program Files\Tesseract-OCR\tesseract.exe"
    )
)
if not defined TESS_FOUND (
    if exist "C:\Program Files (x86)\Tesseract-OCR\tesseract.exe" (
        set "TESS_FOUND=C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"
    )
)
:: Check scoop install path
if not defined TESS_FOUND (
    if exist "%USERPROFILE%\scoop\apps\tesseract\current\tesseract.exe" (
        set "TESS_FOUND=%USERPROFILE%\scoop\apps\tesseract\current\tesseract.exe"
    )
)
:: Check scoop global install path
if not defined TESS_FOUND (
    if exist "C:\ProgramData\scoop\apps\tesseract\current\tesseract.exe" (
        set "TESS_FOUND=C:\ProgramData\scoop\apps\tesseract\current\tesseract.exe"
    )
)

if not defined TESS_FOUND (
    echo.
    echo ERROR: Tesseract OCR is not installed or not found.
    echo.
    echo Install one of:
    echo   - Scoop:  scoop install tesseract
    echo   - Manual: https://github.com/UB-Mannheim/tesseract/wiki
    echo             Install to "C:\Program Files\Tesseract-OCR\"
    echo.
    echo After installing, make sure tesseract.exe is in your PATH
    echo or installed to one of the standard locations above.
    echo.
    goto :fail
)

echo   Found: %TESS_FOUND%
for /f "tokens=*" %%v in ('"%TESS_FOUND%" --version 2^>^&1') do (
    echo   Version: %%v
    goto :tess_ver_done
)
:tess_ver_done
echo   OK
echo.

:: ---- Create Python virtual environment ----
echo [3/6] Creating Python virtual environment in deploy\venv\ ...
if exist "%~dp0venv\Scripts\python.exe" (
    echo   Virtual environment already exists, skipping creation.
) else (
    python -m venv "%~dp0venv"
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        echo Make sure the 'venv' module is available (it ships with Python 3).
        goto :fail
    )
    echo   Created.
)
echo.

:: ---- Install dependencies ----
echo [4/6] Installing Python dependencies...
"%~dp0venv\Scripts\python.exe" -m pip install --upgrade pip >nul 2>&1
"%~dp0venv\Scripts\python.exe" -m pip install -r "%PROJECT_DIR%\requirements.txt" waitress
if errorlevel 1 (
    echo.
    echo ERROR: Failed to install Python packages.
    echo Check your internet connection and try again.
    goto :fail
)
echo   Dependencies installed successfully.
echo.

:: ---- Create data directories ----
echo [5/6] Creating data directories...
for %%d in (data logs reports scans) do (
    if not exist "%PROJECT_DIR%\%%d" (
        mkdir "%PROJECT_DIR%\%%d"
        echo   Created: %%d\
    ) else (
        echo   Exists:  %%d\
    )
)
echo.

:: ---- Copy default config ----
echo [6/6] Checking configuration...
if not exist "%PROJECT_DIR%\config" (
    mkdir "%PROJECT_DIR%\config"
    echo   Created config\ directory.
)
if exist "%PROJECT_DIR%\config\insurance_blocklist.csv" (
    echo   Blocklist config already present.
) else (
    echo   WARNING: No blocklist file found at config\insurance_blocklist.csv
    echo   You will need to provide this file before the system can flag cases.
)
echo.

:: ---- Done ----
echo ============================================================
echo  Setup Complete!
echo ============================================================
echo.
echo  Next steps:
echo.
echo   1. Place your insurance blocklist CSV in:
echo      %PROJECT_DIR%\config\insurance_blocklist.csv
echo.
echo   2. Start the web dashboard:
echo      deploy\start-web.bat
echo.
echo   3. Start the folder watcher (in a separate window):
echo      deploy\start-watcher.bat [scan-folder-path]
echo.
echo   4. Open a browser to http://localhost:5000
echo.
echo   Optional: Install as Windows services for auto-start:
echo      deploy\install-service.bat
echo.
echo ============================================================
goto :end

:fail
echo.
echo ============================================================
echo  Setup FAILED. Fix the errors above and try again.
echo ============================================================
echo.
pause
exit /b 1

:end
pause
exit /b 0
