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

# Anti-bucle del decoder: evita que repita un n-grama de este tamaño en la misma
# ventana (mata "abrimos la terminal abrimos la terminal..."). 3 = seguro. NO usar
# 2 (bloquearia repeticiones legitimas como "muy muy bueno"). 0 = desactivado.
WHISPER_NO_REPEAT_NGRAM = 3
# Hotwords: sesga el reconocimiento hacia estos terminos raros/propios durante el
# decoding (complementa INITIAL_PROMPT). Coma-separado. "" para desactivar.
WHISPER_HOTWORDS = "n8n, Basdonax, Claude Code, GHL, Chatwoot, Corengia"

# Modelo MLX (solo se usa si WHISPER_BACKEND="mlx" en Apple Silicon).
MLX_MODEL = "mlx-community/whisper-large-v3-turbo"

# Idioma forzado. None = autodetect (mas lento, puede confundir idiomas).
WHISPER_LANGUAGE = "es"

# ---------------------------------------------------------------------------
# Microfono. El daemon graba el device default del sistema + el primer match
# de esta lista (en paralelo) y se queda con el que tenga señal real. Util
# cuando el default de Windows es un device virtual (ej MOTIV Mix de Shure)
# que entrega silencio. Dejar [] para usar solo el default del sistema.
# ---------------------------------------------------------------------------
INPUT_DEVICE_PREFERENCE = ["Shure MV7", "Shure", "Logi C270", "C270", "WebCam"]

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

# Estructurar la salida en parrafos cortos y legibles (no un solo choclo gigante).
# True = agrupa oraciones hasta PARAGRAPH_MAX_CHARS y separa con linea en blanco.
# Ideal para pegar en WhatsApp/Notion/mail. False = texto corrido.
STRUCTURE_PARAGRAPHS = True
PARAGRAPH_MAX_CHARS = 220

# ---------------------------------------------------------------------------
# REFINAMIENTO (v3) - pule el dictado como contenido (saca muletillas, resuelve
# autocorrecciones, puntua). Local y gratis. Ver refine.py.
#   "rules"  -> limpieza por CODIGO, determinista. Instantaneo, sin instalar nada,
#               nunca cambia el sentido ni inventa palabras. DEFAULT/RECOMENDADO.
#   "auto"   -> usa Ollama (LLM local) si esta corriendo; si no, cae a reglas.
#   "ollama" -> fuerza Ollama (cae a reglas si falla). Mas prolijo pero mas lento
#               y un modelo chico a veces cambia el sentido. Necesita: ollama pull qwen2.5:3b
#   "off"    -> no refina (comportamiento v2).
# ---------------------------------------------------------------------------
REFINE_BACKEND = "rules"
REFINE_MODEL = "qwen2.5:3b"
REFINE_OLLAMA_URL = "http://localhost:11434"
REFINE_TIMEOUT = 20.0          # segundos max que espera al LLM antes de caer a reglas
# Cuanto queda el modelo caliente en la GPU tras un dictado. "30m" cubre una
# sesion de trabajo sin recargar. "-1" = siempre (ocupa VRAM fija). "0" = descarga ya.
REFINE_KEEP_ALIVE = "30m"

# (v3.1) Formatear segun la app en foco (mail formal, chat casual, codigo intacto).
# Estilo "context-aware" de Glaido. Default False para no sumar latencia/variabilidad.
REFINE_USE_APP_CONTEXT = False

# Muletillas EXTRA para el modo reglas (ademas de las base de refine.py).
# Sumá las tuyas. Conservador: solo palabras que casi nunca son contenido real.
REFINE_FILLERS = []

# Terminos EXTRA para forzar grafia (ademas de los base: Claude Code, n8n, etc.).
# Clave = como lo escribe mal Whisper (en minuscula), valor = grafia correcta.
# Ej: {"das dach": "Das Dach", "zaylie": "Zaylie", "hermes": "Hermes"}
REFINE_TERMS = {}
# Siglas EXTRA a poner en mayuscula (ademas de API, GPU, PDF, etc.).
REFINE_UPPERCASE = []
# Agregar signos de apertura ¿ ¡ que Whisper omite en español. True = recomendado.
REFINE_SPANISH_MARKS = True

# --- Cuanto MODIFICA (vs solo dejar lindo) ---
# Por DEFAULT MemaFlow solo LIMPIA (muletillas, repeticiones, puntuacion, mayusculas,
# signos) y NO cambia palabras. Estas 3 SI cambian/borran texto -> default OFF.
# Corrige marcas/jerga y siglas ("cloud code"->"Claude Code", "api"->"API"). ON (lo quiere Facu).
REFINE_DICTIONARY = True
# Resuelve autocorrecciones ("el lunes, no, el martes" -> "el martes"). BORRA la 1ra version.
REFINE_AUTOCORRECT = False
# Convierte "veinte por ciento" -> "20%". Cambia palabras por numeros.
REFINE_PERCENT = False

# OPT-IN (default OFF). Comandos de puntuacion dictada: "coma"->",", "punto"->".",
# "nueva linea"->salto, "punto y aparte"->parrafo. OJO: "punto"/"coma" son palabras
# comunes; activar SOLO si dictas la puntuacion a proposito (si no, da falsos positivos).
REFINE_SPOKEN_PUNCT = False
# OPT-IN (default OFF). Detecta preguntas cuando Whisper NO puso "?" (arranca con
# que/como/cuando/donde tildado y no es pregunta indirecta). Conservador, pero puede
# fallar en bordes -> queda opcional.
REFINE_DETECT_QUESTIONS = False
