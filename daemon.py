"""
Dictado por voz global tipo WhisperFlow.

Push-to-talk: manten apretada la HOTKEY (default F9) para grabar.
Solta la tecla y el texto transcripto se tipea donde tengas el cursor.

Todo local con faster-whisper en GPU (cuda/float16), fallback CPU.
Vive en la system tray. Para salir: click derecho > Salir.
"""

import os
import sys
import time
import threading
import importlib.util
import subprocess
from datetime import datetime
from pathlib import Path

_IS_MAC = sys.platform == "darwin"

# ----------------------------------------------------------------------------
# Setup CUDA DLLs (nvidia-cublas) antes de importar faster_whisper.
# Copiado de video-editor/transcriber.py:9-18 (patron ya validado).
# ----------------------------------------------------------------------------
try:
    _spec = importlib.util.find_spec("nvidia.cublas")
    if _spec and _spec.submodule_search_locations:
        _cublas_bin = os.path.join(list(_spec.submodule_search_locations)[0], "bin")
        if os.path.isdir(_cublas_bin):
            os.add_dll_directory(_cublas_bin)
            os.environ["PATH"] = _cublas_bin + os.pathsep + os.environ.get("PATH", "")
except Exception:
    pass

import numpy as np
import sounddevice as sd
from pynput import keyboard
import pyperclip
import pystray
from PIL import Image, ImageDraw

# Windows-only sound feedback
try:
    import winsound
    _HAS_WINSOUND = True
except ImportError:
    _HAS_WINSOUND = False

# Permitir ejecutar desde cualquier cwd
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

if _IS_MAC:
    try:
        from config_mac import (
            HOTKEY, WHISPER_MODEL, WHISPER_DEVICE, WHISPER_LANGUAGE,
            WHISPER_BEAM_SIZE, SAMPLE_RATE, CHANNELS, MIN_DURATION,
            TYPE_THRESHOLD_CHARS, BEEPS_ENABLED, BEEP_START_FREQ,
            BEEP_END_FREQ, BEEP_DURATION_MS, BEEP_ERROR_FREQ,
            PARAGRAPH_PAUSE_SEC, PARAGRAPH_SEPARATOR,
        )
    except ImportError:
        from config import (
            HOTKEY, WHISPER_MODEL, WHISPER_DEVICE, WHISPER_LANGUAGE,
            WHISPER_BEAM_SIZE, SAMPLE_RATE, CHANNELS, MIN_DURATION,
            TYPE_THRESHOLD_CHARS, BEEPS_ENABLED, BEEP_START_FREQ,
            BEEP_END_FREQ, BEEP_DURATION_MS, BEEP_ERROR_FREQ,
            PARAGRAPH_PAUSE_SEC, PARAGRAPH_SEPARATOR,
        )
else:
    from config import (
    HOTKEY,
    WHISPER_MODEL,
    WHISPER_DEVICE,
    WHISPER_LANGUAGE,
    WHISPER_BEAM_SIZE,
    SAMPLE_RATE,
    CHANNELS,
    MIN_DURATION,
    TYPE_THRESHOLD_CHARS,
    BEEPS_ENABLED,
    BEEP_START_FREQ,
    BEEP_END_FREQ,
    BEEP_DURATION_MS,
    BEEP_ERROR_FREQ,
    PARAGRAPH_PAUSE_SEC,
    PARAGRAPH_SEPARATOR,
)
from overlay import Overlay

# Preferencia de microfono (solo definida en config_mac.py; opcional)
try:
    from config_mac import INPUT_DEVICE_PREFERENCE
except Exception:
    INPUT_DEVICE_PREFERENCE = []

# Config opcional nueva (backend MLX + calidad). Defaults seguros si el config
# de la plataforma no las define (ej: el config.py viejo de Windows).
try:
    if _IS_MAC:
        import config_mac as _cfg
    else:
        import config as _cfg
except Exception:
    try:
        import config as _cfg
    except Exception:
        _cfg = None

def _cfgget(name, default):
    return getattr(_cfg, name, default) if _cfg is not None else default

