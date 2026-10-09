@echo off
title NEVORA BMS Intelligence - Streamlit Dashboard
echo ========================================================
echo   NEVORA BMS INTELLIGENCE // 800V PINN DIGITAL TWIN
echo   Launching Streamlit Interactive Dashboard...
echo ========================================================
echo.

REM Check if Python launcher 'py' is available
where py >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo Starting Streamlit via Python launcher...
    py -3.13 -m streamlit run app.py
    if %ERRORLEVEL% NEQ 0 (
        py -m streamlit run app.py
    )
    goto end
)

REM Fallback to standard python in PATH
where python >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo Starting Streamlit via python...
    python -m streamlit run app.py
    goto end
)

echo [ERROR] Python not found in PATH or launcher.
pause

:end
