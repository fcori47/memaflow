"""
Overlay flotante del dictado por voz.

- Windows: pill de tkinter con ondas (clase OverlayTk).
- macOS:   pill NATIVA (NSPanel + pyobjc) con esquinas y transparencia reales,
           estilo indicador de dictado de macOS / Wispr Flow (clase OverlayMac).

Ambas exponen la MISMA API publica para que daemon.py no cambie:
    start(), show_recording(), show_transcribing(), hide(), push_amplitude(amp), _run()

Estados:
  IDLE          - oculto
  RECORDING     - visible, barras siguen el volumen del mic
  TRANSCRIBING  - visible, barras en pulse suave ambar
"""

from __future__ import annotations

import math
import sys
import threading
import time
from collections import deque

_IS_MAC = sys.platform == "darwin"

# Fuente segun plataforma (solo Windows/tk)
_FONT_UI = "Helvetica Neue" if _IS_MAC else "Segoe UI"

# ---- Overlay IDENTICO al de macOS (mismos colores y geometria que OverlayMac) ----
# Colores tomados literalmente de _PillView.drawRect_ (mas abajo):
BG = "#09090b"           # pill: RGB(0.035, 0.035, 0.043)
RIM = "#1f1f24"          # rim sutil: blanco @ 0.085 sobre el fondo
REC_COLOR = "#fffbf6"    # barras al grabar: blanco calido (1.0, 0.985, 0.965)
TRANS_COLOR = "#ebb30d"  # barras al transcribir: ambar (0.92, 0.70, 0.05)

# Geometria EXACTA del overlay de Mac (ver MAC_W / MAC_H / MAC_BARS ... abajo).
WIDTH = 168             # = MAC_W
HEIGHT = 44             # = MAC_H
TASKBAR_GAP = 14        # = MAC_DOCK_GAP (px sobre la barra de tareas)
BAR_COUNT = 26          # = MAC_BARS
BAR_W = 2.6             # = MAC_BAR_W
BAR_GAP = 2.6           # = MAC_BAR_GAP
BAR_MIN_H = 3.0
RADIUS = 22             # = HEIGHT / 2 (pill completa, como en Mac)


