import tkinter as tk
import threading
from time import sleep, time
import pyautogui as py
import keyboard as key
import mouse
import win32api as wapi
import win32con as wcon

class MacroRecorder:
    def __init__(self):
        self.steps = []        # list of (x, y, delay_before_click)
        self.is_recording = False
        self._last_time = None

    def start(self):
        self.steps = []
        self.is_recording = True
        self._last_time = time()
        mouse.hook(self._on_event)

    def _on_event(self, event):
        if not self.is_recording:
            return
        if isinstance(event, mouse.ButtonEvent) \
                and event.event_type == mouse.DOWN \
                and event.button == mouse.LEFT:
            now = time()
            x, y = wapi.GetCursorPos()
            self.steps.append((x, y, now - self._last_time))
            self._last_time = now

    def stop(self):
        self.is_recording = False
        sleep(0.05)
        mouse.unhook_all()

    def play(self, click_fn):
        for x, y, delay in self.steps:
            sleep(delay)
            click_fn(x, y)

    def clear(self):
        self.steps = []
        self.is_recording = False

    @property
    def count(self):
        return len(self.steps)

    def has_macro(self):
        return len(self.steps) > 0


CFG_ITEMS = [
    ('w',     'Water button',  'pos'),
    ('b',     'Bait button',   'pos'),
    ('d',     'Drill button',  'pos'),
    ('chest', 'Chest region',  'region'),
    ('ice',   'Ice region',    'region'),
    ('water', 'Water state',   'region'),
]


class AutoFishGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("AutoFish")
        self.root.geometry("440x840")
        self.root.configure(bg='#0d1117')
        self.root.resizable(False, False)

        self.detect = False
        self.pause = False
        self.setup_done = False
        self.capturing = False

        self.pos = {k: None for k, *_ in CFG_ITEMS}
        self.ss  = {k: None for k, _, kind in CFG_ITEMS if kind == 'region'}
        self.macro = MacroRecorder()

        self._build_ui()

    # ------------------------------------------------------------------ UI --

    def _build_ui(self):
        tk.Label(self.root, text="AutoFish", font=('Segoe UI', 18, 'bold'),
                 bg='#0d1117', fg='#58a6ff').pack(pady=(10, 2))
        tk.Label(self.root, text="Automated fishing assistant",
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
        self.instr_label = tk.Label(si, text="Click Set next to any item, or Setup All to configure everything.",
                                    font=('Segoe UI', 9), bg='#161b22', fg='#e6edf3',
                                    wraplength=380, justify='left')
        self.instr_label.pack(anchor='w', padx=10, pady=(2, 6))

        # Configuration card
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
        self.cfg_set_btns = {}

        for key_id, label, kind in CFG_ITEMS:
            row = tk.Frame(cfg_card, bg='#161b22')
            row.pack(fill='x', padx=10, pady=2)

            tk.Label(row, text=label, font=('Segoe UI', 9),
                     bg='#161b22', fg='#8b949e', width=14, anchor='w').pack(side='left')

            var = tk.StringVar(value="Not set")
            self.cfg_val_vars[key_id] = var
            tk.Label(row, textvariable=var, font=('Consolas', 8),
                     bg='#161b22', fg='#484f58', anchor='w').pack(side='left', expand=True, fill='x')

            btn = tk.Button(row, text="Set",
                            command=lambda k=key_id, t=kind: self._capture_item(k, t),
                            bg='#21262d', fg='#58a6ff',
                            font=('Segoe UI', 8, 'bold'),
                            relief='flat', cursor='hand2', bd=0,
                            padx=8, pady=2)
            self.cfg_set_btns[key_id] = btn
            btn.pack(side='right')

        tk.Frame(cfg_card, bg='#161b22', height=6).pack()

        # Macro card
        mac_card = tk.Frame(self.root, bg='#161b22')
        mac_card.pack(fill='x', padx=20, pady=4)

        mac_header = tk.Frame(mac_card, bg='#161b22')
        mac_header.pack(fill='x', padx=10, pady=(6, 4))
        tk.Label(mac_header, text="MACRO", font=('Segoe UI', 7, 'bold'),
                 bg='#161b22', fg='#8b949e').pack(side='left')

        mac_btn_frame = tk.Frame(mac_header, bg='#161b22')
        mac_btn_frame.pack(side='right')
        self.record_btn = tk.Button(mac_btn_frame, text="Record",
                                    command=self._toggle_recording,
                                    bg='#21262d', fg='#f85149',
                                    font=('Segoe UI', 8, 'bold'),
                                    relief='flat', cursor='hand2', bd=0, padx=8, pady=2)
        self.record_btn.pack(side='left', padx=(0, 4))
        self.clear_macro_btn = tk.Button(mac_btn_frame, text="Clear",
                                         command=self._clear_macro,
                                         bg='#21262d', fg='#8b949e',
                                         font=('Segoe UI', 8, 'bold'),
                                         relief='flat', cursor='hand2', bd=0, padx=8, pady=2)
        self.clear_macro_btn.pack(side='left')

        tk.Frame(mac_card, bg='#30363d', height=1).pack(fill='x', padx=10)

        mac_info = tk.Frame(mac_card, bg='#161b22')
        mac_info.pack(fill='x', padx=10, pady=(4, 6))
        self.macro_status_var = tk.StringVar(value="Not recorded")
        tk.Label(mac_info, textvariable=self.macro_status_var,
                 font=('Segoe UI', 9), bg='#161b22', fg='#8b949e').pack(side='left')
        tk.Label(mac_info, text="fish", font=('Segoe UI', 9),
                 bg='#161b22', fg='#8b949e').pack(side='right')
        self.trigger_var = tk.StringVar(value="18")
        tk.Entry(mac_info, textvariable=self.trigger_var, width=4,
                 bg='#21262d', fg='#e6edf3', font=('Segoe UI', 9),
                 relief='flat', insertbackground='white').pack(side='right', padx=2)
        tk.Label(mac_info, text="Trigger every", font=('Segoe UI', 9),
                 bg='#161b22', fg='#8b949e').pack(side='right', padx=(0, 4))

        # Stats
        st_card = tk.Frame(self.root, bg='#161b22')
        st_card.pack(fill='x', padx=20, pady=4)
        tk.Label(st_card, text="STATS", font=('Segoe UI', 7, 'bold'),
                 bg='#161b22', fg='#8b949e').pack(anchor='w', padx=10, pady=(6, 0))

        g = tk.Frame(st_card, bg='#161b22')
        g.pack(fill='x', padx=10, pady=(2, 6))
        self.fish_var = tk.StringVar(value="Fish Found: 0")
        self.ice_var  = tk.StringVar(value="Ice Reformed: 0")
        self.time_var = tk.StringVar(value="Time: 00:00:00")
        for i, v in enumerate([self.fish_var, self.ice_var, self.time_var]):
            tk.Label(g, textvariable=v, font=('Segoe UI', 10),
                     bg='#161b22', fg='#e6edf3').grid(row=i // 2, column=i % 2,
                                                       sticky='w', padx=(0, 24), pady=1)

        # Action buttons
        btn_row = tk.Frame(self.root, bg='#0d1117')
        btn_row.pack(pady=10)
        self.start_btn = self._btn(btn_row, "Start",  '#238636', self.start_fishing, state='disabled')
        self.start_btn.pack(side='left', padx=4)
        self.pause_btn = self._btn(btn_row, "Pause",  '#9e6a03', self.toggle_pause,  state='disabled')
        self.pause_btn.pack(side='left', padx=4)
        self.stop_btn  = self._btn(btn_row, "Stop",   '#b62324', self.stop_fishing,  state='disabled')
        self.stop_btn.pack(side='left', padx=4)

        # Log
        log_card = tk.Frame(self.root, bg='#161b22')
        log_card.pack(fill='both', expand=True, padx=20, pady=(0, 4))
        tk.Label(log_card, text="LOG", font=('Segoe UI', 7, 'bold'),
                 bg='#161b22', fg='#8b949e').pack(anchor='w', padx=10, pady=(8, 0))
        self.log_box = tk.Text(log_card, height=6, bg='#0d1117', fg='#58a6ff',
                               font=('Consolas', 9), relief='flat', state='disabled')
        self.log_box.pack(fill='both', expand=True, padx=10, pady=(2, 8))

        tk.Label(self.root, text="ESC: stop   P: pause/resume",
                 font=('Segoe UI', 8), bg='#0d1117', fg='#484f58').pack(pady=(0, 8))

    def _btn(self, parent, text, color, cmd, state='normal'):
        return tk.Button(parent, text=text, command=cmd,
                         bg=color, fg='white', font=('Segoe UI', 10, 'bold'),
                         width=7, relief='flat', cursor='hand2',
                         activebackground=color, activeforeground='white',
                         state=state, bd=0, pady=6)

    # -------------------------------------------------------- thread helpers --

    def _ui(self, fn, *args, **kwargs):
        self.root.after(0, lambda: fn(*args, **kwargs))

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

    def _set_cfg_val(self, key_id, text, color='#3fb950'):
        self._ui(self.cfg_val_vars[key_id].set, text)
        self._ui(self.cfg_set_btns[key_id].master.children['!label2'].configure, fg=color)

    # -------------------------------------------------------- Ctrl capture --

    def wait_for_ctrl(self):
        while key.is_pressed('ctrl'):
            sleep(0.01)
        sleep(0.05)
        while not key.is_pressed('ctrl'):
            sleep(0.01)
        return py.position()

    def _capture_pos(self, label):
        self.set_instr(f"Move mouse to the {label.upper()}, then hold CTRL")
        self.log(f"Waiting for {label}...")
        x, y = self.wait_for_ctrl()
        return x, y

    def _capture_region(self, label):
        self.set_instr(f"Move to the UPPER-LEFT corner of {label.upper()}, then hold CTRL")
        self.log(f"Waiting for {label} upper-left...")
        x1, y1 = self.wait_for_ctrl()
        self.set_instr(f"Move to the BOTTOM-RIGHT corner of {label.upper()}, then hold CTRL")
        self.log(f"Waiting for {label} bottom-right...")
        x2, y2 = self.wait_for_ctrl()
        return x1, y1, x2 - x1, y2 - y1

    # ---------------------------------------------------- individual Set ----

    def _set_capture_ui(self, capturing):
        state = 'disabled' if capturing else 'normal'
        self._ui(self.setup_all_btn.configure, state=state)
        for btn in self.cfg_set_btns.values():
            self._ui(btn.configure, state=state)
        if not capturing:
            self._check_all_set()

    def _capture_item(self, key_id, kind):
        if self.capturing or self.detect:
            return
        self.capturing = True
        self._set_capture_ui(True)
        threading.Thread(target=self._capture_item_thread,
                         args=(key_id, kind), daemon=True).start()

    def _capture_item_thread(self, key_id, kind):
        label = next(lbl for k, lbl, _ in CFG_ITEMS if k == key_id)
        try:
            self._ui(self.cfg_set_btns[key_id].configure, text='...')
            self._ui(self.cfg_val_vars[key_id].set, 'Capturing...')
            self.set_status(f"Capturing {label}...", '#d29922')

            if kind == 'pos':
                x, y = self._capture_pos(label)
                self.pos[key_id] = (x, y)
                self.log(f"{label}: ({x}, {y})")
                self._ui(self.cfg_val_vars[key_id].set, f"({x}, {y})")
                # update label color to green
                self._ui(lambda: self.cfg_val_vars[key_id].set(f"({x}, {y})"))
                self._mark_row_color(key_id, '#3fb950')
            else:
                x, y, w, h = self._capture_region(label)
                self.pos[key_id] = (x, y, w, h)
                ss = py.screenshot(region=(x, y, w, h))
                self.ss[key_id] = ss
                if key_id == 'chest':
                    ss.save('img.jpeg')
                self.log(f"{label}: ({x}, {y})  {w}×{h}")
                self._ui(self.cfg_val_vars[key_id].set, f"({x}, {y})  {w}×{h}")
                self._mark_row_color(key_id, '#3fb950')

        except Exception as e:
            self.log(f"Capture error: {e}")
            self._ui(self.cfg_val_vars[key_id].set, "Error")
            self._mark_row_color(key_id, '#f85149')
        finally:
            self._ui(self.cfg_set_btns[key_id].configure, text='Set')
            self.capturing = False
            self._set_capture_ui(False)
            self._check_all_set()

    def _mark_row_color(self, key_id, color):
        def _do():
            # the value label is the second Label child of the row frame
            row = self.cfg_set_btns[key_id].master
            for child in row.winfo_children():
                if isinstance(child, tk.Label) and child.cget('font') == 'Consolas 8':
                    child.configure(fg=color)
                    break
        self._ui(_do)

    def _check_all_set(self):
        all_set = all(self.pos[k] is not None for k, *_ in CFG_ITEMS) and \
                  all(self.ss[k] is not None for k in self.ss)
        if all_set and not self.setup_done:
            self.setup_done = True
            self.set_status("Ready to fish — press Start", '#3fb950')
            self.set_instr("All positions configured. Press Start when ready.")
        if all_set:
            self._ui(self.start_btn.configure, state='normal')
        else:
            self._ui(self.start_btn.configure, state='disabled')

    # ---------------------------------------------------- Setup All --------

    def start_setup_all(self):
        if self.capturing or self.detect:
            return
        self.capturing = True
        self._set_capture_ui(True)
        threading.Thread(target=self._setup_all_thread, daemon=True).start()

    def _setup_all_thread(self):
        try:
            self.set_status("Setting up...", '#d29922')
            for key_id, label, kind in CFG_ITEMS:
                self._ui(self.cfg_set_btns[key_id].configure, text='...')
                self._ui(self.cfg_val_vars[key_id].set, 'Capturing...')
                if kind == 'pos':
                    x, y = self._capture_pos(label)
                    self.pos[key_id] = (x, y)
                    self.log(f"{label}: ({x}, {y})")
                    self._ui(self.cfg_val_vars[key_id].set, f"({x}, {y})")
                    self._mark_row_color(key_id, '#3fb950')
                else:
                    x, y, w, h = self._capture_region(label)
                    self.pos[key_id] = (x, y, w, h)
                    ss = py.screenshot(region=(x, y, w, h))
                    self.ss[key_id] = ss
                    if key_id == 'chest':
                        ss.save('img.jpeg')
                    self.log(f"{label}: ({x}, {y})  {w}×{h}")
                    self._ui(self.cfg_val_vars[key_id].set, f"({x}, {y})  {w}×{h}")
                    self._mark_row_color(key_id, '#3fb950')
                self._ui(self.cfg_set_btns[key_id].configure, text='Set')

            self.log("Setup complete!")
        except Exception as e:
            self.log(f"Setup error: {e}")
            self.set_status("Setup failed", '#f85149')
        finally:
            self.capturing = False
            self._set_capture_ui(False)
            self._check_all_set()

    # ------------------------------------------------- Fishing controls ----

    def start_fishing(self):
        if not self.setup_done:
            return
        self.detect = True
        self.pause = False
        self._ui(self.start_btn.configure, state='disabled')
        self._ui(self.pause_btn.configure, state='normal')
        self._ui(self.stop_btn.configure, state='normal')
        self._ui(self.setup_all_btn.configure, state='disabled')
        self._ui(self.record_btn.configure, state='disabled')
        self._ui(self.clear_macro_btn.configure, state='disabled')
        for btn in self.cfg_set_btns.values():
            self._ui(btn.configure, state='disabled')
        threading.Thread(target=self._fishing_loop, daemon=True).start()

    def toggle_pause(self):
        if self.pause:
            self.pause = False
            self.set_status("Running", '#3fb950')
            self._ui(self.pause_btn.configure, text='Pause', bg='#9e6a03')
        else:
            self.pause = True
            self.set_status("Paused", '#d29922')
            self._ui(self.pause_btn.configure, text='Resume', bg='#238636')

    def stop_fishing(self):
        self.detect = False
        self.set_status("Stopped", '#f85149')
        self._ui(self.start_btn.configure, state='normal' if self.setup_done else 'disabled')
        self._ui(self.pause_btn.configure, state='disabled', text='Pause', bg='#9e6a03')
        self._ui(self.stop_btn.configure, state='disabled')
        self._ui(self.setup_all_btn.configure, state='normal')
        self._ui(self.record_btn.configure, state='normal')
        self._ui(self.clear_macro_btn.configure, state='normal')
        for btn in self.cfg_set_btns.values():
            self._ui(btn.configure, state='normal')

    # ---------------------------------------------------- Fishing loop -----

    def _fishing_loop(self):
        try:
            self._fishing_loop_inner()
        except Exception as e:
            self.log(f"Fatal loop error: {e}")
            self.set_status("Error — stopped", '#f85149')
            self.stop_fishing()

    def _fishing_loop_inner(self):
        wx, wy = self.pos['w']
        bx, by = self.pos['b']
        dx, dy = self.pos['d']
        x,  y,  width,  height  = self.pos['chest']
        ix, iy, iwidth, iheight = self.pos['ice']
        sx, sy, swidth, sheight = self.pos['water']
        chest_ss = self.ss['chest']
        ice_ss   = self.ss['ice']
        water_ss = self.ss['water']

        CAST_COOLDOWN = 1.5

        total_time = time()
        pause_time = 0
        found = 0
        ice   = 0
        last_cast = time() - CAST_COOLDOWN

        self.set_status("Running", '#3fb950')

        def do_recast():
            nonlocal last_cast
            self._click(wx, wy)
            sleep(2)
            last_cast = time()

        def refresh_stats():
            elapsed = time() - total_time - pause_time
            h = int(elapsed // 3600)
            m = int((elapsed % 3600) // 60)
            s = int(elapsed % 60)
            self.fish_var.set(f"Fish Found: {found}")
            self.ice_var.set(f"Ice Reformed: {ice}")
            self.time_var.set(f"Time: {h:02d}:{m:02d}:{s:02d}")

        last_debug = 0

        while self.detect:
            if self.pause:
                paused_at = time()
                while self.pause and self.detect:
                    sleep(0.1)
                pause_time += time() - paused_at
                last_cast   = time()
                continue

            cooldown_left = CAST_COOLDOWN - (time() - last_cast)
            if cooldown_left > 0:
                if time() - last_debug >= 1.0:
                    self.log(f'[debug] cast cooldown: {cooldown_left:.1f}s remaining')
                    last_debug = time()
                self._ui(refresh_stats)
                sleep(0.1)
                continue

            # uranium check — if water block no longer looks like water, drill it
            try:
                py.locateOnScreen(water_ss,
                                  region=(sx - 10, sy - 10, swidth + 10, sheight + 10),
                                  confidence=0.6)
                water_ok = True
            except py.ImageNotFoundException:
                water_ok = False

            if not water_ok:
                self.log('[debug] Water: MISMATCH → uranium detected, drilling')
                self._click(dx, dy)
                sleep(0.5)
                do_recast()
                continue

            # chest / fish check
            try:
                py.locateOnScreen(chest_ss,
                                  region=(x - 10, y - 10, width + 10, height + 10),
                                  confidence=0.9)
                chest_ok = True
            except py.ImageNotFoundException:
                chest_ok = False

            if time() - last_debug >= 1.0:
                self.log(f'[debug] Water: OK | Chest: {"visible (waiting)" if chest_ok else "GONE (fish!)"}')
                last_debug = time()

            if not chest_ok:
                self.log('Fish found!')
                found += 1
                self._click(wx, wy)
                sleep(0.5)

                # ice check
                ice_time = time()
                while time() - ice_time <= 0.3:
                    try:
                        if py.locateOnScreen(ice_ss,
                                             region=(ix - 10, iy - 10, iwidth + 10, iheight + 10),
                                             confidence=0.9):
                            self.log('Ice found — drilling')
                            ice += 1
                            self._click(dx, dy)
                            sleep(0.5)
                            self._click(wx, wy)
                            sleep(0.5)
                            self._click(bx, by)
                            sleep(0.5)
                            break
                    except py.ImageNotFoundException:
                        break

                # macro trigger
                try:
                    macro_trigger = max(1, int(self.trigger_var.get()))
                except ValueError:
                    macro_trigger = 18
                if self.macro.has_macro() and found % macro_trigger == 0:
                    self.log(f'Stack full ({found} fish) — running macro')
                    self.set_status('Running macro...', '#d29922')
                    self.macro.play(self._click)
                    self.log('Macro complete — resuming')
                    self.set_status('Running', '#3fb950')

                do_recast()

            self._ui(refresh_stats)
            sleep(0.1)

        elapsed = time() - total_time - pause_time
        h = int(elapsed // 3600)
        m = int((elapsed % 3600) // 60)
        s = int(elapsed % 60)
        self.log("--- Session ended ---")
        self.log(f"Fish Found: {found}  |  Ice Reformed: {ice}")
        self.log(f"Time: {h:02d}:{m:02d}:{s:02d}")
        if found:
            self.log(f"Ice rate: {ice / found * 100:.1f}% per catch")

    def _click(self, x, y):
        old_pos = wapi.GetCursorPos()
        try:
            wapi.SetCursorPos((x, y))
        except Exception as e:
            self.log(f"Click error: {e}")
        wapi.mouse_event(wcon.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        sleep(0.1)
        wapi.mouse_event(wcon.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        wapi.SetCursorPos(old_pos)

    # ------------------------------------------------------------ Macro -----

    def _toggle_recording(self):
        if self.macro.is_recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self):
        self.macro.start()
        self._ui(self.record_btn.configure, text='Stop', bg='#b62324')
        self._ui(self.macro_status_var.set, 'Recording — click to capture steps')
        self.set_status('Recording macro...', '#f85149')

    def _stop_recording(self):
        self.macro.stop()
        self._ui(self.record_btn.configure, text='Record', bg='#21262d')
        self._ui(self.macro_status_var.set, f'{self.macro.count} steps recorded')
        self.set_status('Macro saved', '#3fb950')

    def _clear_macro(self):
        self.macro.clear()
        self._ui(self.macro_status_var.set, 'Not recorded')

    # --------------------------------------------------------------- run ---

    def run(self):
        key.add_hotkey('esc', self.stop_fishing)
        key.add_hotkey('p', self.toggle_pause)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    def _on_close(self):
        self.detect = False
        self.root.destroy()


if __name__ == '__main__':
    AutoFishGUI().run()
