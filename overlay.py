# Display-only detection overlay: a click-through window kept just above Growtopia that draws
# YOLO boxes. Nothing here feeds the bot — fishing still runs purely on the picked regions.
# WGC captures only the Growtopia window, so the overlay never shows up in what the bot sees.
import ctypes, ctypes.wintypes, threading, time
from pathlib import Path

import numpy as np
import win32con, win32gui

import utils

MODEL = Path(__file__).resolve().parent / "runs/detect/runs/detect/growfisher-2/weights/best.pt"
IMGSZ, CONF = 1280, 0.25
FPS = 10           # inference rate; kept low so the fishing loop keeps its CPU
STALE = 1.0        # hide boxes older than this (s), e.g. if inference stalls
KEY = "#010203"    # colour Windows makes fully transparent
COLORS = {"splash": "#38bdf8", "bubble_caught": "#3fb950", "bubble_maxed": "#d29922",
          "bubble_nothing": "#f85149", "bubble_emptier": "#a371f7"}


def visible_rect(hwnd):
    # Real on-screen bounds in physical px. GetWindowRect lies for DPI-unaware Growtopia on a
    # scaled monitor (gives 96-DPI virtualized coords + invisible borders); this one doesn't,
    # and it matches the WGC frame 1:1 (measured: both 2002x1165 at 125% scaling).
    r = ctypes.wintypes.RECT()
    ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(r), ctypes.sizeof(r))  # DWMWA_EXTENDED_FRAME_BOUNDS
    return r.left, r.top, r.right, r.bottom


class Overlay:
    def __init__(self, on_log=print, model_path=MODEL):
        self.log, self.model_path = on_log, Path(model_path)
        self._stop = threading.Event()
        self._threads = []
        self._dets = None  # (time, (frame_h, frame_w), [(label, conf, (x1, y1, x2, y2)), ...])

    @property
    def running(self):
        return any(t.is_alive() for t in self._threads)

    def start(self):
        """-> True if the overlay is (now) running."""
        if self.running: return True
        if not self.model_path.exists():
            self.log(f"overlay: model not found: {self.model_path}"); return False
        self._stop.clear()
        self._dets = None
        self._threads = [threading.Thread(target=f, daemon=True) for f in (self._infer, self._ui)]
        for t in self._threads: t.start()
        return True

    def stop(self):
        self._stop.set()

    def _infer(self):
        try:
            import torch
            from ultralytics import YOLO  # lazy: only needed when the overlay is on
            model = YOLO(str(self.model_path))
            device = 0 if torch.cuda.is_available() else "cpu"
        except Exception as e:
            self.log(f"overlay: can't load model ({e})"); self._stop.set(); return
        self.log(f"overlay: {self.model_path.parent.parent.name} on {'GPU' if device == 0 else 'CPU'}")
        last = None
        while not self._stop.is_set():
            t0 = time.time()
            f = utils.latest_frame()
            if f is not None and f is not last:  # same object = no new frame, skip
                try:
                    r = model.predict(np.ascontiguousarray(f[..., :3]), imgsz=IMGSZ, conf=CONF,
                                      device=device, verbose=False)[0]
                    self._dets = (time.time(), f.shape[:2],
                                  [(r.names[int(c)], s, b) for b, s, c in
                                   zip(r.boxes.xyxy.tolist(), r.boxes.conf.tolist(), r.boxes.cls.tolist())])
                except Exception as e:
                    self.log(f"overlay: inference error ({e})"); self._stop.set(); return
                last = f
            self._stop.wait(max(0.0, 1 / FPS - (time.time() - t0)))

    def _ui(self):
        import tkinter as tk
        # Per-monitor DPI-aware for THIS thread only, so the overlay window uses real screen
        # pixels like visible_rect(). Must be a pointer-sized arg: a plain -4 is passed as a
        # 32-bit int and silently fails (the bot's own process-wide call does exactly that and
        # stays DPI-unaware, which its click/region calibration relies on — leave that alone).
        ctypes.windll.user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
        root = tk.Tk()  # own Tk in its own thread; pywebview owns the main thread
        root.overrideredirect(True)
        root.attributes("-transparentcolor", KEY)
        canvas = tk.Canvas(root, bg=KEY, highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        root.update_idletasks()
        me = self._hwnd = int(root.wm_frame(), 16)
        ex = win32gui.GetWindowLong(me, win32con.GWL_EXSTYLE)
        win32gui.SetWindowLong(me, win32con.GWL_EXSTYLE, ex | win32con.WS_EX_LAYERED |
                               win32con.WS_EX_TRANSPARENT | win32con.WS_EX_TOOLWINDOW |
                               win32con.WS_EX_NOACTIVATE)  # click-through, no taskbar entry
        state = {"geo": None, "shown": True}

        def tick():
            if self._stop.is_set():
                root.destroy(); return
            game = utils.HWND
            if not win32gui.IsWindow(game) or win32gui.IsIconic(game):
                if state["shown"]: root.withdraw(); state["shown"] = False
                root.after(200, safe_tick); return
            if not state["shown"]: root.deiconify(); state["shown"] = True
            l, t, r, b = visible_rect(game)
            # sit directly above Growtopia in z-order (not topmost), so other apps still cover it.
            # Placed via SetWindowPos, not root.geometry(): Tk left the window at (0,0).
            above = win32gui.GetWindow(game, win32con.GW_HWNDPREV)
            flags = win32con.SWP_NOACTIVATE
            if above == me:
                flags |= win32con.SWP_NOZORDER
                if state["geo"] == (l, t, r, b):
                    flags |= win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
            if flags != win32con.SWP_NOACTIVATE | win32con.SWP_NOZORDER | win32con.SWP_NOMOVE | win32con.SWP_NOSIZE:
                win32gui.SetWindowPos(me, above or win32con.HWND_TOP, l, t, r - l, b - t, flags)
                state["geo"] = (l, t, r, b)
            canvas.delete("all")
            d = self._dets
            if d and time.time() - d[0] < STALE:
                (fh, fw), dets = d[1], d[2]
                sx, sy = (r - l) / fw, (b - t) / fh  # frame px -> screen px (1.0 when they match)
                for label, conf, (x1, y1, x2, y2) in dets:
                    col = COLORS.get(label, "#ffffff")
                    x1, y1, x2, y2 = x1 * sx, y1 * sy, x2 * sx, y2 * sy
                    canvas.create_rectangle(x1, y1, x2, y2, outline=col, width=2)
                    txt = canvas.create_text(x1 + 3, y1 - 2, anchor="sw", fill="#0d1117",
                                             text=f"{label} {conf:.2f}", font=("Segoe UI", 9, "bold"))
                    bx = canvas.bbox(txt)
                    canvas.tag_lower(canvas.create_rectangle(bx[0] - 3, bx[1], bx[2] + 3, bx[3],
                                                             fill=col, outline=col), txt)
            root.after(33, safe_tick)

        def safe_tick():  # Tk swallows callback errors; surface them and shut down instead
            try:
                tick()
            except Exception as e:
                self.log(f"overlay: window error ({e})"); self._stop.set(); root.destroy()

        root.after(0, safe_tick)
        try:
            root.mainloop()
        except Exception as e:
            self.log(f"overlay: window error ({e})")
        finally:
            self._stop.set()
            # Tk must be freed on the thread that made it, else "Tcl_AsyncDelete: wrong thread"
            # crashes the process. The tick closures form a cycle with root -> break it here.
            root = canvas = None
            import gc; gc.collect()
