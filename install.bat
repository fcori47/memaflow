@echo off
REM ============================================================
REM Instalador del dictado por voz
REM
REM Lo que hace:
REM   1. Verifica que Python este instalado (3.10 o superior).
REM   2. Crea un entorno virtual aislado en .venv\
REM   3. Instala las dependencias dentro del venv (no toca tu Python global).
REM   4. Te dice como arrancarlo.
REM ============================================================

setlocal enableextensions
cd /d "%~dp0"

echo.
echo ============================================================
echo   Dictado por voz - Instalador
echo ============================================================
echo.

REM ---- 1. Detectar Python ----
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] No se encontro Python en tu PC.
    echo.
    echo Instalalo desde:
    echo   https://www.python.org/downloads/
    echo.
    echo IMPORTANTE: al instalar, tildar la casilla "Add Python to PATH".
    echo Despues de instalar Python, volve a correr este install.bat
    echo.
    pause
    exit /b 1
)

echo [1/4] Python detectado:
python --version
echo.

REM ---- 2. Crear venv ----
if exist .venv (
    echo [2/4] Entorno virtual .venv ya existe, lo reuso.
) else (
    echo [2/4] Creando entorno virtual aislado en .venv ...
    python -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] No pude crear el entorno virtual.
        pause
        exit /b 1
    )
)
echo.

REM ---- 3. Activar venv + actualizar pip ----
call .venv\Scripts\activate.bat
echo [3/4] Actualizando pip...
python -m pip install --upgrade pip --quiet
echo.

REM ---- 4. Instalar dependencias ----
echo [4/4] Instalando dependencias (puede tardar 2-5 minutos la primera vez)...
echo.
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Fallo la instalacion de dependencias.
    pause
    exit /b 1
)
echo.

REM ---- 5. Detectar GPU NVIDIA ----
echo ============================================================
echo   Detectando GPU NVIDIA...
echo ============================================================
where nvidia-smi >nul 2>nul
if %errorlevel% equ 0 (
    echo GPU NVIDIA detectada. El dictado va a usar GPU (cuda/float16).
    echo Modelo recomendado: large-v3-turbo ^(ya configurado^).
) else (
    echo No detecte GPU NVIDIA.
    echo Va a usar CPU. Te recomiendo cambiar el modelo a uno mas chico:
    echo   1. Abri config.py
    echo   2. Cambia WHISPER_MODEL = "large-v3-turbo" por WHISPER_MODEL = "medium"
    echo      ^(o "small" si la PC es vieja^)
)
echo.

REM ---- 6. Crear acceso directo en Startup de Windows ----
echo ============================================================
echo   Configurando autostart...
echo ============================================================
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$startup=[Environment]::GetFolderPath('Startup');" ^
  "$target=(Resolve-Path '.\iniciar_dictado.bat').Path;" ^
  "$workdir=(Get-Location).Path;" ^
  "$s=(New-Object -ComObject WScript.Shell).CreateShortcut(\"$startup\Dictado por voz.lnk\");" ^
  "$s.TargetPath=$target; $s.WorkingDirectory=$workdir; $s.WindowStyle=7;" ^
  "$s.Description='Dictado por voz con Whisper'; $s.Save();" ^
  "Write-Host ('Autostart configurado en: ' + $startup + '\Dictado por voz.lnk')"
echo.

echo ============================================================
echo   Instalacion lista
echo ============================================================
echo.
echo Para arrancar el dictado AHORA, doble click en:
echo   iniciar_dictado.bat
echo.
echo La proxima vez que prendas la PC va a arrancar solo.
echo Si queres sacarlo del autostart, borra el acceso directo desde:
echo   Win+R -^> shell:startup -^> borrar "Dictado por voz.lnk"
echo.
pause