WHISPER_BACKEND = _cfgget("WHISPER_BACKEND", "faster")
MLX_MODEL = _cfgget("MLX_MODEL", "mlx-community/whisper-large-v3-turbo")
INITIAL_PROMPT = _cfgget("INITIAL_PROMPT", None)
CONDITION_ON_PREVIOUS_TEXT = _cfgget("CONDITION_ON_PREVIOUS_TEXT", False)
HALLUCINATION_BLACKLIST = _cfgget("HALLUCINATION_BLACKLIST", [])
# Estructurar el texto en parrafos cortos legibles (no un solo choclo).
STRUCTURE_PARAGRAPHS = _cfgget("STRUCTURE_PARAGRAPHS", True)
PARAGRAPH_MAX_CHARS = _cfgget("PARAGRAPH_MAX_CHARS", 220)

# ----------------------------------------------------------------------------
# Logging
# ----------------------------------------------------------------------------
# Si existe la raiz del proyecto claudio_contenido (caso desarrollo de Facu),
# usamos logs/ ahi. Si no (distribucion standalone), usamos logs/ junto al daemon.
_project_logs = HERE.parent.parent / "logs"
if (HERE.parent.parent / "CLAUDE.md").exists():
    LOGS_DIR = _project_logs
else:
    LOGS_DIR = HERE / "logs"
LOGS_DIR.mkdir(exist_ok=True)


def log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    log_file = LOGS_DIR / f"dictado_voz_{datetime.now().strftime('%Y%m%d')}.log"
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ----------------------------------------------------------------------------
# Backend de transcripcion: MLX (GPU/Metal) con fallback a faster-whisper (CPU).
# El modelo se carga UNA vez al arrancar y se mantiene caliente (proceso vivo).
# ----------------------------------------------------------------------------
_backend: str = WHISPER_BACKEND   # se degrada a "faster" si MLX no esta disponible
_fw_model = None                  # faster-whisper WhisperModel (lazy)
_mlx_ready = False                # True cuando el modelo MLX quedo caliente en GPU
_model_lock = threading.Lock()


def _detect_device() -> tuple[str, str]:
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda", "float16"
    except Exception:
        pass
    return "cpu", "int8"


def _load_faster_whisper():
    """Carga (una vez) faster-whisper y lo deja caliente. Fallback / Windows."""
    global _fw_model
    if _fw_model is not None:
        return _fw_model
    from faster_whisper import WhisperModel
    device = WHISPER_DEVICE
    if device == "auto":
        device, compute_type = _detect_device()
    else:
        compute_type = "float16" if device == "cuda" else "int8"
    log(f"Cargando faster-whisper '{WHISPER_MODEL}' en {device}/{compute_type}...")
    t0 = time.time()
    _fw_model = WhisperModel(WHISPER_MODEL, device=device, compute_type=compute_type)
    log(f"faster-whisper cargado en {time.time() - t0:.1f}s")
    try:
        list(_fw_model.transcribe(np.zeros(SAMPLE_RATE, dtype=np.float32),
                                  language=WHISPER_LANGUAGE, beam_size=1)[0])
        log("Warm-up faster-whisper OK")
    except Exception as e:
        log(f"Warm-up faster-whisper fallo (no critico): {e}")
    return _fw_model


def _load_mlx() -> bool:
    """Importa mlx-whisper y deja el modelo caliente en la GPU. True si OK."""
    global _mlx_ready
    if _mlx_ready:
        return True
    try:
        import mlx_whisper  # noqa: F401
        log(f"Cargando modelo MLX '{MLX_MODEL}' en GPU/Metal...")
        t0 = time.time()
        # warm-up: baja el modelo (1ra vez) y lo deja cacheado/caliente en memoria
        mlx_whisper.transcribe(
            np.zeros(SAMPLE_RATE, dtype=np.float32),
            path_or_hf_repo=MLX_MODEL, language=WHISPER_LANGUAGE, fp16=True,
        )
        _mlx_ready = True
        log(f"Modelo MLX listo (GPU) en {time.time() - t0:.1f}s")
        return True
    except Exception as e:
        log(f"MLX no disponible ({e}); caigo a faster-whisper.")
        return False