# ===========================================================================
# Windows / fallback: overlay con tkinter
# ===========================================================================
class OverlayTk:
    def __init__(self) -> None:
        import tkinter as tk  # import diferido
        self._tk = tk
        self._amp = 0.0
        self._pulse = 0.0  # fase del pulso al transcribir (= OverlayMac._pulse)
        self._smoothed: deque[float] = deque([0.0] * BAR_COUNT, maxlen=BAR_COUNT)
        self._state = "IDLE"
        self._root = None
        self._canvas = None
        self._ready_evt = threading.Event()

    def start(self) -> None:
        t = threading.Thread(target=self._run, daemon=True)
        t.start()
        self._ready_evt.wait(timeout=5)

    def show_recording(self) -> None:
        self._schedule(lambda: self._set_state("RECORDING"))

    def show_transcribing(self) -> None:
        self._schedule(lambda: self._set_state("TRANSCRIBING"))

    def hide(self) -> None:
        self._schedule(lambda: self._set_state("IDLE"))

    def push_amplitude(self, amp: float) -> None:
        self._amp = max(0.0, min(1.0, amp))

    def _schedule(self, fn) -> None:
        if self._root is None:
            return
        try:
            self._root.after(0, fn)
        except Exception:
            pass

    def _run(self) -> None:
        tk = self._tk
        self._root = tk.Tk()
        self._root.withdraw()
        self._root.overrideredirect(True)
        self._root.attributes("-topmost", True)
        self._root.attributes("-alpha", 0.93)  # = alpha del pill de Mac (0.93)
        TRANSPARENT = "#010203"
        try:
            self._root.attributes("-transparentcolor", TRANSPARENT)
        except tk.TclError:
            TRANSPARENT = BG
        self._root.configure(bg=TRANSPARENT)

        self._canvas = tk.Canvas(
            self._root, width=WIDTH, height=HEIGHT, bg=TRANSPARENT,
            highlightthickness=0, bd=0,
        )
        self._canvas.pack()

        self._position_window()
        self._draw_static()
        self._tick()
        self._ready_evt.set()
        self._root.mainloop()

    def _position_window(self) -> None:
        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        taskbar_h = 80 if _IS_MAC else 48
        x = (sw - WIDTH) // 2
        y = sh - taskbar_h - HEIGHT - TASKBAR_GAP
        self._root.geometry(f"{WIDTH}x{HEIGHT}+{x}+{y}")

    def _draw_static(self) -> None:
        c = self._canvas
        c.delete("all")
        # rim tenue (como el "rim light" del overlay de Mac): pill rim + pill BG 1px adentro.
        self._round_rect(c, 0, 0, WIDTH, HEIGHT, RADIUS, fill=RIM, outline="")
        self._round_rect(c, 1, 1, WIDTH - 1, HEIGHT - 1, RADIUS - 1, fill=BG, outline="")

    def _round_rect(self, canvas, x1, y1, x2, y2, r, **kw) -> None:
        canvas.create_arc(x1, y1, x1 + 2 * r, y1 + 2 * r, start=90, extent=90, style="pieslice", **kw)
        canvas.create_arc(x2 - 2 * r, y1, x2, y1 + 2 * r, start=0, extent=90, style="pieslice", **kw)
        canvas.create_arc(x1, y2 - 2 * r, x1 + 2 * r, y2, start=180, extent=90, style="pieslice", **kw)
        canvas.create_arc(x2 - 2 * r, y2 - 2 * r, x2, y2, start=270, extent=90, style="pieslice", **kw)
        canvas.create_rectangle(x1 + r, y1, x2 - r, y2, **kw)
        canvas.create_rectangle(x1, y1 + r, x2, y2 - r, **kw)

    def _set_state(self, new_state: str) -> None:
        if new_state == self._state:
            return
        self._state = new_state
        if new_state == "IDLE":
            self._root.withdraw()
            self._smoothed = deque([0.0] * BAR_COUNT, maxlen=BAR_COUNT)
            self._pulse = 0.0
        else:
            self._root.deiconify()
            self._root.lift()
            self._root.attributes("-topmost", True)

    def _tick(self) -> None:
        try:
            if self._state != "IDLE":
                self._render_frame()
        except Exception:
            pass
        self._root.after(16, self._tick)  # ~60 fps (= MAC_FPS)

    @staticmethod
    def _lerp_color(c1: str, c2: str, t: float) -> str:
        """Interpola dos colores hex (#rrggbb) segun t en [0,1]."""
        t = max(0.0, min(1.0, t))
        a = (int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16))
        b = (int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16))
        r = tuple(int(a[k] + (b[k] - a[k]) * t) for k in range(3))
        return f"#{r[0]:02x}{r[1]:02x}{r[2]:02x}"

    def _render_frame(self) -> None:
        c = self._canvas
        self._draw_static()

        # --- _advance: identico a OverlayMac._advance ---
        if self._state == "RECORDING":
            lv = self._amp
        else:
            self._pulse += 0.16
            lv = 0.16 + 0.13 * abs(math.sin(self._pulse))
        self._smoothed.append(max(lv, 0.04))

        # --- dibujado: identico a _PillView.drawRect_ ---
        # tkinter no tiene alpha por figura => simulamos el alpha de cada barra
        # mezclando su color contra el fondo del pill (la ventana ya va al 93%).
        transcribing = self._state == "TRANSCRIBING"
        levels = list(self._smoothed)          # historial scrolleando (26 valores)
        n = len(levels)
        if n == 0:
            return
        total = n * BAR_W + (n - 1) * BAR_GAP
        x0 = (WIDTH - total) / 2.0
        cy = HEIGHT / 2.0
        min_h = BAR_MIN_H
        max_h = HEIGHT - 16.0

        for i, lv in enumerate(levels):
            v = max(0.0, min(1.0, lv))
            bh = min_h + v * (max_h - min_h)
            x = x0 + i * (BAR_W + BAR_GAP) + BAR_W / 2.0
            if transcribing:
                color = self._lerp_color(BG, TRANS_COLOR, 0.95)
            else:
                a = 0.42 + 0.55 * v
                color = self._lerp_color(BG, REC_COLOR, a)
            # Linea vertical con puntas redondeadas (= barra de radio MAC_BAR_W/2).
            c.create_line(x, cy - bh / 2, x, cy + bh / 2,
                          fill=color, width=BAR_W, capstyle="round")


# ===========================================================================
# macOS: overlay NATIVO con NSPanel (pyobjc) — pill compacta + onda al centro
# ===========================================================================
# Geometria de la pill (estilo indicador de dictado de macOS / Wispr Flow)
MAC_W = 168
MAC_H = 44
MAC_DOCK_GAP = 14         # px sobre el dock
MAC_BARS = 26             # cantidad de barras de la onda
MAC_BAR_W = 2.6
MAC_BAR_GAP = 2.6
MAC_FPS = 60


