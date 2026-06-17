# ponytail: set DPI awareness BEFORE any other import touches the DPI context.
# If this is skipped, ClientToScreen returns logical pixels but ImageGrab reads physical → coord drift.
import ctypes
_dpi_set = False
for fn, arg in [
    (lambda: ctypes.windll.user32.SetProcessDpiAwarenessContext(-4), None),  # PER_MONITOR_AWARE_V2
    (lambda: ctypes.windll.shcore.SetProcessDpiAwareness(2), None),          # per-monitor
    (lambda: ctypes.windll.user32.SetProcessDPIAware(), None),               # system aware
]:
    try:
        if fn():
            _dpi_set = True
            break
    except Exception:
        continue
print(f"DPI awareness set: {_dpi_set}")

import tkinter as tk
import threading
import keyboard as key
import json
import os
from time import sleep, time
from threading import Event

import win32gui
from utils import HWND, grab_window
from autofisher import Autofisher

CALIB_FILE = "calib.json"


CFG_ITEMS = [
    # (cfg_key,        label,            kind,    save_name)
    ('bait_pos',       'Bait button',    'pos',   None),
    ('water_pos',      'Water button',   'pos',   None),
    ('deto_pos',       'Deto button',    'pos',   None),
    ('first_fish_pos', 'First fish',     'pos',   None),
    ('recycle_pos',    'Recycle button', 'pos',   None),
    ('water_img',      'Water region',   'region','water'),
    ('splash_img',     'Splash region',  'region','splash'),
    ('emptier_img',    'Inv. emptier',   'region','emptier'),
    ('empty_fish_img', 'Empty fish',     'region','empty_fish'),
    ('number_bbox',    'Recycle number', 'region', None),
]


class AutoFishGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("AutoFish")
        self.root.geometry("520x900")
        self.root.configure(bg='#0d1117')
        self.root.resizable(True, True)
        self.root.minsize(480, 700)

        self.cfg = {k: None for k, *_ in CFG_ITEMS}
        self.capturing = False
        self.running = False
        self.pause = False
        self.setup_done = False
        self.stop_event = Event()
        self.start_time = None

        self._build_ui()
        self._load_calibration()

    # ---------------------------------------------------------------- UI ----

    def _build_ui(self):
        tk.Label(self.root, text="AutoFish", font=('Segoe UI', 18, 'bold'),
                 bg='#0d1117', fg='#58a6ff').pack(pady=(10, 2))
        tk.Label(self.root, text="Growtopia fishing assistant",
                 font=('Segoe UI', 9), bg='#0d1117', fg='#8b949e').pack()

        # Status + instruction
        si = tk.Frame(self.root, bg='#161b22')
        si.pack(fill='x', padx=20, pady=(8, 4))
        tk.Label(si, text="STATUS", font=('Segoe UI', 7, 'bold'),
                 bg='#161b22', fg='#8b949e').pack(anchor='w', padx=10, pady=(6, 0))
        self.status_label = tk.Label(si, text="Idle — configure positions below",
                                     font=('Segoe UI', 10), bg='#161b22', fg='#3fb950')
        self.status_label.pack(anchor='w', padx=10)
        tk.Label(si, text="INSTRUCTION", font=('Segoe UI', 7, 'bold'),
                 bg='#161b22', fg='#8b949e').pack(anchor='w', padx=10, pady=(4, 0))
        self.instr_label = tk.Label(si, text="Click Set on any row, or Setup All.",
                                    font=('Segoe UI', 9), bg='#161b22', fg='#e6edf3',
                                    wraplength=380, justify='left')
        self.instr_label.pack(anchor='w', padx=10, pady=(2, 6))

        # Config card
        cfg_card = tk.Frame(self.root, bg='#161b22')
        cfg_card.pack(fill='x', padx=20, pady=4)

        header = tk.Frame(cfg_card, bg='#161b22')
        header.pack(fill='x', padx=10, pady=(6, 4))
        tk.Label(header, text="CONFIGURATION", font=('Segoe UI', 7, 'bold'),
                 bg='#161b22', fg='#8b949e').pack(side='left')
        self.setup_all_btn = tk.Button(header, text="Setup All",
                                       command=self.start_setup_all,
                                       bg='#1f6feb', fg='white',
                                       font=('Segoe UI', 8, 'bold'),
                                       relief='flat', cursor='hand2', bd=0,
                                       padx=8, pady=2)
        self.setup_all_btn.pack(side='right')

        tk.Frame(cfg_card, bg='#30363d', height=1).pack(fill='x', padx=10)

        self.cfg_val_vars = {}
        self.cfg_val_lbls = {}
        self.cfg_set_btns = {}

        for k, label, kind, _ in CFG_ITEMS:
            row = tk.Frame(cfg_card, bg='#161b22')
            row.pack(fill='x', padx=10, pady=2)
            tk.Label(row, text=label, font=('Segoe UI', 9),
                     bg='#161b22', fg='#8b949e', width=14, anchor='w').pack(side='left')
            var = tk.StringVar(value="Not set")
            self.cfg_val_vars[k] = var
            lbl = tk.Label(row, textvariable=var, font=('Consolas', 8),
                           bg='#161b22', fg='#484f58', anchor='w')
            lbl.pack(side='left', expand=True, fill='x')
            self.cfg_val_lbls[k] = lbl
            btn = tk.Button(row, text="Set",
                            command=lambda kk=k, t=kind: self._capture_item(kk, t),
                            bg='#21262d', fg='#58a6ff',
                            font=('Segoe UI', 8, 'bold'),
                            relief='flat', cursor='hand2', bd=0, padx=8, pady=2)
            self.cfg_set_btns[k] = btn
            btn.pack(side='right')

        tk.Frame(cfg_card, bg='#161b22', height=6).pack()

        # Stats
        st_card = tk.Frame(self.root, bg='#161b22')
        st_card.pack(fill='x', padx=20, pady=4)
        tk.Label(st_card, text="STATS", font=('Segoe UI', 7, 'bold'),
                 bg='#161b22', fg='#8b949e').pack(anchor='w', padx=10, pady=(6, 0))
        g = tk.Frame(st_card, bg='#161b22')
        g.pack(fill='x', padx=10, pady=(2, 6))
        self.fish_var = tk.StringVar(value="Fish: 0")
        self.time_var = tk.StringVar(value="Time: 00:00:00")
        for i, v in enumerate([self.fish_var, self.time_var]):
            tk.Label(g, textvariable=v, font=('Segoe UI', 10),
                     bg='#161b22', fg='#e6edf3').grid(row=0, column=i,
                                                      sticky='w', padx=(0, 24), pady=1)

        # Buttons
        btn_row = tk.Frame(self.root, bg='#0d1117')
        btn_row.pack(pady=10)
        self.start_btn = self._btn(btn_row, "Start", '#238636', self.start_fishing, 'disabled')
        self.start_btn.pack(side='left', padx=4)
        self.pause_btn = self._btn(btn_row, "Pause", '#9e6a03', self.toggle_pause, 'disabled')
        self.pause_btn.pack(side='left', padx=4)
        self.stop_btn  = self._btn(btn_row, "Stop",  '#b62324', self.stop_fishing, 'disabled')
        self.stop_btn.pack(side='left', padx=4)

        # Log
        log_card = tk.Frame(self.root, bg='#161b22')
        log_card.pack(fill='both', expand=True, padx=20, pady=(0, 4))
        tk.Label(log_card, text="LOG", font=('Segoe UI', 7, 'bold'),
                 bg='#161b22', fg='#8b949e').pack(anchor='w', padx=10, pady=(8, 0))
        log_wrap = tk.Frame(log_card, bg='#0d1117')
        log_wrap.pack(fill='both', expand=True, padx=10, pady=(2, 8))
        self.log_box = tk.Text(log_wrap, height=12, bg='#0d1117', fg='#58a6ff',
                               font=('Consolas', 9), relief='flat', state='disabled',
                               wrap='word')
        scrollbar = tk.Scrollbar(log_wrap, command=self.log_box.yview,
                                 bg='#0d1117', troughcolor='#161b22', bd=0)
        self.log_box.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side='right', fill='y')
        self.log_box.pack(side='left', fill='both', expand=True)

        tk.Label(self.root, text="Hold CTRL to capture   ESC: stop   P: pause",
                 font=('Segoe UI', 8), bg='#0d1117', fg='#484f58').pack(pady=(0, 8))

    def _btn(self, parent, text, color, cmd, state='normal'):
        return tk.Button(parent, text=text, command=cmd,
                         bg=color, fg='white', font=('Segoe UI', 10, 'bold'),
                         width=7, relief='flat', cursor='hand2',
                         activebackground=color, activeforeground='white',
                         state=state, bd=0, pady=6)

    # -------------------------------------------------------- helpers -----

    def _ui(self, fn, *a, **kw):
        self.root.after(0, lambda: fn(*a, **kw))

    def log(self, msg):
        def _do():
            self.log_box.configure(state='normal')
            self.log_box.insert('end', f"> {msg}\n")
            self.log_box.see('end')
            self.log_box.configure(state='disabled')
        self._ui(_do)

    def set_status(self, text, color='#3fb950'):
        self._ui(self.status_label.configure, text=text, fg=color)

    def set_instr(self, text):
        self._ui(self.instr_label.configure, text=text)

    # ----------------------------------------------------- capture --------

    def wait_for_ctrl(self):
        while key.is_pressed('ctrl'): sleep(0.01)
        sleep(0.05)
        while not key.is_pressed('ctrl'): sleep(0.01)
        screen = win32gui.GetCursorPos()
        client = win32gui.ScreenToClient(HWND, screen)
        wrect = win32gui.GetWindowRect(HWND)
        crect = win32gui.GetClientRect(HWND)
        self.log(f"screen={screen} → client={client}  win={wrect}  client_rect={crect}")
        return client

    def _capture_pos(self, label):
        self.set_instr(f"Move to {label.upper()}, then hold CTRL")
        return self.wait_for_ctrl()

    def _capture_region(self, label, save_name):
        self.set_instr(f"Move to UPPER-LEFT of {label.upper()}, hold CTRL")
        x1, y1 = self.wait_for_ctrl()
        self.set_instr(f"Move to BOTTOM-RIGHT of {label.upper()}, hold CTRL")
        x2, y2 = self.wait_for_ctrl()
        bbox = (x1, y1, x2, y2)
        if save_name:
            grab_window(bbox).save(f"{save_name}.png")
        return bbox

    def _set_capture_ui(self, capturing):
        state = 'disabled' if capturing else 'normal'
        self._ui(self.setup_all_btn.configure, state=state)
        for btn in self.cfg_set_btns.values():
            self._ui(btn.configure, state=state)
        if not capturing:
            self._check_all_set()

    def _capture_item(self, k, kind):
        if self.capturing or self.running: return
        self.capturing = True
        self._set_capture_ui(True)
        threading.Thread(target=self._capture_item_thread,
                         args=(k, kind), daemon=True).start()

    def _capture_item_thread(self, k, kind):
        label, save = next((lbl, s) for kk, lbl, _, s in CFG_ITEMS if kk == k)
        try:
            self._ui(self.cfg_set_btns[k].configure, text='...')
            self._ui(self.cfg_val_vars[k].set, 'Capturing...')
            self.set_status(f"Capturing {label}...", '#d29922')

            if kind == 'pos':
                val = self._capture_pos(label)
                self._ui(self.cfg_val_vars[k].set, f"({val[0]}, {val[1]})")
            else:
                val = self._capture_region(label, save)
                self._ui(self.cfg_val_vars[k].set,
                         f"({val[0]}, {val[1]}) → ({val[2]}, {val[3]})")
            self.cfg[k] = val
            self._ui(self.cfg_val_lbls[k].configure, fg='#3fb950')
            self.log(f"{label}: {val}")
            self._save_calibration()
        except Exception as e:
            self.log(f"Capture error: {e}")
            self._ui(self.cfg_val_vars[k].set, "Error")
            self._ui(self.cfg_val_lbls[k].configure, fg='#f85149')
        finally:
            self._ui(self.cfg_set_btns[k].configure, text='Set')
            self.capturing = False
            self._set_capture_ui(False)

    def start_setup_all(self):
        if self.capturing or self.running: return
        self.capturing = True
        self._set_capture_ui(True)
        threading.Thread(target=self._setup_all_thread, daemon=True).start()

    def _setup_all_thread(self):
        try:
            self.set_status("Setting up...", '#d29922')
            for k, label, kind, save in CFG_ITEMS:
                self._ui(self.cfg_set_btns[k].configure, text='...')
                self._ui(self.cfg_val_vars[k].set, 'Capturing...')
                val = self._capture_pos(label) if kind == 'pos' \
                      else self._capture_region(label, save)
                self.cfg[k] = val
                text = f"({val[0]}, {val[1]})" if kind == 'pos' \
                       else f"({val[0]}, {val[1]}) → ({val[2]}, {val[3]})"
                self._ui(self.cfg_val_vars[k].set, text)
                self._ui(self.cfg_val_lbls[k].configure, fg='#3fb950')
                self._ui(self.cfg_set_btns[k].configure, text='Set')
                self.log(f"{label}: {val}")
            self._save_calibration()
            self.log("Setup complete")
        except Exception as e:
            self.log(f"Setup error: {e}")
            self.set_status("Setup failed", '#f85149')
        finally:
            self.capturing = False
            self._set_capture_ui(False)

    def _check_all_set(self):
        ready = all(v is not None for v in self.cfg.values())
        if ready and not self.setup_done:
            self.setup_done = True
            self.set_status("Ready — press Start", '#3fb950')
            self.set_instr("All set. Press Start.")
        self._ui(self.start_btn.configure,
                 state='normal' if ready else 'disabled')

    # ----------------------------------------------------- persistence ---

    def _save_calibration(self):
        # ponytail: tuples become lists in JSON — coerce back on load
        with open(CALIB_FILE, "w") as f:
            json.dump(self.cfg, f, indent=2)

    def _load_calibration(self):
        if not os.path.exists(CALIB_FILE):
            return
        try:
            data = json.load(open(CALIB_FILE))
        except Exception as e:
            self.log(f"calib load failed: {e}")
            return

        loaded = 0
        for k, label, kind, save in CFG_ITEMS:
            val = data.get(k)
            if val is None:
                continue
            # JSON gives list; convert to tuple to match capture-time shape
            val = tuple(val)
            # region needs the PNG on disk (unless save_name is None, e.g. number_bbox)
            if kind == 'region' and save and not os.path.exists(f"{save}.png"):
                self.log(f"{label}: missing {save}.png — recapture")
                continue
            self.cfg[k] = val
            text = f"({val[0]}, {val[1]})" if kind == 'pos' \
                   else f"({val[0]}, {val[1]}) → ({val[2]}, {val[3]})"
            self.cfg_val_vars[k].set(text)
            self.cfg_val_lbls[k].configure(fg='#3fb950')
            loaded += 1
        if loaded:
            self.log(f"loaded {loaded}/{len(CFG_ITEMS)} from {CALIB_FILE}")
        self._check_all_set()

    # ----------------------------------------------------- fishing -------

    def start_fishing(self):
        if not self.setup_done or self.running: return
        self.running = True
        self.pause = False
        self.stop_event.clear()
        self.start_time = time()
        self._ui(self.start_btn.configure, state='disabled')
        self._ui(self.pause_btn.configure, state='normal')
        self._ui(self.stop_btn.configure,  state='normal')
        self._ui(self.setup_all_btn.configure, state='disabled')
        for b in self.cfg_set_btns.values():
            self._ui(b.configure, state='disabled')
        self.set_status("Running", '#3fb950')
        threading.Thread(target=self._fish_thread, daemon=True).start()
        self._tick_stats()

    def _fish_thread(self):
        try:
            fisher = Autofisher(cfg=self.cfg, stop_event=self.stop_event,
                                on_log=self.log, paused=lambda: self.pause)
            self._fisher = fisher
            fisher.loop()
        except Exception as e:
            self.log(f"Loop error: {e}")
            self.set_status("Error — stopped", '#f85149')
        finally:
            # ponytail: watchdog sets stop_event AND needs_restart — restart only on the latter
            if getattr(getattr(self, '_fisher', None), 'needs_restart', False):
                self.log("auto-restart in 3s")
                sleep(3)
                self.stop_event.clear()
                threading.Thread(target=self._fish_thread, daemon=True).start()
            else:
                self._on_loop_end()

    def _on_loop_end(self):
        self.running = False
        self._ui(self.start_btn.configure, state='normal')
        self._ui(self.pause_btn.configure, state='disabled', text='Pause', bg='#9e6a03')
        self._ui(self.stop_btn.configure,  state='disabled')
        self._ui(self.setup_all_btn.configure, state='normal')
        for b in self.cfg_set_btns.values():
            self._ui(b.configure, state='normal')

    def toggle_pause(self):
        if not self.running: return
        self.pause = not self.pause
        if self.pause:
            self.set_status("Paused", '#d29922')
            self._ui(self.pause_btn.configure, text='Resume', bg='#238636')
        else:
            self.set_status("Running", '#3fb950')
            self._ui(self.pause_btn.configure, text='Pause', bg='#9e6a03')

    def stop_fishing(self):
        if not self.running: return
        self.stop_event.set()
        self.set_status("Stopping...", '#f85149')

    def _tick_stats(self):
        if not self.running: return
        elapsed = int(time() - self.start_time)
        h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
        self.time_var.set(f"Time: {h:02d}:{m:02d}:{s:02d}")
        fish = getattr(getattr(self, '_fisher', None), 'fish', 0)
        self.fish_var.set(f"Fish: {fish}")
        self.root.after(500, self._tick_stats)

    # ------------------------------------------------------ run / quit ---

    def run(self):
        key.add_hotkey('esc', self.stop_fishing)
        key.add_hotkey('p',   self.toggle_pause)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self):
        self.stop_event.set()
        self.root.destroy()


if __name__ == '__main__':
    AutoFishGUI().run()