def load_model() -> None:
    """Prepara el backend elegido. Se llama al arrancar (thread aparte)."""
    global _backend
    with _model_lock:
        if _backend == "mlx":
            if _load_mlx():
                return
            _backend = "faster"   # degradar limpio
        _load_faster_whisper()


# ----------------------------------------------------------------------------
# Sound feedback
# ----------------------------------------------------------------------------
def beep(freq: int) -> None:
    if not BEEPS_ENABLED:
        return
    if _HAS_WINSOUND:
        try:
            winsound.Beep(freq, BEEP_DURATION_MS)
        except Exception:
            pass
    elif _IS_MAC:
        # En Mac usamos afplay con sonidos del sistema (no bloquea)
        sound = "/System/Library/Sounds/Pop.aiff" if freq >= 1000 else "/System/Library/Sounds/Tink.aiff"
        try:
            subprocess.Popen(["afplay", sound], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass


# ----------------------------------------------------------------------------
# Estado global
# ----------------------------------------------------------------------------
class State:
    def __init__(self) -> None:
        self.recording = False
        self.paused = False
        # Capturas en paralelo: [{"name", "stream", "chunks", "primary"}]
        self.captures: list[dict] = []
        self.record_start: float = 0.0
        self.kb_controller = keyboard.Controller()
        self.tray_icon: pystray.Icon | None = None
        self.overlay: Overlay | None = None
        self.mic_name: str = "?"
        self.lock = threading.Lock()


state = State()


# ----------------------------------------------------------------------------
# Grabacion
# ----------------------------------------------------------------------------
def _make_callback(capture: dict):
    """Callback de audio para una captura especifica."""
    def _cb(indata, frames, time_info, status) -> None:
        if status:
            # Overflow / underflow no son criticos para dictado corto
            pass
        capture["chunks"].append(indata.copy())
        # Alimentar overlay con la amplitud (RMS) en tiempo real.
        # El primario siempre empuja; el fallback solo si tiene señal real,
        # para que las ondas se vean aunque el mic primario este muerto.
        if state.overlay is not None:
            try:
                rms = float(np.sqrt(np.mean(indata.astype(np.float32) ** 2)))
                # Mapear RMS (~0..0.3 hablando normal) a 0..1 con leve compresion
                amp = min(1.0, rms * 6.0)
                if capture["primary"] or amp > 0.05:
                    state.overlay.push_amplitude(amp)
            except Exception:
                pass
    return _cb


def _resolve_capture_devices() -> list[tuple]:
    """
    Mics a grabar en paralelo: [(device_idx_o_None, nombre), ...].
    1ro el default del sistema (el que el usuario este usando, ej AirPods).
    2do el primer match de INPUT_DEVICE_PREFERENCE si es OTRO device (fallback,
    porque los AirPods entregan silencio cuando se auto-cambian al iPhone).
    """
    out = []
    try:
        devices = sd.query_devices()
        default_name = None
        try:
            default_name = sd.query_devices(kind="input")["name"]
            out.append((None, default_name))
        except Exception:
            pass
        fallback = None
        for pref in INPUT_DEVICE_PREFERENCE:
            for i, d in enumerate(devices):
                if d["max_input_channels"] > 0 and pref.lower() in d["name"].lower():
                    fallback = (i, d["name"])
                    break
            if fallback:
                break
        if fallback and fallback[1] != default_name:
            out.append(fallback)
    except Exception:
        pass
    if not out:
        out = [(None, "default")]
    return out


def _open_captures() -> list[dict]:
    """Abre un stream por cada mic candidato. Reinicia PortAudio antes (Mac)."""
    if _IS_MAC:
        # CoreAudio + Bluetooth (AirPods): tras cerrar un stream, el contexto
        # PortAudio del proceso queda stale (streams que abren sin error pero
        # entregan ceros, lista de devices vieja, AUHAL invalido tras sleep).
        try:
            sd._terminate()
            sd._initialize()
        except Exception:
            pass
    captures = []
    for idx, name in _resolve_capture_devices():
        cap = {"name": name, "stream": None, "chunks": [], "primary": not captures}
        try:
            stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="float32",
                callback=_make_callback(cap),
                device=idx,
            )
            stream.start()
            cap["stream"] = stream
            captures.append(cap)
        except Exception as e:
            log(f"No pude abrir mic '{name}': {e}")
    return captures