def _build_overlay_mac():
    """Construye la clase OverlayMac sobre pyobjc. Devuelve None si no hay Cocoa."""
    try:
        from AppKit import (
            NSPanel, NSView, NSColor, NSBezierPath, NSApplication, NSScreen,
            NSTimer, NSBackingStoreBuffered,
        )
        from Foundation import NSMakeRect, NSRunLoop
        import objc
    except Exception:
        return None

    # Constantes (con fallback a literales si el nombre no esta expuesto)
    def _const(mod_get, default):
        try:
            return mod_get()
        except Exception:
            return default
    import AppKit as _AK
    BORDERLESS = getattr(_AK, "NSWindowStyleMaskBorderless", 0)
    NONACTIVATING = getattr(_AK, "NSWindowStyleMaskNonactivatingPanel", 1 << 7)
    STATUS_LEVEL = getattr(_AK, "NSStatusWindowLevel", 25)
    POLICY_ACCESSORY = getattr(_AK, "NSApplicationActivationPolicyAccessory", 1)
    CB_ALL_SPACES = getattr(_AK, "NSWindowCollectionBehaviorCanJoinAllSpaces", 1 << 0)
    CB_STATIONARY = getattr(_AK, "NSWindowCollectionBehaviorStationary", 1 << 4)
    CB_FS_AUX = getattr(_AK, "NSWindowCollectionBehaviorFullScreenAuxiliary", 1 << 8)
    RUNLOOP_COMMON = getattr(_AK, "NSRunLoopCommonModes", "kCFRunLoopCommonModes")

    class _PillView(NSView):
        def drawRect_(self, rect):
            ov = getattr(self, "overlay", None)
            if ov is None:
                return
            b = self.bounds()
            w = b.size.width
            h = b.size.height
            r = h / 2.0
            # --- fondo: pill oscura translucida ---
            path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(b, r, r)
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.035, 0.035, 0.043, 0.93).set()
            path.fill()
            # rim sutil (rim light)
            inset = NSMakeRect(0.6, 0.6, w - 1.2, h - 1.2)
            rim = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(inset, r, r)
            rim.setLineWidth_(1.0)
            NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.085).set()
            rim.stroke()
            # --- barras de la onda (centradas, simetricas) ---
            levels = ov._levels()
            n = len(levels)
            if n == 0:
                return
            total = n * MAC_BAR_W + (n - 1) * MAC_BAR_GAP
            x0 = (w - total) / 2.0
            cy = h / 2.0
            min_h = 3.0
            max_h = h - 16.0
            transcribing = (ov._state == "TRANSCRIBING")
            for i, lv in enumerate(levels):
                bh = min_h + max(0.0, min(1.0, lv)) * (max_h - min_h)
                x = x0 + i * (MAC_BAR_W + MAC_BAR_GAP)
                y = cy - bh / 2.0
                br = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                    NSMakeRect(x, y, MAC_BAR_W, bh), MAC_BAR_W / 2.0, MAC_BAR_W / 2.0)
                if transcribing:
                    NSColor.colorWithCalibratedRed_green_blue_alpha_(0.92, 0.70, 0.05, 0.95).set()
                else:
                    a = 0.42 + 0.55 * min(1.0, lv)
                    NSColor.colorWithCalibratedRed_green_blue_alpha_(1.0, 0.985, 0.965, a).set()
                br.fill()

        def tick_(self, timer):
            ov = getattr(self, "overlay", None)
            if ov is None:
                return
            win = self.window()
            if win is None:
                return
            if ov._want_visible and not ov._is_shown:
                ov._reposition(win)
                win.orderFrontRegardless()
                ov._is_shown = True
            elif (not ov._want_visible) and ov._is_shown:
                win.orderOut_(None)
                ov._is_shown = False
                ov._reset_bars()
                return
            if not ov._is_shown:
                return
            ov._advance()
            self.setNeedsDisplay_(True)

        # No robar foco / no recibir clicks
        def acceptsFirstResponder(self):
            return False

    class OverlayMac:
        def __init__(self) -> None:
            self._amp = 0.0
            self._state = "IDLE"
            self._want_visible = False
            self._is_shown = False
            self._pulse = 0.0
            self._smoothed: deque[float] = deque([0.0] * MAC_BARS, maxlen=MAC_BARS)
            self._panel = None
            self._view = None

        # ---- API publica (la llama el daemon desde otros threads) ----
        def start(self) -> None:
            # En Mac el daemon llama _run() en el hilo principal; start() no se usa.
            pass

        def show_recording(self) -> None:
            self._state = "RECORDING"
            self._want_visible = True

        def show_transcribing(self) -> None:
            self._state = "TRANSCRIBING"
            self._want_visible = True

        def hide(self) -> None:
            self._want_visible = False
            self._state = "IDLE"

        def push_amplitude(self, amp: float) -> None:
            self._amp = max(0.0, min(1.0, amp))

        # ---- helpers (corren en el hilo principal via timer) ----
        def _levels(self):
            return list(self._smoothed)

        def _reset_bars(self):
            self._smoothed = deque([0.0] * MAC_BARS, maxlen=MAC_BARS)
            self._pulse = 0.0

        def _advance(self):
            if self._state == "RECORDING":
                lv = self._amp
            else:
                self._pulse += 0.16
                lv = 0.16 + 0.13 * abs(math.sin(self._pulse))
            self._smoothed.append(max(lv, 0.04))

        def _reposition(self, win):
            try:
                vf = NSScreen.mainScreen().visibleFrame()
                x = vf.origin.x + (vf.size.width - MAC_W) / 2.0
                y = vf.origin.y + MAC_DOCK_GAP
                win.setFrameOrigin_((x, y))
            except Exception:
                pass

        # ---- run loop (hilo principal) ----
        def _run(self) -> None:
            app = NSApplication.sharedApplication()
            try:
                app.setActivationPolicy_(POLICY_ACCESSORY)  # sin icono en Dock, no roba foco
            except Exception:
                pass

            style = BORDERLESS | NONACTIVATING
            panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
                NSMakeRect(0, 0, MAC_W, MAC_H), style, NSBackingStoreBuffered, False)
            panel.setOpaque_(False)
            panel.setBackgroundColor_(NSColor.clearColor())
            panel.setLevel_(STATUS_LEVEL)
            panel.setHasShadow_(True)
            panel.setIgnoresMouseEvents_(True)
            panel.setHidesOnDeactivate_(False)
            try:
                panel.setFloatingPanel_(True)
                panel.setBecomesKeyOnlyIfNeeded_(True)
                panel.setCollectionBehavior_(CB_ALL_SPACES | CB_STATIONARY | CB_FS_AUX)
            except Exception:
                pass

            view = _PillView.alloc().initWithFrame_(NSMakeRect(0, 0, MAC_W, MAC_H))
            view.overlay = self
            panel.setContentView_(view)
            self._panel = panel
            self._view = view
            self._reposition(panel)

            # Timer de animacion (~60fps) en el run loop principal, incluso durante tracking
            timer = NSTimer.timerWithTimeInterval_target_selector_userInfo_repeats_(
                1.0 / MAC_FPS, view, "tick:", None, True)
            NSRunLoop.currentRunLoop().addTimer_forMode_(timer, RUNLOOP_COMMON)

            app.run()

    return OverlayMac


