import ctypes
for fn in [
    lambda: ctypes.windll.user32.SetProcessDpiAwarenessContext(-4),
    lambda: ctypes.windll.shcore.SetProcessDpiAwareness(2),
    lambda: ctypes.windll.user32.SetProcessDPIAware(),
]:
    try:
        fn(); break
    except Exception:
        continue

import json, os, threading, time, keyboard as key
import win32gui, win32con, webview
from threading import Event
from utils import HWND, grab_window
from autofisher import Autofisher

CALIB_FILE = "calib.json"

CFG_ITEMS = [
    ('bait_pos',       'Bait button',    'pos',    None),
    ('water_pos',      'Water button',   'pos',    None),
    ('deto_pos',       'Deto button',    'pos',    None),
    ('first_fish_pos', 'First fish',     'pos',    None),
    ('recycle_pos',    'Recycle button', 'pos',    None),
    ('uranium_img',    'Uranium region', 'region', 'uranium'),
    ('splash_img',     'Splash region',  'region', 'splash'),
    ('nothing_img',    'Nothing notif',  'region', 'nothing'),
    ('emptier_img',    'Inv. emptier',   'region', 'emptier'),
    ('empty_fish_img', 'Empty fish',     'region', 'empty_fish'),
    ('number_bbox',    'Recycle number', 'region', None),
]


def _fmt(val, kind):
    if kind == 'pos':    return f"({val[0]}, {val[1]})"
    return f"({val[0]}, {val[1]}) → ({val[2]}, {val[3]})"


