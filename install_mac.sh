#!/bin/bash
# Instalador de MemaFlow para macOS (Apple Silicon: M1/M2/M3/M4).
# Crea el entorno virtual, instala dependencias y baja el modelo.

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "==> MemaFlow — instalador para macOS"

# 1) Python 3.10+
if ! command -v python3 >/dev/null 2>&1; then
    echo "ERROR: no encuentro python3. Instalalo desde https://www.python.org/downloads/ y reintenta."
    exit 1
fi
echo "==> Python: $(python3 --version)"

# 2) ffmpeg (necesario para decodificar audio)
if ! command -v ffmpeg >/dev/null 2>&1; then
    echo "==> Instalando ffmpeg con Homebrew..."
    if command -v brew >/dev/null 2>&1; then
        brew install ffmpeg
    else
        echo "AVISO: no tenes Homebrew. Instala ffmpeg a mano (brew install ffmpeg) si la transcripcion falla."
    fi
fi

# 3) Entorno virtual
if [ ! -d ".venv" ]; then
    echo "==> Creando entorno virtual..."
    python3 -m venv .venv
fi

# 4) Dependencias
echo "==> Instalando dependencias (puede tardar unos minutos)..."
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements.txt

# 5) Pre-descargar el modelo MLX (asi el primer dictado no espera)
echo "==> Descargando el modelo de voz (~1.5 GB, una sola vez)..."
./.venv/bin/python - <<'PY'
import numpy as np, mlx_whisper
mlx_whisper.transcribe(np.zeros(16000, dtype=np.float32),
    path_or_hf_repo="mlx-community/whisper-large-v3-turbo", language="es", fp16=True)
print("Modelo listo.")
PY

echo ""
echo "==> Listo. Para arrancar:  ./iniciar_dictado_mac.sh"
echo ""
echo "IMPORTANTE — permisos de macOS (una sola vez):"
echo "  1) Ajustes del Sistema > Privacidad y Seguridad > Accesibilidad  -> permitir la app/terminal."
echo "  2) Ajustes del Sistema > Privacidad y Seguridad > Microfono      -> permitir."
echo "  3) Para que arranque solo al prender la Mac: Ajustes > General >"
echo "     Items de inicio > '+' y agregar iniciar_dictado_mac.sh"
echo ""
echo "Uso: hace clic donde quieras escribir, manten apretada F9, hablas, soltas."