def start_recording() -> None:
    with state.lock:
        if state.recording or state.paused:
            return
        state.record_start = time.time()
        try:
            state.captures = _open_captures()
        except Exception as e:
            log(f"Error abriendo mics: {e}")
            state.captures = []
        if not state.captures:
            log("Error abriendo mic: ningun dispositivo disponible")
            if state.overlay:
                state.overlay.hide()
            return
        state.recording = True
        if state.overlay:
            state.overlay.show_recording()


def stop_recording_and_transcribe() -> None:
    with state.lock:
        if not state.recording:
            return
        state.recording = False
        duration = time.time() - state.record_start
        captures = state.captures
        state.captures = []
        for cap in captures:
            try:
                cap["stream"].stop()
                cap["stream"].close()
            except Exception:
                pass

    if duration < MIN_DURATION:
        log(f"Descartado (apreton corto: {duration:.2f}s)")
        if state.overlay:
            state.overlay.hide()
        return

    # Elegir la captura con mas señal (RMS). Si el mic primario (ej AirPods)
    # entrego silencio, gana el fallback (mic del MacBook) y el dictado se salva.
    best_audio = None
    best_rms = -1.0
    best_name = "?"
    detalle = []
    for cap in captures:
        if not cap["chunks"]:
            detalle.append(f"{cap['name']}: sin audio")
            continue
        audio = np.concatenate(cap["chunks"], axis=0).flatten().astype(np.float32)
        rms = float(np.sqrt(np.mean(audio ** 2)))
        detalle.append(f"{cap['name']}: rms {rms:.4f}")
        if rms > best_rms:
            best_audio = audio
            best_rms = rms
            best_name = cap["name"]

    if best_audio is None:
        log(f"Sin audio capturado ({' | '.join(detalle)})")
        if state.overlay:
            state.overlay.hide()
        return

    if len(captures) > 1:
        log(f"Mic elegido: {best_name}  ({' | '.join(detalle)})")
    state.mic_name = best_name

    if state.overlay:
        state.overlay.show_transcribing()

    # Transcripcion en thread aparte para no bloquear el hotkey listener
    threading.Thread(
        target=_transcribe_and_paste,
        args=(best_audio, duration),
        daemon=True,
    ).start()


def _segments_to_text(segments) -> str:
    """
    Une segmentos (tuplas start, end, text) insertando PARAGRAPH_SEPARATOR cuando
    hay una pausa >= PARAGRAPH_PAUSE_SEC entre el fin de un segmento y el siguiente.
    """
    parts: list[str] = []
    prev_end: float | None = None
    for start, end, text in segments:
        txt = (text or "").strip()
        if not txt:
            continue
        if prev_end is not None:
            gap = start - prev_end
            parts.append(PARAGRAPH_SEPARATOR if gap >= PARAGRAPH_PAUSE_SEC else " ")
        parts.append(txt)
        prev_end = end
    return "".join(parts).strip()


def _strip_accents_lower(s: str) -> str:
    import unicodedata
    return "".join(
        c for c in unicodedata.normalize("NFD", s.lower())
        if unicodedata.category(c) != "Mn"
    )


def _postprocess(text: str) -> str:
    """Limpieza liviana: espacios, frases alucinadas de relleno, mayuscula inicial.
    NUNCA toca la grafia de palabras (sin autocorrect): respeta n8n, MLX, GPU, etc."""
    if not text:
        return text
    import re
    out_lines: list[str] = []
    for block in text.split("\n"):
        block = re.sub(r"[ \t]+", " ", block).strip()
        if not block:
            out_lines.append("")
            continue
        norm = _strip_accents_lower(block)
        # descartar bloques cortos que son solo una frase tipica alucinada
        if len(block) < 90 and any(b in norm for b in HALLUCINATION_BLACKLIST):
            continue
        out_lines.append(block)
    out = "\n".join(out_lines)
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    if out and out[0].islower():
        out = out[0].upper() + out[1:]
    if STRUCTURE_PARAGRAPHS:
        out = _structure_text(out, PARAGRAPH_MAX_CHARS)
    return out


