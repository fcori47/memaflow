"""
MemaFlow v3 - Refinamiento del dictado (local y gratis).

Toma el texto que sale de Whisper (ya limpio de formato por _postprocess) y lo
PULE como contenido: saca muletillas (eh, este, o sea), arregla cuando te
corregis a media frase (falsos arranques), puntua y separa en parrafos.

Filosofia MemaFlow: todo local, sin nube, sin API paga, y degrada solo.
  - backend "auto"  -> usa un LLM local via Ollama si esta corriendo; si no,
                       cae a limpieza por reglas (cero instalacion).
  - backend "ollama"-> fuerza Ollama (con fallback a reglas si falla).
  - backend "rules" -> solo reglas (instantaneo, sin LLM).
  - backend "off"   -> no refina (devuelve el texto tal cual).

GARANTIA: el refinamiento NUNCA arruina un dictado. Si el LLM devuelve algo
vacio, mucho mas largo (alucino) o mucho mas corto (se comio contenido), se
descarta y se devuelve el texto original.

Sin dependencias nuevas: solo stdlib (urllib, json, re, ctypes en Windows).
"""

import re
import json
import unicodedata
import urllib.request

# Muletillas que casi NUNCA son contenido real -> se sacan en cualquier posicion.
_FILLERS_ALWAYS = [
    "eh", "ehh", "ehhh", "em", "emm", "mmm", "mm", "uh", "o sea", "osea",
]
# Muletillas ambiguas (a veces son palabra real, ej "este lunes", "un tipo de") ->
# solo se sacan cuando estan AISLADAS: al inicio de oracion + coma, entre comas,
# o colgadas antes de un punto. Nunca en medio de la frase.
_FILLERS_DELIMITED = [
    "este", "esto", "bueno", "nada", "viste", "viste que", "digamos", "a ver",
    "mira", "mirá", "tipo", "como que", "por así decirlo", "que sé yo", "no sé",
    "dale", "obvio", "che",
]
# Determinantes/preposiciones para detectar correcciones paralelas ("el lunes, no, el martes").
_DET = r"(?:el|la|los|las|un|una|unos|unas|al|a|en|de|del|lo|mi|tu|su|este|esta|ese|esa|esos|esas)"

# Diccionario de terminos: Whisper transcribe mal marcas/jerga tecnica ("cloud code",
# "chat gpt", siglas en minuscula) -> se fuerza la grafia canonica. Es el "custom
# dictionary" de Glaido/Wispr, gratis. Multi-palabra y casos especificos PRIMERO
# (el orden importa: dict mantiene orden de insercion). Ampliable desde config.
_TERMS_DEFAULT = {
    # variantes con que Whisper destroza "Claude" (lo escucha como "cloud/claud")
    "cloud code": "Claude Code", "claud code": "Claude Code",
    "clod code": "Claude Code", "clode code": "Claude Code",
    "closed code": "Claude Code", "cloud cod": "Claude Code",
    "claude code": "Claude Code",
    "chat gpt": "ChatGPT", "chatgpt": "ChatGPT",
    "open ai": "OpenAI", "openai": "OpenAI",
    "ene ocho ene": "n8n", "n8 n": "n8n", "n8n": "n8n",
    "you tube": "YouTube", "youtube": "YouTube",
    "tik tok": "TikTok", "tiktok": "TikTok",
    "linked in": "LinkedIn", "linkedin": "LinkedIn",
    "whats app": "WhatsApp", "whatsapp": "WhatsApp",
    "git hub": "GitHub", "github": "GitHub",
    "claude": "Claude", "anthropic": "Anthropic", "gpt": "GPT",
    "python": "Python", "ollama": "Ollama", "obsidian": "Obsidian",
    "notion": "Notion", "instagram": "Instagram", "basdonax": "Basdonax",
    "memaflow": "MemaFlow", "whisper": "Whisper", "windows": "Windows",
    "google": "Google",
}
# Siglas que van SIEMPRE en mayuscula (Whisper las escribe en minuscula).
_UPPER_DEFAULT = [
    "api", "gpu", "cpu", "ram", "pdf", "html", "css", "sql", "json", "url",
    "crm", "erp", "mcp", "sdk", "ui", "ux", "llm", "usb",
]

# Cache del estado de Ollama por proceso (None = sin chequear todavia).
_OLLAMA_OK = None


