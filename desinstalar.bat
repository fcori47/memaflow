@echo off
REM ============================================================
REM Desinstala el dictado por voz: para el daemon, borra el venv
REM y avisa donde estan los archivos de autostart y el modelo
REM cacheado por si querer borrar manualmente.
REM ============================================================

setlocal enableextensions
cd /d "%~dp0"

echo.
echo ============================================================
echo   Dictado por voz - Desinstalar
echo ============================================================
echo.
echo Esto va a:
echo   - Cerrar el dictado si esta corriendo.
echo   - Borrar el entorno virtual .venv (libs instaladas).
echo.
echo NO va a borrar:
echo   - El modelo de Whisper cacheado en %USERPROFILE%\.cache\huggingface\
echo     (~1.6 GB; borralo a mano si queres).
echo   - El acceso directo de autostart en shell:startup
echo     (Win+R, "shell:startup", borrar a mano si lo creaste).
echo.
choice /m "Continuar"
if errorlevel 2 (
    echo Cancelado.
    pause
    exit /b 0
)

REM Cerrar pythonw que corre el daemon
echo.
echo Cerrando dictado si esta corriendo...
taskkill /F /IM pythonw.exe >nul 2>nul
taskkill /F /IM python.exe /FI "WINDOWTITLE eq daemon*" >nul 2>nul

REM Borrar venv
if exist .venv (
    echo Borrando .venv ...
    rmdir /S /Q .venv
)

echo.
echo Listo. Si tambien queres borrar el modelo de Whisper:
echo   1. Win+R
echo   2. Escribi: %%USERPROFILE%%\.cache\huggingface
echo   3. Borrar las carpetas que digan "whisper" o "Systran"
echo.
pause