class Api:
    def __init__(self):
        self.cfg       = {k: None for k, *_ in CFG_ITEMS}
        self.capturing = False
        self.running   = False
        self.pause     = False
        self.stop_event = Event()
        self._fisher   = None
        self._start_time = None
        self._window   = None  # set after webview.create_window

    def _push(self, ev: dict):
        if self._window:
            self._window.evaluate_js(f'window.__push({json.dumps(ev)})')

    def _log(self, msg):
        self._push({'type': 'log', 'msg': msg})

    def _status(self, text, color='#3fb950'):
        self._push({'type': 'status', 'text': text, 'color': color})

    def _instr(self, text):
        self._push({'type': 'instr', 'text': text})

    def _state(self):
        elapsed = ''
        if self._start_time:
            s = int(time.time() - self._start_time)
            elapsed = f"{s//3600:02d}:{(s%3600)//60:02d}:{s%60:02d}"
        self._push({
            'type': 'state',
            'running':   self.running,
            'capturing': self.capturing,
            'paused':    self.pause,
            'fish':      getattr(self._fisher, 'fish', 0),
            'elapsed':   elapsed,
        })

    # --------------------------------------------------------- capture ----

    def _wait_ctrl(self):
        while key.is_pressed('ctrl'): time.sleep(0.01)
        time.sleep(0.05)
        while not key.is_pressed('ctrl'): time.sleep(0.01)
        screen = win32gui.GetCursorPos()
        return win32gui.ScreenToClient(HWND, screen)

    def capture_item(self, k, kind):
        if self.capturing or self.running: return
        self.capturing = True
        self._state()
        threading.Thread(target=self._capture_thread, args=(k, kind), daemon=True).start()

    def _capture_thread(self, k, kind):
        label, _, save = next((lbl, t, s) for kk, lbl, t, s in CFG_ITEMS if kk == k)
        try:
            self._push({'type': 'cfg_update', 'key': k, 'text': 'Capturing...', 'ok': False})
            self._status(f"Capturing {label}...", '#d29922')

            if kind == 'pos':
                self._instr(f"Move to {label.upper()}, then hold CTRL")
                val = self._wait_ctrl()
            else:
                self._instr(f"Move to UPPER-LEFT of {label.upper()}, hold CTRL")
                x1, y1 = self._wait_ctrl()
                self._instr(f"Move to BOTTOM-RIGHT of {label.upper()}, hold CTRL")
                x2, y2 = self._wait_ctrl()
                val = (x1, y1, x2, y2)
                if save:
                    grab_window(val).save(f"{save}.png")

            self.cfg[k] = val
            self._push({'type': 'cfg_update', 'key': k, 'text': _fmt(val, kind), 'ok': True})
            self._log(f"{label}: {val}")
            self._save_calib()
            self._check_ready()
        except Exception as e:
            self._push({'type': 'cfg_update', 'key': k, 'text': 'Error', 'ok': False})
            self._log(f"Capture error: {e}")
        finally:
            self.capturing = False
            self._state()

    def start_setup_all(self):
        if self.capturing or self.running: return
        self.capturing = True
        self._state()
        threading.Thread(target=self._setup_all_thread, daemon=True).start()

    def _setup_all_thread(self):
        try:
            self._status("Setting up...", '#d29922')
            for k, label, kind, save in CFG_ITEMS:
                self._push({'type': 'cfg_update', 'key': k, 'text': 'Capturing...', 'ok': False})
                if kind == 'pos':
                    self._instr(f"Move to {label.upper()}, then hold CTRL")
                    val = self._wait_ctrl()
                else:
                    self._instr(f"Move to UPPER-LEFT of {label.upper()}, hold CTRL")
                    x1, y1 = self._wait_ctrl()
                    self._instr(f"Move to BOTTOM-RIGHT of {label.upper()}, hold CTRL")
                    x2, y2 = self._wait_ctrl()
                    val = (x1, y1, x2, y2)
                    if save:
                        grab_window(val).save(f"{save}.png")
                self.cfg[k] = val
                self._push({'type': 'cfg_update', 'key': k, 'text': _fmt(val, kind), 'ok': True})
                self._log(f"{label}: {val}")
            self._save_calib()
            self._log("Setup complete")
            self._check_ready()
        except Exception as e:
            self._log(f"Setup error: {e}")
            self._status("Setup failed", '#f85149')
        finally:
            self.capturing = False
            self._state()

    # --------------------------------------------------------- fishing ----

    def start_fishing(self):
        if self.running or not all(v is not None for v in self.cfg.values()): return
        self.running = True
        self.pause = False
        self.stop_event.clear()
        self._start_time = time.time()
        self._status("Running")
        self._state()
        threading.Thread(target=self._fish_thread, daemon=True).start()
        threading.Thread(target=self._tick_thread, daemon=True).start()

    def _fish_thread(self):
        try:
            self._fisher = Autofisher(cfg=self.cfg, stop_event=self.stop_event,
                                      on_log=self._log, paused=lambda: self.pause)
            self._fisher.loop()
        except Exception as e:
            self._log(f"Loop error: {e}")
            self._status("Error — stopped", '#f85149')
        finally:
            self.running = False
            self._start_time = None
            self._state()
            self._check_ready()

    def _tick_thread(self):
        while self.running:
            self._state()
            time.sleep(0.5)

    def toggle_pause(self):
        if not self.running: return
        self.pause = not self.pause
        if self.pause:
            self._status("Paused", '#d29922')
        else:
            self._status("Running")
        self._state()

    def stop_fishing(self):
        if not self.running: return
        self.stop_event.set()
        self._status("Stopping...", '#f85149')

    # --------------------------------------------------------- helpers ----

    def _check_ready(self):
        if all(v is not None for v in self.cfg.values()):
            self._status("Ready — press Start")
            self._instr("All set. Press Start.")

    def _save_calib(self):
        with open(CALIB_FILE, 'w') as f:
            json.dump(self.cfg, f, indent=2)

    def load_calibration(self):
        if not os.path.exists(CALIB_FILE): return
        try:
            data = json.load(open(CALIB_FILE))
        except Exception as e:
            self._log(f"calib load failed: {e}"); return
        loaded = 0
        for k, label, kind, save in CFG_ITEMS:
            val = data.get(k)
            if val is None: continue
            val = tuple(val)
            if kind == 'region' and save and not os.path.exists(f"{save}.png"):
                self._log(f"{label}: missing {save}.png — recapture"); continue
            self.cfg[k] = val
            self._push({'type': 'cfg_update', 'key': k, 'text': _fmt(val, kind), 'ok': True})
            loaded += 1
        if loaded:
            self._log(f"loaded {loaded}/{len(CFG_ITEMS)} from {CALIB_FILE}")
        self._check_ready()


if __name__ == '__main__':
    import sys as _sys
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('Growfisher.App')
    api = Api()
    if getattr(_sys, 'frozen', False):
        _base = _sys._MEIPASS
        _url  = os.path.join(_base, 'ui', 'dist', 'index.html')
    else:
        _url = 'http://localhost:5173/'
    window = webview.create_window(
        'Growfisher', _url,
        js_api=api, width=560, height=900, resizable=False
    )
    api._window = window

    def on_start(w):
        api.load_calibration()
        hwnd = win32gui.FindWindow(None, 'Growfisher')
        ico_small = win32gui.LoadImage(0, 'ui/public/icon.ico', win32con.IMAGE_ICON, 16, 16, win32con.LR_LOADFROMFILE)
        ico_big   = win32gui.LoadImage(0, 'ui/public/icon.ico', win32con.IMAGE_ICON, 32, 32, win32con.LR_LOADFROMFILE)
        win32gui.SendMessage(hwnd, win32con.WM_SETICON, win32con.ICON_SMALL, ico_small)
        win32gui.SendMessage(hwnd, win32con.WM_SETICON, win32con.ICON_BIG, ico_big)
        dark = ctypes.c_int(0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(dark), ctypes.sizeof(dark))

    webview.start(on_start, window)
