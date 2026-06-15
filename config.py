"""
Configuracion de MemaFlow (default / Windows).
Editar y reiniciar el daemon para aplicar cambios.

En macOS el daemon carga ademas config_mac.py (lo pisa donde corresponda).
"""

# ---------------------------------------------------------------------------
# Hotkey push-to-talk. Mantener apretada para grabar, soltar para transcribir + pegar.
# Opciones de tecla unica: "f1".."f12", "pause", "scroll_lock", "insert".
# Combinaciones formato pynput: "<ctrl>+<space>", "<alt>+<f9>", etc.
# ---------------------------------------------------------------------------
HOTKEY = "f9"

# ---------------------------------------------------------------------------
# BACKEND de transcripcion.
#   "faster" -> faster-whisper (GPU NVIDIA/CUDA o CPU). Default en Windows/Linux.
#   "mlx"    -> mlx-whisper en GPU/Metal (solo Apple Silicon; ver config_mac.py).
# ---------------------------------------------------------------------------
WHISPER_BACKEND = "faster"

# Modelo faster-whisper. large-v3-turbo: rapido + preciso en GPU.
# Sin GPU NVIDIA, usar "small" o "medium" (CPU).
WHISPER_MODEL = "large-v3-turbo"
WHISPER_DEVICE = "auto"      # "auto" detecta CUDA; o forzar "cuda"/"cpu"
WHISPER_BEAM_SIZE = 5

# Modelo MLX (solo se usa si WHISPER_BACKEND="mlx" en Apple Silicon).
MLX_MODEL = "mlx-community/whisper-large-v3-turbo"

# Idioma forzado. None = autodetect (mas lento, puede confundir idiomas).
WHISPER_LANGUAGE = "es"

# ---------------------------------------------------------------------------
# CALIDAD del texto.
# initial_prompt: le da a Whisper un ejemplo de COMO queres que escriba.
# Sirve para fijar puntuacion, mayusculas, dialecto y la grafia de tus
# terminos/nombres propios. PERSONALIZALO con las palabras que mas usas.
# Tiene que ir bien escrito (con tildes y enie reales).
# ---------------------------------------------------------------------------
INITIAL_PROMPT = (
    "Hola, te cuento lo que estuve haciendo hoy. Transcripcion en espanol "
    "con puntuacion y mayusculas correctas. Terminos que escribo asi: "
    "Claude Code, ChatGPT, Python, GPU, prompt, API, workflow, agente de IA."
)

# condition_on_previous_text=False corta loops de repeticion y el arrastre de
# contexto entre dictados (clave en push-to-talk: cada dictado es independiente).
CONDITION_ON_PREVIOUS_TEXT = False

# Post-proceso: frases de relleno que Whisper alucina en silencios (se descartan).
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
SAMPLE_RATE = 16000   # Whisper espera 16kHz
CHANNELS = 1

# Duracion minima del apreton (segundos). Mas corto = se descarta (evita basura).
MIN_DURATION = 0.3

# Si el texto supera este largo, usa clipboard + Ctrl/Cmd+V en vez de tipeo.
TYPE_THRESHOLD_CHARS = 500

# Beep al empezar/terminar (feedback sonoro). Desactivar con False.
BEEPS_ENABLED = True
BEEP_START_FREQ = 880
BEEP_END_FREQ = 1320
BEEP_DURATION_MS = 60
BEEP_ERROR_FREQ = 440

# Separacion de parrafos: si entre dos segmentos hay un silencio mayor a este
# umbral (segundos), se inserta un doble enter (parrafo nuevo).
PARAGRAPH_PAUSE_SEC = 1.5
PARAGRAPH_SEPARATOR = "\n\n"