def _strip_accents_lower(s):
    """minusculas y sin tildes, para comparar/normalizar (no se devuelve al usuario)."""
    return "".join(
        c for c in unicodedata.normalize("NFD", s.lower())
        if unicodedata.category(c) != "Mn"
    )


# ---------------------------------------------------------------------------
# Deteccion de la app en foco (opcional, v3.1 estilo Glaido "context-aware").
# Devuelve el titulo de la ventana activa (ej "... - Gmail", "WhatsApp",
# "Visual Studio Code"). Solo Windows por ahora; None en otros SO.
# ---------------------------------------------------------------------------
def active_app():
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return None
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value or None
    except Exception:
        return None


def _tono_para_app(app):
    """Pista de tono segun la app en foco. No inventa estructura (ni saludos),
    solo orienta el registro. Devuelve "" si no hay contexto."""
    if not app:
        return ""
    a = app.lower()
    if any(k in a for k in ("gmail", "outlook", "mail", "correo")):
        return "Destino: un correo. Registro claro y prolijo, sin inventar saludo ni firma."
    if any(k in a for k in ("whatsapp", "telegram", "slack", "discord", "messenger")):
        return "Destino: un chat. Registro casual y directo, frases cortas."
    if any(k in a for k in ("code", "visual studio", "cursor", "terminal", "powershell", "vim")):
        return "Destino: un editor de codigo. Manten intactos los terminos tecnicos y nombres de funciones/variables."
    if any(k in a for k in ("notion", "obsidian", "docs", "word", "documento")):
        return "Destino: un documento. Registro ordenado, parrafos claros."
    return ""


# ---------------------------------------------------------------------------
# Modo REGLAS: limpieza sin IA. Instantaneo, cero dependencias, conservador.
# No reescribe ni toca la grafia: solo saca muletillas aisladas y normaliza
# espacios/puntuacion. No intenta resolver autocorrecciones (eso es del LLM).
# ---------------------------------------------------------------------------
def _remove_fillers(text, extra):
    delimited = _FILLERS_DELIMITED + list(extra or [])
    for f in _FILLERS_ALWAYS:
        text = re.sub(r"(?i)\b" + re.escape(f) + r"\b[ ,]*", " ", text)
    for f in delimited:
        fp = re.escape(f)
        # al inicio de oracion + coma:  "Bueno, te cuento"  ->  "Te cuento"
        # (^\s* tolera espacios que dejo el filtro anterior, ej tras sacar "eh")
        text = re.sub(r"(?i)(^\s*|[.?!]\s+)" + fp + r"\s*,\s*", r"\1", text)
        # entre comas:  ", viste, "  ->  ", "
        text = re.sub(r"(?i),\s*" + fp + r"\s*,", ",", text)
        # aislada por coma antes de un punto:  "perfecto, viste."  ->  "perfecto."
        # (exige coma: asi "muy bueno." / "no hay nada." NO se tocan)
        text = re.sub(r"(?i),\s*" + fp + r"\s*([.?!])", r"\1", text)
    return text


def _fix_autocorrections(text):
    # (a) Correccion paralela: "UNIDAD, [no|mejor dicho|...], UNIDAD"  ->  2da UNIDAD.
    #     UNIDAD = "<det> palabra" (el lunes) o adverbio de tiempo (hoy, mañana).
    #     Cubre "mandalo el lunes, no, el martes" -> "mandalo el martes" y
    #     "hoy, no, mañana" -> "mañana". Se queda SIEMPRE con la version FINAL.
    unit = r"(?:" + _DET + r"\s+[\wáéíóúñ]+|hoy|mañana|manana|ayer|anteayer)"
    # cadena de marcadores: absorbe "no, mejor dicho," como un solo bloque.
    marc = (r"(?:(?:no|mejor dicho|mejor|perd[oó]n|perdon|digo|quise decir|"
            r"quer[ií]a decir|queria decir|o mejor)\s*,?\s*)+")
    pat = re.compile(r"(?i)\b(" + unit + r")\s*,\s*" + marc + r"(" + unit + r")")
    text = pat.sub(lambda m: m.group(2), text)
    # (b) Marcador inequivoco entre comas:  ", X, mejor dicho, "  ->  ", "
    #     (solo si X esta delimitado por comas: contexto seguro, no rompe nada).
    marc2 = r"(?:mejor dicho|perd[oó]n|perdon|digo|quise decir|quer[ií]a decir|queria decir)"
    text = re.sub(r"(?i),\s*[^,.?!]+?\s*,\s*" + marc2 + r"\s*,\s*", ", ", text)
    return text