def _structure_text(text: str, max_chars: int) -> str:
    """Reparte el texto en parrafos cortos y legibles (no un solo choclo).
    Respeta los cortes que ya existen (pausas largas -> doble enter) y dentro
    de cada bloque agrupa oraciones hasta ~max_chars, cortando en el punto/
    pregunta mas cercano. No reescribe ni recapitaliza palabras."""
    import re
    blocks = [b.strip() for b in text.split("\n\n") if b.strip()]
    out_paras: list[str] = []
    for block in blocks:
        # dividir en oraciones: despues de . ? ! … seguido de espacio
        sentences = [s.strip() for s in re.split(r"(?<=[.?!…])\s+", block) if s.strip()]
        if not sentences:
            continue
        cur = ""
        for s in sentences:
            if cur and len(cur) + 1 + len(s) > max_chars:
                out_paras.append(cur)
                cur = s
            else:
                cur = f"{cur} {s}".strip() if cur else s
        if cur:
            out_paras.append(cur)
    return "\n\n".join(out_paras)


def _transcribe(audio: np.ndarray) -> str:
    """Transcribe el audio con el backend activo (MLX->fallback faster-whisper).
    Devuelve el texto final ya con parrafos y post-proceso."""
    global _backend
    if _backend == "mlx" and _mlx_ready:
        try:
            import mlx_whisper
            r = mlx_whisper.transcribe(
                audio,
                path_or_hf_repo=MLX_MODEL,
                language=WHISPER_LANGUAGE,
                initial_prompt=INITIAL_PROMPT,
                condition_on_previous_text=CONDITION_ON_PREVIOUS_TEXT,
                word_timestamps=False,
                fp16=True,
            )
            segs = [(s.get("start", 0.0), s.get("end", 0.0), s.get("text", ""))
                    for s in r.get("segments", [])]
            return _postprocess(_segments_to_text(segs))
        except Exception as e:
            log(f"MLX transcribe fallo, caigo a faster-whisper: {e}")
            _backend = "faster"

    model = _load_faster_whisper()
    segments_iter, _info = model.transcribe(
        audio,
        language=WHISPER_LANGUAGE,
        beam_size=WHISPER_BEAM_SIZE,
        initial_prompt=INITIAL_PROMPT,
        condition_on_previous_text=CONDITION_ON_PREVIOUS_TEXT,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 300},
        word_timestamps=False,
    )
    segs = [(s.start, s.end, s.text) for s in segments_iter]
    return _postprocess(_segments_to_text(segs))


def _transcribe_and_paste(audio: np.ndarray, audio_duration: float) -> None:
    t0 = time.time()
    try:
        log(f"Mic: {state.mic_name}  amplitud max: {float(np.abs(audio).max()):.4f}")
    except Exception:
        pass
    try:
        text = _transcribe(audio)
    except Exception as e:
        log(f"Error transcribiendo: {e}")
        if state.overlay:
            state.overlay.hide()
        return

    transcribe_time = time.time() - t0

    if not text:
        log(f"Sin texto (audio {audio_duration:.1f}s, transcripcion {transcribe_time:.2f}s)")
        if state.overlay:
            state.overlay.hide()
        return

    preview = text[:80].replace("\n", " ")
    log(f"[{audio_duration:.1f}s audio / {transcribe_time:.2f}s transcribe] {preview}")

    paste_text(text)
    if state.overlay:
        state.overlay.hide()


