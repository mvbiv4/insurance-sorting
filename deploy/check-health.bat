@echo off
CHCP 65001 >nul 2>&1
setlocal EnableDelayedExpansion

echo ============================================================
echo  Insurance Sorting - Health Check
echo ============================================================
echo.

:: Resolve project root
set "PROJECT_DIR=%~dp0.."
pushd "%PROJECT_DIR%"
set "PROJECT_DIR=%CD%"
popd

set "PASS=0"
set "FAIL=0"
set "WARN=0"

:: ---- Check Web Dashboard ----
echo [Web Dashboard]
curl -s -o nul -w "%%{http_code}" http://localhost:5000/ > "%TEMP%\ins_health_http.tmp" 2>nul
set /p HTTP_CODE=<"%TEMP%\ins_health_http.tmp"
del "%TEMP%\ins_health_http.tmp" 2>nul

if "%HTTP_CODE%"=="200" (
    echo   PASS - Web dashboard responding on port 5000 (HTTP 200)
    set /a PASS+=1
) else (
    if "%HTTP_CODE%"=="" (
        echo   FAIL - Web dashboard is not responding on port 5000
        echo          Start it with: deploy\start-web.bat
    ) else (
        echo   WARN - Web dashboard returned HTTP %HTTP_CODE% on port 5000
        set /a WARN+=1
    )
    set /a FAIL+=1
)
echo.

:: ---- Check Watcher Process ----
echo [Folder Watcher]
tasklist /fi "imagename eq python.exe" /v 2>nul | findstr /i "watch" >nul 2>&1
if not errorlevel 1 (
    echo   PASS - Watcher process appears to be running
    set /a PASS+=1
) else (
    :: Also check via NSSM service
    sc query InsuranceSortingWatcher >nul 2>&1
    if not errorlevel 1 (
        for /f "tokens=3 delims=: " %%s in ('sc query InsuranceSortingWatcher ^| findstr "STATE"') do set "SVC_STATE=%%s"
        if "!SVC_STATE!"=="4" (
            echo   PASS - Watcher running as Windows service
            set /a PASS+=1
        ) else (
            echo   WARN - Watcher service installed but state is: !SVC_STATE!
            echo          Expected RUNNING (4). Try: nssm restart InsuranceSortingWatcher
            set /a WARN+=1
            set /a FAIL+=1
        )
    ) else (
        echo   FAIL - No watcher process or service found
        echo          Start it with: deploy\start-watcher.bat
        set /a FAIL+=1
    )
)
echo.

:: ---- Check Database ----
echo [Database]
set "DB_FILE=%PROJECT_DIR%\data\flagged_cases.db"
if exist "%DB_FILE%" (
    for %%f in ("%DB_FILE%") do set "DB_SIZE=%%~zf"
    set /a DB_SIZE_KB=!DB_SIZE! / 1024
    echo   PASS - Database exists: flagged_cases.db (!DB_SIZE_KB! KB)
    set /a PASS+=1
) else (
    echo   WARN - Database not found yet: %DB_FILE%
    echo          It will be created when the first file is processed.
    set /a WARN+=1
)
echo.

:: ---- Check Config ----
echo [Configuration]
if exist "%PROJECT_DIR%\config\insurance_blocklist.csv" (
    echo   PASS - Blocklist file present
    set /a PASS+=1
) else (
    echo   WARN - No blocklist file at config\insurance_blocklist.csv
    echo          The system cannot flag cases without this file.
    set /a WARN+=1
)
echo.

:: ---- Check Disk Space ----
echo [Disk Space]
for /f "tokens=3" %%a in ('dir "%PROJECT_DIR%" /-C 2^>nul ^| findstr /i "bytes free"') do set "FREE_BYTES=%%a"
if defined FREE_BYTES (
    set /a FREE_GB=!FREE_BYTES:~0,-9! 2>nul
    if !FREE_GB! LSS 1 (
        echo   WARN - Low disk space: less than 1 GB free
        set /a WARN+=1
    ) else (
        echo   PASS - !FREE_GB! GB free disk space
        set /a PASS+=1
    )
) else (
    echo   WARN - Could not determine free disk space
    set /a WARN+=1
)
echo.

:: ---- Check Tesseract ----
echo [Tesseract OCR]
where tesseract >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=*" %%v in ('tesseract --version 2^>^&1') do (
        echo   PASS - Tesseract found: %%v
        goto :tess_done
    )
    :tess_done
    set /a PASS+=1
) else (
    if exist "C:\Program Files\Tesseract-OCR\tesseract.exe" (
        echo   PASS - Tesseract found at standard location
        set /a PASS+=1
    ) else (
        echo   FAIL - Tesseract not found in PATH or standard locations
        set /a FAIL+=1
    )
)
echo.

:: ---- Summary ----
echo ============================================================
set /a TOTAL=!PASS!+!FAIL!
if !FAIL! EQU 0 (
    if !WARN! EQU 0 (
        echo  Result: ALL CHECKS PASSED (!PASS!/!TOTAL!)
    ) else (
        echo  Result: PASSED with !WARN! warning(s) (!PASS!/!TOTAL! checks OK)
    )
) else (
    echo  Result: !FAIL! check(s) FAILED, !PASS! passed, !WARN! warning(s)
)
echo ============================================================
echo.

pause
exit /b !FAIL!
