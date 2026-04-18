@echo off
title Scan Agent
cd /d "%~dp0"

echo ============================================================
echo   Scan Agent - Starting...
echo ============================================================
echo.

REM Activate virtual environment if present
if exist ".venv\Scripts\activate.bat" (
    echo Activating virtual environment...
    call .venv\Scripts\activate.bat
)

REM Try to find Python
where python >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set PYTHON_CMD=python
    goto :found_python
)

where py >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set PYTHON_CMD=py
    goto :found_python
)

where python3 >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set PYTHON_CMD=python3
    goto :found_python
)

echo ERROR: Python not found!
echo.
echo Install Python 3.8+ from https://www.python.org/downloads/
echo Make sure to check "Add Python to PATH" during installation.
echo.
pause
exit /b 1

:found_python
echo Using: %PYTHON_CMD%
%PYTHON_CMD% --version
echo.

REM Run the orchestrator
%PYTHON_CMD% run.py %*

REM If run.py exits (error or Ctrl+C), pause so user can read output
echo.
echo ============================================================
echo   Scan Agent stopped.
echo ============================================================
pause