# ----------------------------------------------------------------------------
# Pegado
# ----------------------------------------------------------------------------
def paste_text(text: str) -> None:
    # Pequeno delay para asegurar que la app focuseada este lista
    time.sleep(0.05)

    if len(text) > TYPE_THRESHOLD_CHARS or "\n" in text:
        # Clipboard + Cmd/Ctrl+V para textos largos O con saltos de linea.
        # Clave para multi-parrafo: tipear "\n" manda Enter, y en apps de chat
        # (WhatsApp, Slack) Enter ENVIA el mensaje -> lo cortaria. Pegar respeta
        # los saltos como parte del texto, en un solo mensaje.
        try:
            previous_clip = ""
            try:
                previous_clip = pyperclip.paste()
            except Exception:
                pass
            pyperclip.copy(text)
            time.sleep(0.05)
            # Mac usa Cmd+V, Windows usa Ctrl+V
            mod_key = keyboard.Key.cmd if _IS_MAC else keyboard.Key.ctrl
            state.kb_controller.press(mod_key)
            state.kb_controller.press("v")
            state.kb_controller.release("v")
            state.kb_controller.release(mod_key)
            # Restaurar clipboard previo despues de un toque
            def _restore():
                time.sleep(0.5)
                try:
                    pyperclip.copy(previous_clip)
                except Exception:
                    pass
            threading.Thread(target=_restore, daemon=True).start()
            return
        except Exception as e:
            log(f"Fallback clipboard fallo, tipeando: {e}")

    # Tipeo caracter por caracter (funciona en cualquier app, no toca clipboard).
    # Cada "\n" se tipea como Enter explicito para compatibilidad con apps que
    # no procesan "\n" como salto (Notepad clasico, algunos campos web).
    try:
        lines = text.split("\n")
        for i, chunk in enumerate(lines):
            if chunk:
                state.kb_controller.type(chunk)
            if i < len(lines) - 1:
                state.kb_controller.press(keyboard.Key.enter)
                state.kb_controller.release(keyboard.Key.enter)
    except Exception as e:
        log(f"Error tipeando: {e}")
        # Ultimo recurso: solo dejar en el portapapeles
        try:
            pyperclip.copy(text)
            log("Texto dejado en el portapapeles (Ctrl+V para pegar)")
        except Exception:
            pass


# ----------------------------------------------------------------------------
# Hotkey listener
# ----------------------------------------------------------------------------
def _parse_hotkey(spec: str):
    """Devuelve la Key/KeyCode para detectar press/release."""
    s = spec.strip().lower()
    # Tecla unica tipo "f9", "f1", "pause", "scroll_lock"
    if hasattr(keyboard.Key, s):
        return getattr(keyboard.Key, s)
    # Tecla unica caracter
    if len(s) == 1:
        return keyboard.KeyCode.from_char(s)
    # Fallback: intentar como KeyCode por nombre (puede variar por plataforma)
    try:
        return keyboard.KeyCode.from_vk(getattr(keyboard.Key, s).value.vk)
    except Exception:
        pass
    log(f"ADVERTENCIA: tecla '{spec}' no reconocida por pynput en esta plataforma. Usando f9.")
    return keyboard.Key.f9


_HOTKEY_OBJ = _parse_hotkey(HOTKEY)


def _matches_hotkey(key) -> bool:
    return key == _HOTKEY_OBJ


def _on_press(key):
    if state.paused:
        return
    if _matches_hotkey(key) and not state.recording:
        start_recording()


def _on_release(key):
    if state.paused:
        return
    if _matches_hotkey(key) and state.recording:
        stop_recording_and_transcribe()


def start_hotkey_listener() -> keyboard.Listener:
    listener = keyboard.Listener(on_press=_on_press, on_release=_on_release)
    listener.daemon = True
    listener.start()
    log(f"Hotkey listener activo. Manten apretada [{HOTKEY.upper()}] para dictar.")
    return listener


# ----------------------------------------------------------------------------
# System tray
# ----------------------------------------------------------------------------
def _make_icon_image(active: bool) -> Image.Image:
    """Genera un icono procedural si no hay icon.png disponible."""
    icon_path = HERE / "icon.png"
    if icon_path.exists():
        try:
            return Image.open(icon_path)
        except Exception:
            pass
    # Fallback: circulo de color (verde activo / gris pausado)
    size = 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    color = (34, 197, 94, 255) if active else (115, 115, 115, 255)
    draw.ellipse((4, 4, size - 4, size - 4), fill=color)
    # Microfono simplificado
    draw.rounded_rectangle((24, 16, 40, 40), radius=8, fill=(255, 255, 255, 255))
    draw.rectangle((30, 40, 34, 50), fill=(255, 255, 255, 255))
    draw.rectangle((22, 48, 42, 52), fill=(255, 255, 255, 255))
    return img


