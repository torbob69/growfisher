<img width="500" height="500" alt="growfisher" src="https://github.com/user-attachments/assets/47c29fa4-9234-4704-beaa-cef4912e5ce3" />


# Growfisher
### Computer vision based Growtopia autofishing tool.

---

## The problem with existing autofishing tools

**Most macro-based tools lock your screen.** They simulate mouse clicks at fixed screen coordinates, which means you cannot open other tabs, watch YouTube, or do anything else while the bot runs. The moment you alt-tab or cover the window, it breaks.

**Proxy and packet-based tools break on every update.** Tools that work by intercepting or modifying Growtopia's network traffic hook into the game's internals. Every time Growtopia pushes an update, these tools stop working and you have to wait for the developer to patch them.

---

## Why Growfisher is different

Growfisher uses computer vision to watch the game the same way a human would — by looking at the screen. It detects the fishing state visually (splash, bite, empty line) and responds accordingly. This makes it:

- **Update-proof.** It does not touch game files, memory, or network traffic. Growtopia updates cannot break it.
- **Multitask-friendly.** Input is sent directly to the game's window handle, so the game does not need to be focused. You can watch YouTube, browse, or work while it runs.
- **Reliable.** The only things that can interrupt it are a bad internet connection or Growtopia's own servers going down.

---

## Features

- Automatic cast, wait, and recycle fish when full spot
- Detects splash, bite, and empty line events via template matching
- Sends input directly to the Growtopia window, works minimized or behind other windows
- No DLL injection, no packet manipulation, no game file modification

---

## Disclaimer

Growtopia's rules prohibit all forms of automation, including bots and macros, regardless of method. Using this tool is against Growtopia's Terms of Service and may result in a permanent account suspension. Use at your own risk.

## Installation

### Option 1 — Download the exe (easiest)

Go to the [Releases](../../releases/latest) page and download `Growfisher.exe`. No Python or Node required.

### Option 2 — Build from source

**Requirements:** Python 3.11+, Node.js 18+

```powershell
# 1. Clone and enter the repo
git clone https://github.com/torbob69/autofisher

# 2. Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Install Node dependencies
cd ui && npm install && cd ..

# 5. Build the exe
cd ui && npm run build && cd ..
pyinstaller gui.spec
```

The exe will be at `dist\gui.exe`.

---

## Setup and Usage Guide
Will be announced later.
