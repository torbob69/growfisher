import win32gui
import win32api
import win32con
import time
import keyboard
import ctypes
import cv2
import numpy as np

from datetime import datetime as dt
import pygetwindow as gw
from PIL import ImageGrab, Image
import win32ui
from rapidocr_onnxruntime import RapidOCR
from windows_capture import WindowsCapture, Frame, InternalCaptureControl
import threading

_ocr = RapidOCR()  # one engine instance, models load once

# per-monitor v2 — survives mixed-DPI monitors; fall back if API missing
try:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(-4)  # PER_MONITOR_AWARE_V2
except (AttributeError, OSError):
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        ctypes.windll.user32.SetProcessDPIAware()

WIN_NAME = "Growtopia"

def find_hwnd():
    hits = []
    def cb(h, _):
        t = win32gui.GetWindowText(h)
        if t.startswith(WIN_NAME):
            hits.append(h)
    win32gui.EnumWindows(cb, None)
    return hits[0] if hits else 0

HWND = find_hwnd()
print("HWND =", HWND, "title =", win32gui.GetWindowText(HWND) if HWND else "(not found)")



def click(x, y):
    lParam = (y << 16) | (x & 0xFFFF)
    win32gui.PostMessage(HWND, win32con.WM_LBUTTONDOWN, win32con.MK_LBUTTON, lParam)
    time.sleep(0.05)
    win32gui.PostMessage(HWND, win32con.WM_LBUTTONUP, 0, lParam)

def press(key):
    scan = keyboard.key_to_scan_codes(key)[0]
    vk   = win32api.MapVirtualKey(scan, 1)  # scan -> virtual key
    down = (scan << 16) | 1
    up   = (scan << 16) | 1 | (1 << 30) | (1 << 31)

    win32gui.PostMessage(HWND, win32con.WM_KEYDOWN, vk, down)
    time.sleep(0.05)
    win32gui.PostMessage(HWND, win32con.WM_KEYUP,   vk, up)
    print(f"pressed {key!r} at {dt.now()}")
    
def get_mouse_pos():
    # wait for a fresh 'x' press; suppress=True keeps the key out of the focused app
    keyboard.wait('x', suppress=True)
    x, y = win32gui.ScreenToClient(HWND, win32gui.GetCursorPos())
    print(f"cursor pos: ({x}, {y})")
    return (x, y)

def chat(text : str = "Hi welcome to torbob69's autofisher."):
    pos = get_mouse_pos()
    click(*pos)
    for letter in text:
        time.sleep(0.03)
        press(letter)
        print(f"typed {letter!r} at {dt.now()}")

    press("enter")
    click(*pos)
    
def get_area():
    print("Put your mouse at the top left of the area box")
    top_left = get_mouse_pos()
    print("Put your mouse at the bottom right of the area box")
    bottom_right = get_mouse_pos()
    
    return top_left, bottom_right

# Windows.Graphics.Capture — no flash, works occluded, captures DirectX directly.
_latest_frame = None
_frame_lock = threading.Lock()
_frame_ready = threading.Event()

_cap = WindowsCapture(window_name=WIN_NAME)

@_cap.event
def on_frame_arrived(frame: Frame, capture_control: InternalCaptureControl):
    global _latest_frame
    with _frame_lock:
        _latest_frame = frame.frame_buffer.copy()
    _frame_ready.set()

@_cap.event
def on_closed():
    pass

_cap.start_free_threaded()

def grab_window(bbox=None):
    _frame_ready.wait(timeout=2)  # blocks once at startup until first frame arrives
    with _frame_lock:
        arr = _latest_frame
    img = Image.fromarray(arr[..., :3][..., ::-1])  # BGRA → RGB
    if bbox is None:
        return img
    # WGC frame is window-relative (incl. title bar); bbox is client-relative — shift
    wl, wt, _, _ = win32gui.GetWindowRect(HWND)
    cx, cy = win32gui.ClientToScreen(HWND, (0, 0))
    ox, oy = cx - wl, cy - wt
    return img.crop((bbox[0]+ox, bbox[1]+oy, bbox[2]+ox, bbox[3]+oy))

def get_image(img_name : str):
    top_left, bottom_right = get_area()
    bbox = (*top_left, *bottom_right)  # client coords
    img = grab_window(bbox)
    img.save(f"{img_name}.png")
    return bbox


def match(area: tuple[int, int, int, int], ori_img_path: str, threshold: float = 0.85):
    hay_pil = grab_window(area)
    hay = cv2.cvtColor(np.array(hay_pil), cv2.COLOR_RGB2BGR)
    needle = cv2.imread(ori_img_path)
    res = cv2.matchTemplate(hay, needle, cv2.TM_CCOEFF_NORMED)
    _, score, _, _ = cv2.minMaxLoc(res)
    return score >= threshold

def read_text(area: tuple[int, int, int, int], digits_only: bool = False):
    # rapidocr; upscale 2x for tiny game text
    img = grab_window(area)
    img = img.resize((img.width * 2, img.height * 2))
    result, _ = _ocr(np.array(img))
    if not result:
        return ""
    text = " ".join(r[1] for r in result)
    if digits_only:
        text = "".join(c for c in text if c.isdigit())
    return text

def read_number(area: tuple[int, int, int, int]) -> int | None:
    s = read_text(area, digits_only=True)
    return int(s) if s else None

def find_numbers(area=None, min_digit_ratio: float = 0.6):
    # OCR the area (or whole window), return each numeric region separately
    img = grab_window(area) if area else grab_window()
    result, _ = _ocr(np.array(img))
    out = []
    for box, text, conf in result or []:
        digits = "".join(c for c in text if c.isdigit())
        if digits and len(digits) / max(len(text), 1) >= min_digit_ratio:
            out.append({"value": int(digits), "raw": text, "box": box, "conf": conf})
    return out

# get_image("test")