def _toggle_pause(icon, item):
    state.paused = not state.paused
    if state.paused and state.recording:
        # Si estaba grabando justo cuando pausan, abortar
        for cap in state.captures:
            try:
                cap["stream"].stop()
                cap["stream"].close()
            except Exception:
                pass
        state.recording = False
        state.captures = []
    icon.icon = _make_icon_image(active=not state.paused)
    icon.title = "Dictado por voz - Pausado" if state.paused else "Dictado por voz - Activo"
    log("Pausado" if state.paused else "Reanudado")


def _open_file(path: str) -> None:
    """Abre un archivo con el programa por defecto. Cross-platform."""
    try:
        if _IS_MAC:
            subprocess.run(["open", path], check=False)
        else:
            os.startfile(path)
    except Exception as e:
        log(f"No pude abrir {path}: {e}")


def _open_logs(icon, item):
    log_file = LOGS_DIR / f"dictado_voz_{datetime.now().strftime('%Y%m%d')}.log"
    _open_file(str(log_file))


def _open_config(icon, item):
    config_file = HERE / ("config_mac.py" if _IS_MAC else "config.py")
    _open_file(str(config_file))


def _quit(icon, item):
    log("Saliendo")
    for cap in state.captures:
        try:
            cap["stream"].stop()
            cap["stream"].close()
        except Exception:
            pass
    icon.stop()
    os._exit(0)


def build_tray() -> pystray.Icon:
    image = _make_icon_image(active=True)
    menu = pystray.Menu(
        pystray.MenuItem(
            lambda item: "Pausado" if state.paused else "Activo",
            None,
            enabled=False,
        ),
        pystray.MenuItem(
            lambda item: "Reanudar" if state.paused else "Pausar",
            _toggle_pause,
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Editar config", _open_config),
        pystray.MenuItem("Ver log de hoy", _open_logs),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Salir", _quit),
    )
    icon = pystray.Icon(
        "dictado_voz",
        image,
        title=f"Dictado por voz [{HOTKEY.upper()}]",
        menu=menu,
    )
    state.tray_icon = icon
    return icon


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------
def main() -> None:
    log("=" * 60)
    log("Dictado por voz arrancando...")
    log(f"Hotkey: {HOTKEY} (push-to-talk)")
    log(f"Modelo: {WHISPER_MODEL}  Idioma: {WHISPER_LANGUAGE}")

    # Cargar modelo en thread aparte
    threading.Thread(target=load_model, daemon=True).start()

    if _IS_MAC:
        # En Mac, tkinter (NSWindow) debe correr en el hilo principal.
        # pystray tambien requiere el hilo principal, por eso lo omitimos en Mac.
        # El overlay corre en el hilo principal via _run() directo.
        # Para salir: Ctrl+C en la terminal.
        log("Mac: overlay en hilo principal, system tray omitido. Ctrl+C para salir.")
        start_hotkey_listener()
        state.overlay = Overlay()
        log("Overlay listo.")
        try:
            state.overlay._run()  # bloquea el hilo principal con tkinter mainloop
        except KeyboardInterrupt:
            log("Ctrl+C recibido, saliendo")
            os._exit(0)
    else:
        # Overlay visual (corre en su propio thread Tk)
        state.overlay = Overlay()
        state.overlay.start()
        log("Overlay listo (arriba de la barra de tareas).")

        # Hotkey listener (thread propio, daemon)
        start_hotkey_listener()

        # System tray (en thread aparte; pystray Win32 lo soporta)
        icon = build_tray()
        tray_thread = threading.Thread(target=icon.run, daemon=True)
        tray_thread.start()
        log("System tray listo. Click derecho en el icono para opciones.")

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            log("Ctrl+C recibido, saliendo")
            os._exit(0)


if __name__ == "__main__":
    main()