# Palabras que SI pueden repetirse legitimamente (enfasis), no son tartamudeo.
_REPEAT_OK = {"muy", "no", "si", "sí", "ya", "casi", "tan", "re", "bien", "mal", "tan"}


def _collapse_repeats(text):
    # palabra repetida inmediata por titubeo:  "el el martes" -> "el martes".
    # Pero respeta el enfasis: "muy muy bueno" (2x de un intensificador) se queda;
    # 3+ repeticiones SIEMPRE se colapsan (eso ya es tartamudeo/alucinacion).
    def repl(m):
        word = m.group(1)
        count = len(m.group(0).split())
        if count == 2 and word.lower() in _REPEAT_OK:
            return m.group(0)
        return word
    return re.sub(r"(?i)\b(\w+)(\s+\1\b)+", repl, text)


def _fix_punct(text):
    text = re.sub(r"\s+([,.;:!?…])", r"\1", text)         # espacio antes de signo
    text = re.sub(r"([,;:])(?=[^\s\d])", r"\1 ", text)    # espacio despues de , ; : (no en 1,000 / 12:30)
    text = re.sub(r"([¿¡])\s+", r"\1", text)              # sin espacio tras ¿ ¡
    text = re.sub(r"(\s*,){2,}", ",", text)               # comas repetidas
    text = re.sub(r"\s*,\s*([.?!])", r"\1", text)          # coma colgada antes de punto
    text = re.sub(r"[ \t]{2,}", " ", text)                # espacios multiples
    text = re.sub(r"([.?!]\s+[¿¡]?)([a-zñáéíóúü])",        # mayuscula tras . ? ! (y ¿¡)
                  lambda m: m.group(1) + m.group(2).upper(), text)
    return text


def _apply_dictionary(text, terms, uppercase):
    """Fuerza la grafia canonica de marcas/jerga ("cloud code" -> "Claude Code")
    y pone siglas en mayuscula ("api" -> "API"). Respeta limites de palabra, asi
    no toca palabras que contengan la sigla. Idempotente."""
    for wrong, right in terms.items():
        text = re.sub(r"(?i)\b" + re.escape(wrong) + r"\b", right, text)
    for s in uppercase:
        text = re.sub(r"(?i)\b" + re.escape(s) + r"\b", s.upper(), text)
    return text


def _fix_spanish_marks(text):
    """Agrega los signos de apertura ¿ ¡ que Whisper suele omitir en español.
    Conservador: solo si la oracion cierra con ? o ! y no tiene ya el de apertura."""
    out = []
    for sent in re.split(r"(?<=[.?!…])\s+", text):
        c = sent.strip()
        if not c:
            continue
        if c.endswith("?") and "¿" not in c:
            c = "¿" + c
        elif c.endswith("!") and "¡" not in c:
            c = "¡" + c
        out.append(c)
    return " ".join(out)


_SOUND_TAG = re.compile(
    r"[\[(]\s*(m[úu]sica|risas|aplausos|silencio|ru[íi]do|tos|suspiro|inaudible)\s*[\])]",
    re.I)


def _strip_sound_tags(text):
    # saca etiquetas de sonido que mete Whisper: [musica], (risas), [aplausos]
    return _SOUND_TAG.sub("", text)


def _collapse_sentence_loops(text):
    # colapsa oraciones consecutivas IDENTICAS (alucinacion en loop), >=3 palabras
    parts = re.split(r"(?<=[.?!])\s+", text)
    out, prev = [], None
    for p in parts:
        norm = _strip_accents_lower(re.sub(r"[^\w\s]", "", p)).strip()
        if norm and norm == prev and len(norm.split()) >= 3:
            continue
        out.append(p)
        prev = norm
    return " ".join(out)


_PERCENT_WORDS = {
    "cero": 0, "uno": 1, "dos": 2, "tres": 3, "cuatro": 4, "cinco": 5, "seis": 6,
    "siete": 7, "ocho": 8, "nueve": 9, "diez": 10, "once": 11, "doce": 12,
    "trece": 13, "catorce": 14, "quince": 15, "dieciseis": 16, "diecisiete": 17,
    "dieciocho": 18, "diecinueve": 19, "veinte": 20, "veinticinco": 25,
    "treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60, "setenta": 70,
    "ochenta": 80, "noventa": 90, "cien": 100, "ciento": 100,
}