# ===========================================================================
# Seleccion de implementacion
# ===========================================================================
Overlay = OverlayTk
if _IS_MAC:
    _OverlayMac = _build_overlay_mac()
    if _OverlayMac is not None:
        Overlay = _OverlayMac


# ---------------------------------------------------------------------------
# Quick test cuando se corre directo
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    ov = Overlay()
    if _IS_MAC:
        # Simular actividad desde un thread mientras el overlay corre en main
        def _sim():
            time.sleep(1.0)
            print("RECORDING 5s")
            ov.show_recording()
            t0 = time.time()
            while time.time() - t0 < 5:
                ov.push_amplitude(0.35 + 0.55 * abs(math.sin((time.time() - t0) * 6)))
                time.sleep(0.02)
            print("TRANSCRIBING 3s")
            ov.show_transcribing()
            time.sleep(3)
            print("HIDE")
            ov.hide()
        threading.Thread(target=_sim, daemon=True).start()
        ov._run()
    else:
        ov.start()
        time.sleep(1)
        ov.show_recording()
        t0 = time.time()
        while time.time() - t0 < 5:
            ov.push_amplitude(0.3 + 0.5 * abs(math.sin((time.time() - t0) * 6)))
            time.sleep(0.03)
        ov.show_transcribing()
        time.sleep(3)
        ov.hide()
        time.sleep(1)
        print("OK")
