<div align="center">
  <img width="120" height="120" alt="growfisher" src="https://github.com/user-attachments/assets/47c29fa4-9234-4704-beaa-cef4912e5ce3" />

  <h1>Growfisher</h1>
  <p>Computer vision based Growtopia autofishing tool.</p>

  <a href="https://github.com/torbob69/autofisher/releases/latest">
    <img src="https://img.shields.io/github/v/release/torbob69/autofisher?label=download&style=for-the-badge" alt="Download" />
  </a>
</div>

---

## The problem with existing autofishing tools

**Most macro-based tools lock your screen.** They simulate mouse clicks at fixed screen coordinates, which means you cannot open other tabs, watch YouTube, or do anything else while the bot runs. The moment you alt-tab or cover the window, it breaks.

**Proxy and packet-based tools break on every update.** Tools that work by intercepting or modifying Growtopia's network traffic hook into the game's internals. Every time Growtopia pushes an update, these tools stop working and you have to wait for the developer to patch them.

---

## Why Growfisher is different

Growfisher uses computer vision to watch the game the same way a human would — by looking at the screen. It detects the fishing state visually and responds accordingly.

- **Update-proof.** It does not touch game files, memory, or network traffic. Growtopia updates cannot break it.
- **Multitask-friendly.** Input is sent directly to the game's window handle, so the game does not need to be in focus. You can watch YouTube, browse, or work while it runs.
- **Reliable.** The only things that can interrupt it are a bad internet connection or Growtopia's own servers going down.

---

## Features

- Automatic cast, wait, and recycle when spot is full
- Detects splash, bite, and empty line events via template matching
- Sends input directly to the Growtopia window — works minimized or behind other windows
- No DLL injection, no packet manipulation, no game file modification

---

## System Requirements

| | |
|---|---|
| **OS** | Windows 10 / 11 (64-bit) |
| **Runtime** | [WebView2](https://developer.microsoft.com/en-us/microsoft-edge/webview2/) (pre-installed on Windows 11, auto-installs on Windows 10) |
| **Game** | Growtopia (Windows client) |
| **Hardware** | Any PC capable of running Growtopia |

> Building from source additionally requires Python 3.11+ and Node.js 18+.

---

## Installation

### Option 1 — Download (recommended)

Download the latest `Growfisher.exe` from the [Releases](https://github.com/torbob69/autofisher/releases/latest) page. No Python or Node.js required — just run it.

### Option 2 — Build from source

**Requirements:** Python 3.11+, Node.js 18+

```powershell
# Clone the repo
git clone https://github.com/torbob69/autofisher
cd autofisher

# Create and activate a virtual environment
python -m venv venv
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
cd ui && npm install && cd ..

# Build
cd ui && npm run build && cd ..
pyinstaller gui.spec
```

The exe will be at `dist\Growfisher.exe`.

---

## Disclaimer

Growtopia's rules prohibit all forms of automation, including bots and macros, regardless of method. Using this tool is against Growtopia's Terms of Service and may result in a permanent account suspension. **Use at your own risk.**