def _percent_words(text):
    # "veinte por ciento" -> "20%";  "20 por ciento" -> "20%"
    def repl(m):
        n = _PERCENT_WORDS.get(_strip_accents_lower(m.group(1)))
        return f"{n}%" if n is not None else m.group(0)
    text = re.sub(r"(?i)\b(" + "|".join(_PERCENT_WORDS) + r")\s+por\s+ciento\b", repl, text)
    text = re.sub(r"\b(\d+)\s+por\s+ciento\b", r"\1%", text)
    return text


def _fix_stutter(text):
    # falso arranque "c- como" / "pe- pero" -> "como" / "pero".
    # Solo si el fragmento (1-3 letras) es prefijo de la palabra que sigue
    # (asi NO toca "e-mail", "ex-novia": "mail"/"novia" no empiezan con "e"/"ex").
    def repl(m):
        a, b = m.group(1), m.group(2)
        return b if b.lower().startswith(a.lower()) else m.group(0)
    return re.sub(r"(?i)\b([a-zñáéíóúü]{1,3})-\s*([a-zñáéíóúü]+)", repl, text)


# Conectores que piden coma al arrancar la oracion (lista CERRADA = seguro).
_CONNECTORS = [
    "sin embargo", "no obstante", "por lo tanto", "por ende", "es decir",
    "por ejemplo", "en resumen", "en conclusion", "por otro lado", "de hecho",
]


def _fix_connectors(text):
    for c in _CONNECTORS:
        text = re.sub(
            r"(?i)(^|[.?!]\s+)(" + re.escape(c) + r")\s+(?=[a-zñáéíóúü0-9])",
            lambda m: m.group(1) + m.group(2)[0].upper() + m.group(2)[1:] + ", ", text)
    # coma antes de "pero" (solo pero; idempotente: no duplica si ya hay coma)
    text = re.sub(r"(?<=[a-zñáéíóúü])\s+pero\b", ", pero", text)
    return text


def _spoken_commands(text):
    # comandos de puntuacion dictada (OPT-IN). El orden importa: lo especifico primero.
    reps = [
        (r"(?i)\bnuevo\s+p[áa]rrafo\b", "\n\n"),
        (r"(?i)\bnueva\s+l[íi]nea\b", "\n"),
        (r"(?i)\bpunto\s+y\s+aparte\b", ".\n\n"),
        (r"(?i)\bpunto\s+y\s+seguido\b", ". "),
        (r"(?i)\bsigno\s+de\s+pregunta\b", "?"),
        (r"(?i)\bpunto\s+y\s+coma\b", ";"),
        (r"(?i)\bdos\s+puntos\b", ":"),
        (r"(?i)\bcoma\b", ","),
        (r"(?i)\bpunto\b", "."),
    ]
    for pat, rep in reps:
        text = re.sub(pat, rep, text)
    return text


_Q_WORDS = r"(?:qu[ée]|qui[ée]n|c[óo]mo|cu[áa]ndo|d[óo]nde|cu[áa]l|cu[áa]nto[s]?|por\s+qu[ée])"
_Q_STOP = re.compile(r"(?i)^(no\s+s[ée]|sab[ée]s|deci|contame|cont[áa]|explic[áa]|"
                     r"mostr[áa]|fij[áa]te|verific[áa]|pregunt)")


def _detect_questions(text):
    # OPT-IN: agrega ¿...? cuando Whisper NO puso el signo y la oracion arranca con
    # interrogativo tildado y NO es pregunta indirecta ("no se que hacer").
    out = []
    for sent in re.split(r"(?<=[.?!…])\s+", text):
        c = sent.strip()
        if c and not c.endswith(("?", "!")) and "¿" not in c:
            body = c.rstrip(".")
            if re.match(r"(?i)^" + _Q_WORDS + r"\b", body) and not _Q_STOP.search(body):
                c = "¿" + body + "?"
        out.append(c)
    return " ".join(out)


