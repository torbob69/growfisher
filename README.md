<img width="3180" height="1344" alt="Gemini_Generated_Image_dnc22idnc22idnc2 (1)" src="https://github.com/user-attachments/assets/8b5b3c25-fe6d-41e0-ae95-a9b6bf7ca41c" />

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
