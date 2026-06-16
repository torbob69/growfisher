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
from PIL import ImageGrab

# make process DPI-aware so GetCursorPos and ImageGrab agree on pixels
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
    # ponytail: wait for a fresh 'x' press; suppress=True keeps the key out of the focused app
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

def get_image(img_name : str):
    top_left, bottom_right = get_area()
    # client coords -> screen coords for ImageGrab
    l, t = win32gui.ClientToScreen(HWND, top_left)
    r, b = win32gui.ClientToScreen(HWND, bottom_right)
    img = ImageGrab.grab(bbox=(l, t, r, b), all_screens=True)
    img.save(f"{img_name}.png")
    return img


# get_image("testing")
# get_point = get_mouse_pos()
# print(f"pointed: {get_point}")