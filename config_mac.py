"""
Configuracion de MemaFlow — override para macOS (Apple Silicon).

La transcripcion corre en la GPU (Metal) via mlx-whisper. En Macs sin ventilador
(Air) eso evita el thermal throttling de la CPU y NO se degrada con el uso.
El daemon carga este archivo automaticamente cuando detecta macOS.
"""

# Hotkey push-to-talk. En Mac usamos F9 (pynput no reconoce "scroll_lock" en macOS).
# Si F9 no responde: Ajustes > Teclado > Atajos > desactivar atajos que usen F9.
HOTKEY = "f9"

# ---------------------------------------------------------------------------
# BACKEND: en Apple Silicon, MLX corre en GPU/Metal (rapido, no throttlea).
# Si MLX falla al cargar, el daemon cae solo a faster-whisper (CPU).
# ---------------------------------------------------------------------------
WHISPER_BACKEND = "mlx"

# Modelo MLX en GPU. large-v3-turbo = mejor calidad/velocidad para dictado.
#   "mlx-community/whisper-large-v3-turbo"     -> fp16, ~1.5 GB, maxima calidad.
#   "mlx-community/whisper-large-v3-turbo-q4"  -> 4-bit, ~0.5 GB, mas liviano.
MLX_MODEL = "mlx-community/whisper-large-v3-turbo"

# Fallback faster-whisper (solo si WHISPER_BACKEND="faster" o si MLX falla).
WHISPER_MODEL = "small"
WHISPER_DEVICE = "auto"
WHISPER_BEAM_SIZE = 5

WHISPER_LANGUAGE = "es"

# ---------------------------------------------------------------------------
# CALIDAD: PERSONALIZA este prompt con las palabras/nombres que mas usas.
# (con tildes y enie reales)
# ---------------------------------------------------------------------------
INITIAL_PROMPT = (
    "Hola, te cuento lo que estuve haciendo hoy. Transcripcion en espanol "
    "con puntuacion y mayusculas correctas. Terminos que escribo asi: "
    "Claude Code, ChatGPT, Python, GPU, prompt, API, workflow, agente de IA."
)

CONDITION_ON_PREVIOUS_TEXT = False

HALLUCINATION_BLACKLIST = [
    "subtitulos realizados por la comunidad de amara.org",
    "subtitulos por la comunidad de amara.org",
    "subtitulado por la comunidad de amara.org",
    "mas informacion en www",
    "gracias por ver el video",
    "gracias por ver este video",
    "no olvides suscribirte",
    "suscribite al canal",
    "subscribe",
    "thanks for watching",
]

# ---------------------------------------------------------------------------
# Audio
# ---------------------------------------------------------------------------
SAMPLE_RATE = 16000
CHANNELS = 1

# Mic de RESPALDO: graba en paralelo con el mic default del sistema (ej AirPods)
# + el primero de esta lista. Al soltar la tecla gana el de mayor senal. Asi, si
# los AirPods entregan silencio (se auto-cambian al telefono), el dictado se salva
# con el mic interno. Poner el nombre (o parte) de tu mic interno.
INPUT_DEVICE_PREFERENCE = ["MacBook", "Microphone"]

MIN_DURATION = 0.3
TYPE_THRESHOLD_CHARS = 500

BEEPS_ENABLED = True
BEEP_START_FREQ = 880
BEEP_END_FREQ = 1320
BEEP_DURATION_MS = 60
BEEP_ERROR_FREQ = 440

PARAGRAPH_PAUSE_SEC = 1.5
PARAGRAPH_SEPARATOR = "\n\n"
