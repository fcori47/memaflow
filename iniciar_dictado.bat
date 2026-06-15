@echo off
REM ============================================================
REM Arranca el dictado por voz sin ventana de consola.
REM Usa el Python del entorno virtual local (.venv).
REM ============================================================

cd /d "%~dp0"

if not exist .venv\Scripts\pythonw.exe (
    echo No encuentro el entorno virtual. Corre primero install.bat
    pause
    exit /b 1
)

REM pythonw = Python sin ventana de consola (corre en background)
start "" /B ".venv\Scripts\pythonw.exe" daemon.py
exit /b 0
