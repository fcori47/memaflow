#!/bin/bash
# Arranca el daemon de MemaFlow en background (macOS).
# Uso: ./iniciar_dictado_mac.sh  (o ponelo en Items de inicio para autostart)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$SCRIPT_DIR/.venv"
PYTHON="$VENV/bin/python"
LOG_DIR="$SCRIPT_DIR/logs"
LOG_FILE="$LOG_DIR/memaflow_$(date +%Y%m%d).log"

mkdir -p "$LOG_DIR"

if [ ! -f "$PYTHON" ]; then
    osascript -e 'display alert "MemaFlow" message "Falta el entorno virtual. Corre install_mac.sh primero." as warning'
    exit 1
fi

# Matar instancia previa si existe
pkill -f "MacOS/Python daemon.py" 2>/dev/null
pkill -f "$PYTHON daemon.py" 2>/dev/null
sleep 0.5

cd "$SCRIPT_DIR"
nohup "$PYTHON" daemon.py >> "$LOG_FILE" 2>&1 &
echo "MemaFlow arrancado (PID $!). Log: $LOG_FILE"