def _clean_rules(text, extra_fillers, terms, uppercase, spanish_marks,
                 spoken_punct=False, detect_questions=False,
                 autocorrect=False, dictionary=False, percent=False):
    """Limpieza determinista (sin LLM). Por DEFAULT solo COSMETICO (no cambia
    palabras): etiquetas de sonido, muletillas, repeticiones (palabra y frase),
    tartamudeo, comas de conectores, puntuacion y signos español.
    Lo que CAMBIA/BORRA palabras va detras de flags (default off): autocorrect
    (autocorrecciones), dictionary (terminos/siglas), percent (porcentajes)."""
    if not text:
        return text
    out_lines = []
    for line in text.split("\n"):
        s = _strip_sound_tags(line)
        if spoken_punct:
            s = _spoken_commands(s)
        s = _remove_fillers(s, extra_fillers)
        if autocorrect:
            s = _fix_autocorrections(s)
        s = _collapse_repeats(s)
        s = _collapse_sentence_loops(s)
        s = _fix_stutter(s)
        if percent:
            s = _percent_words(s)
        if dictionary:
            s = _apply_dictionary(s, terms, uppercase)
        s = _fix_connectors(s)
        s = _fix_punct(s)
        if detect_questions:
            s = _detect_questions(s)
        if spanish_marks:
            s = _fix_spanish_marks(s)
        s = s.strip()
        # mayuscula en la primera letra real (tolera ¿ ¡ al inicio)
        s = re.sub(r"^([¿¡]?\s*)([a-zñáéíóúü])",
                   lambda m: m.group(1) + m.group(2).upper(), s)
        out_lines.append(s)
    return "\n".join(out_lines)


# ---------------------------------------------------------------------------
# Modo OLLAMA: refinamiento con LLM local. La magia.
# ---------------------------------------------------------------------------
def _ollama_up(url, timeout=1.5):
    global _OLLAMA_OK
    if _OLLAMA_OK is not None:
        return _OLLAMA_OK
    try:
        req = urllib.request.Request(url.rstrip("/") + "/api/tags")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            _OLLAMA_OK = (r.status == 200)
    except Exception:
        _OLLAMA_OK = False
    return _OLLAMA_OK


def warm(model, ollama_url="http://localhost:11434", keep_alive="30m",
         timeout=180, log=print):
    """Precarga el modelo en la GPU (sin generar) y lo deja caliente. Llamar al
    arrancar el daemon, en thread aparte. Asi el PRIMER dictado ya lo encuentra
    cargado y no paga el arranque en frio (los famosos 72s del modelo grande)."""
    if not _ollama_up(ollama_url):
        return False
    try:
        # Calentamos con el system prompt REAL (no vacio): asi Ollama no solo
        # carga el modelo en GPU sino que ademas cachea la evaluacion del prompt
        # fijo, y el PRIMER dictado del usuario ya sale rapido (no a 16s).
        sistema, _ = _build_prompt("hola", None, "es")
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": sistema},
                {"role": "user", "content": "hola"},
            ],
            "stream": False,
            "keep_alive": keep_alive,
            "options": {"num_predict": 4, "temperature": 0.0},
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            ollama_url.rstrip("/") + "/api/chat",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as r:
            r.read()
        log(f"[refine] modelo {model} precargado y caliente (prompt cacheado)")
        return True
    except Exception as e:
        log(f"[refine] no pude precalentar {model}: {e}")
        return False


def _build_prompt(text, app, language):
    tono = _tono_para_app(app)
    sistema = (
        "Sos un editor de dictado por voz. Recibis una transcripcion cruda en "
        "espanol rioplatense (voseo) y la devolves PULIDA, sin cambiar lo que la "
        "persona quiso decir.\n"
        "Reglas:\n"
        "1. Saca muletillas y relleno: eh, em, este, o sea, viste, tipo, digamos, nada, a ver.\n"
        "2. Falsos arranques: si la persona se corrige a media frase (por ejemplo "
        "'mandalo el lunes, no, el martes'), deja SOLO la version final ('mandalo el martes').\n"
        "3. Corregi puntuacion, mayusculas y tildes. Separa en parrafos cortos si hace falta.\n"
        "4. NO agregues informacion, NO resumas, NO opines, NO traduzcas, NO inventes nada.\n"
        "5. Manten el tono y el sentido. Preserva TAL CUAL terminos tecnicos y nombres "
        "propios (Claude Code, n8n, ChatGPT, Python, GPU, API, Basdonax).\n"
        "6. Responde UNICAMENTE con el texto pulido. Sin comillas, sin titulos, sin "
        "explicaciones, sin decir 'aca tenes'.\n"
    )
    if tono:
        sistema += f"7. {tono}\n"
    return sistema, text


