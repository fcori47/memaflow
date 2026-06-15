# 🎙️ MemaFlow

**Dictado por voz local, gratis y privado. Apretás una tecla, hablás, soltás, y el texto aparece escrito donde tengas el cursor.**

Como los dictados por voz pagos (tipo Wispr Flow), pero **100% en tu PC**: sin nube, sin APIs, sin suscripción, sin que tu voz salga de tu máquina. Anda en cualquier app — el navegador, tu editor, WhatsApp Web, o hablándole a Claude Code / ChatGPT.

Usa [Whisper](https://github.com/openai/whisper) de OpenAI corriendo **local**:
- En **Mac (Apple Silicon)** transcribe en la **GPU** con [MLX](https://github.com/ml-explore/mlx) → vuela y no calienta el CPU.
- En **Windows** usa [faster-whisper](https://github.com/SYSTRAN/faster-whisper) en la **GPU NVIDIA** (o CPU si no tenés).

---

## ¿Por qué MemaFlow?

- ⚡ **Rápido de verdad.** En un MacBook Air M3 transcribe ~10x más rápido que el tiempo real (45 segundos de audio → ~3 segundos), y **no se pone lento con las horas** porque corre en la GPU, no en el CPU.
- 🔒 **Privado.** Tu voz nunca sale de tu computadora. No hay servidor, no hay API, no hay cuenta.
- 💸 **Gratis y para siempre.** Software libre (MIT). Cero suscripción.
- ✍️ **Escribe bien.** Puntuación, mayúsculas y signos `¿?` correctos. Le podés enseñar tus palabras (nombres propios, términos técnicos) para que no las escriba mal.
- 📑 **Texto ordenado, no un choclo.** Aunque hables seguido, te separa el dictado en **párrafos cortos y legibles**. Listo para pegar en WhatsApp, Notion o un mail — y entra como un solo mensaje, sin cortarse.
- 🌎 **Pensado para el español** (incluido el voseo argentino), pero configurable a cualquier idioma de Whisper.

---

## 🚀 Instalación

### Mac (Apple Silicon: M1/M2/M3/M4)

```bash
git clone https://github.com/fcori47/MemaFlow.git
cd MemaFlow
chmod +x install_mac.sh iniciar_dictado_mac.sh
./install_mac.sh
./iniciar_dictado_mac.sh
```

La primera vez, macOS te va a pedir permisos (una sola vez):
1. **Ajustes del Sistema → Privacidad y Seguridad → Accesibilidad** → permitir (para que pueda "tipear" por vos).
2. **Ajustes del Sistema → Privacidad y Seguridad → Micrófono** → permitir.

### Windows (NVIDIA o CPU)

1. Instalá [Python 3.10+](https://www.python.org/downloads/) (tildá **"Add Python to PATH"**).
2. Doble clic en `install.bat` (crea el entorno e instala todo).
3. Doble clic en `iniciar_dictado.bat`.

Con GPU NVIDIA usa el modelo `large-v3-turbo`. Sin GPU, cambiá en `config.py` a `WHISPER_MODEL = "small"`.

---

## 🎧 Cómo se usa

1. Hacé clic donde quieras escribir.
2. **Mantené apretada `F9`** y hablá.
3. **Soltá** `F9` → el texto aparece escrito.

Mientras grabás aparece una **pastilla con la onda de tu voz** (en Mac, abajo en el centro). Si hacés una pausa larga entre frases, te separa en párrafos solo.

> Para cambiar la tecla, editá `HOTKEY` en `config.py` (Windows) o `config_mac.py` (Mac). Opciones: `"f8"`, `"f10"`, `"pause"`, `"insert"`, etc.

---

## ⚙️ Personalización

Todo se configura en `config.py` (Windows) o `config_mac.py` (Mac):

| Qué | Variable |
|---|---|
| Tecla | `HOTKEY` |
| Idioma | `WHISPER_LANGUAGE` (`"es"`, `"en"`, …) |
| Modelo | `WHISPER_MODEL` / `MLX_MODEL` |
| **Tus palabras** | `INITIAL_PROMPT` |
| Separar párrafos | `PARAGRAPH_PAUSE_SEC` |

**El truco de calidad más útil:** editá `INITIAL_PROMPT` y meté ahí los nombres y términos que más usás, bien escritos. Whisper los toma como ejemplo y deja de escribirlos mal. Ej: `"... Términos que escribo así: Claude Code, n8n, Kubernetes, mi-empresa, fulanito."`

---

## 🔁 Que arranque solo al prender la PC

- **Mac:** Ajustes del Sistema → General → **Ítems de inicio** → `+` → elegí `iniciar_dictado_mac.sh`.
- **Windows:** `Win + R` → escribí `shell:startup` → pegá un acceso directo a `iniciar_dictado.bat`.

---

## 🧠 ¿Cómo funciona por dentro?

```
Apretás F9  →  graba el micrófono  →  soltás  →  Whisper transcribe (local, en GPU)
            →  limpia el texto (puntúa, saca alucinaciones)  →  lo "tipea" donde estés
```

- **Mac:** `mlx-whisper` con `whisper-large-v3-turbo` en Metal (GPU). No toca el CPU → no hay thermal throttling.
- **Windows/Linux:** `faster-whisper` (CTranslate2) en CUDA o CPU.
- El modelo se carga **una sola vez** al arrancar y queda caliente, así cada dictado es instantáneo.

---

## 🩹 Problemas comunes

- **`F9` no hace nada:** otra app lo está usando. Cambiá `HOTKEY` a `f8`/`f10`/`pause`.
- **Mac, no escribe nada:** falta el permiso de **Accesibilidad** (Ajustes → Privacidad y Seguridad).
- **Va lento en Windows:** no tenés GPU NVIDIA → usá `WHISPER_MODEL = "small"` o `"medium"`.
- **Escribe frases raras en los silencios:** subí `MIN_DURATION` o agregá la frase a `HALLUCINATION_BLACKLIST`.

---

## 📄 Licencia

MIT. Hacé lo que quieras con esto.

Hecho por **Facundo Corengia** — *El Dios de la IA*. Si te sirve, contá que lo usás 🙌