def _refine_ollama(text, model, url, timeout, app, language, log, keep_alive, max_tokens):
    sistema, usuario = _build_prompt(text, app, language)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": sistema},
            {"role": "user", "content": usuario},
        ],
        "stream": False,
        # keep_alive: cuanto tiempo queda el modelo caliente en la GPU tras
        # responder (asi el proximo dictado no paga la carga en frio).
        "keep_alive": keep_alive,
        # num_predict: tope de tokens. Un dictado refinado no deberia exceder
        # esto; evita que el modelo divague y acota la latencia.
        "options": {"temperature": 0.1, "top_p": 0.9, "num_predict": max_tokens},
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url.rstrip("/") + "/api/chat",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        resp = json.loads(r.read().decode("utf-8"))
    out = (resp.get("message", {}) or {}).get("content", "") or ""
    return out.strip()


# ---------------------------------------------------------------------------
# Guardarrail: el refinado tiene que parecerse al original. Si no, descartar.
# ---------------------------------------------------------------------------
def _strip_wrapping_quotes(s):
    s = s.strip()
    if len(s) >= 2 and s[0] in "\"'`" and s[-1] in "\"'`":
        s = s[1:-1].strip()
    return s


def _sanity_ok(original, refined):
    if not refined:
        return False
    o = len(original)
    n = len(refined)
    if o == 0:
        return False
    # alucino / explico de mas, o se comio el contenido
    if n > o * 1.7 + 50:
        return False
    if n < o * 0.35:
        return False
    return True


# ---------------------------------------------------------------------------
# API publica
# ---------------------------------------------------------------------------
def refine(text, *, backend="auto", model="qwen2.5:3b",
           ollama_url="http://localhost:11434", timeout=20.0,
           app=None, language="es", extra_fillers=None, log=print,
           keep_alive="30m", max_tokens=512,
           extra_terms=None, extra_uppercase=None, spanish_marks=True,
           spoken_punct=False, detect_questions=False,
           dictionary=False, autocorrect=False, percent=False):
    """Devuelve el texto refinado. NUNCA tira excepcion ni devuelve vacio si el
    input no era vacio: ante cualquier problema, vuelve al texto original."""
    if not text or backend == "off":
        return text

    fillers = list(extra_fillers or [])
    terms = {**_TERMS_DEFAULT, **(extra_terms or {})}
    uppercase = _UPPER_DEFAULT + list(extra_uppercase or [])

    # Resolver que backend usar realmente
    use = backend
    if backend == "auto":
        use = "ollama" if _ollama_up(ollama_url) else "rules"

    if use == "rules":
        try:
            return _clean_rules(text, fillers, terms, uppercase, spanish_marks,
                                spoken_punct, detect_questions,
                                autocorrect, dictionary, percent) or text
        except Exception as e:
            log(f"[refine] reglas fallo: {e}")
            return text

    # use == "ollama"
    try:
        out = _refine_ollama(text, model, ollama_url, timeout, app, language, log,
                             keep_alive, max_tokens)
        out = _strip_wrapping_quotes(out)
        if _sanity_ok(text, out):
            return out
        log("[refine] salida del LLM rara (sanity check), uso reglas")
    except Exception as e:
        log(f"[refine] Ollama fallo ({e}); caigo a reglas")
        # si fallo el request, marcar Ollama caido para no reintentar cada vez
        global _OLLAMA_OK
        _OLLAMA_OK = False

    try:
        return _clean_rules(text, fillers) or text
    except Exception:
        return text


if __name__ == "__main__":
    # Prueba rapida:  python refine.py
    demo = ("eh, bueno, te cuento, o sea, hoy estuve, este, armando el agente, "
            "no, mejor dicho, el workflow de n8n viste y quedo andando tipo "
            "perfecto. mandaselo al cliente el lunes, no, el martes mejor.")
    print("--- CRUDO ---")
    print(demo)
    print("\n--- REGLAS ---")
    print(refine(demo, backend="rules"))
    print("\n--- AUTO (Ollama si esta) ---")
    print(refine(demo, backend="auto"))
