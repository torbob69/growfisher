from autofisher import Autofisher, CONFIG_PATH, CONFIG_KEYS
from utils import get_mouse_pos, get_area, get_image
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text
from rich.table import Table
from rich.live import Live
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.styles import Style
from prompt_toolkit.patch_stdout import patch_stdout
from threading import Thread
import os, time, json, msvcrt

ITEM_TYPES = {
    "water_pos":      ("pos",    None),
    "bait_pos":       ("pos",    None),
    "deto_pos":       ("pos",    None),
    "recycle_pos":    ("pos",    None),
    "first_fish_pos": ("pos",    None),
    "uranium_img":    ("region", "uranium"),
    "splash_img":     ("region", "splash"),
    "empty_fish_img": ("region", "empty_fish"),
}

console = Console()

BANNER = r'''
     ██████╗ ██████╗  ██████╗ ██╗    ██╗███████╗██╗███████╗██╗  ██╗███████╗██████╗
    ██╔════╝ ██╔══██╗██╔═══██╗██║    ██║██╔════╝██║██╔════╝██║  ██║██╔════╝██╔══██╗
    ██║  ███╗██████╔╝██║   ██║██║ █╗ ██║█████╗  ██║███████╗███████║█████╗  ██████╔╝
    ██║   ██║██╔══██╗██║   ██║██║███╗██║██╔══╝  ██║╚════██║██╔══██║██╔══╝  ██╔══██╗
    ╚██████╔╝██║  ██║╚██████╔╝╚███╔███╔╝██║     ██║███████║██║  ██║███████╗██║  ██║
     ╚═════╝ ╚═╝  ╚═╝ ╚═════╝  ╚══╝╚══╝ ╚═╝     ╚═╝╚══════╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝
'''

COMMANDS = {
    "/setup":  "recalibrate all positions & regions",
    "/start":  "start the fishing loop",
    "/stop":   "stop the fishing loop",
    "/status": "show live state (fish caught, elapsed)",
    "/config": "print saved config",
    "/help":   "show this list",
    "/quit":   "exit",
}

BORDER = "#5f6a7a"
ACCENT = "#e91e63"
BOX_W  = 72


class SlashCompleter(Completer):
    # prefix-based completion: only fires when input starts with '/', matches by prefix
    def __init__(self, commands):
        self.commands = commands

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if not text.startswith("/"):
            return
        for cmd, desc in self.commands.items():
            if cmd.startswith(text):
                yield Completion(
                    cmd,
                    start_position=-len(text),
                    display=cmd,
                    display_meta=desc,
                )


_prompt_style = Style.from_dict({
    "border":  BORDER,
    "arrow":   f"{ACCENT} bold",
    "":        "#ffffff",
    "completion-menu":                     f"bg:#1a1a2e",
    "completion-menu.completion":          f"bg:#1a1a2e #c0c0c0",
    "completion-menu.completion.current":  f"bg:{ACCENT} #ffffff bold",
    "completion-menu.meta.completion":         f"bg:#141422 #808a99",
    "completion-menu.meta.completion.current": f"bg:{ACCENT} #ffffff",
    "bottom-toolbar":         f"bg:default {BORDER}",
    "bottom-toolbar.text":    f"bg:default {BORDER}",
})


_session = PromptSession(
    completer=SlashCompleter(COMMANDS),
    style=_prompt_style,
    complete_while_typing=True,
)


def bordered_prompt():
    with patch_stdout(raw=True):
        return _session.prompt(HTML(
            f'<style fg="{ACCENT}"><b>› </b></style>'
        )).strip()


def gradient(text, colors=((66, 133, 244), (156, 39, 176), (233, 30, 99))):
    t = Text()
    for line in text.splitlines():
        n = max(len(line) - 1, 1)
        for i, ch in enumerate(line):
            pos = i / n * (len(colors) - 1)
            idx = min(int(pos), len(colors) - 2)
            frac = pos - idx
            a, b = colors[idx], colors[idx + 1]
            r = round(a[0] + (b[0] - a[0]) * frac)
            g = round(a[1] + (b[1] - a[1]) * frac)
            bl = round(a[2] + (b[2] - a[2]) * frac)
            t.append(ch, style=f"rgb({r},{g},{bl})")
        t.append("\n")
    return t


def ts():
    return f"[dim]{time.strftime('%H:%M:%S')}[/dim]"


def choose(title, options):
    # options: list of (value, label). arrow up/down + enter to pick, esc to cancel.
    idx = 0
    def render():
        t = Text()
        t.append(f"{title} ", style="bold cyan")
        t.append("(↑/↓ to move, Enter to select, Esc to cancel)\n", style="dim")
        for i, (_, label) in enumerate(options):
            if i == idx:
                t.append("  › ", style="bold magenta")
                t.append_text(Text.from_markup(f"[bold]{label}[/bold]"))
                t.append("\n")
            else:
                t.append("    ")
                t.append_text(Text.from_markup(f"[dim]{label}[/dim]"))
                t.append("\n")
        return t

    with Live(render(), console=console, refresh_per_second=30, transient=True) as live:
        while True:
            ch = msvcrt.getch()
            if ch == b"\r":
                return options[idx][0]
            if ch == b"\x1b":
                return None
            if ch in (b"\xe0", b"\x00"):
                d = msvcrt.getch()
                if d == b"H": idx = (idx - 1) % len(options)
                elif d == b"P": idx = (idx + 1) % len(options)
            live.update(render())


class Session:
    def __init__(self):
        self.af = None
        self.thread = None
        self.started_at = None

    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def _log(self, msg):
        console.print(f"{ts()} [green]LOG[/green]  {msg}")

    def _ensure(self):
        if self.af is None:
            self.af = Autofisher()
            self.af.log = self._log

    def start(self):
        if self.running():
            console.print(f"{ts()} [yellow]already running[/yellow]")
            return
        self._ensure()
        self.af.stop_event.clear()
        self.started_at = time.time()
        self.thread = Thread(target=self.af.loop, daemon=True)
        self.thread.start()
        console.print(f"{ts()} [green]started[/green]  press [cyan]/stop[/cyan] to end")

    def stop(self):
        if not self.running():
            console.print(f"{ts()} [dim]not running[/dim]")
            return
        self.af.stop_event.set()
        console.print(f"{ts()} [yellow]stopping…[/yellow]")
        self.thread.join(timeout=5)
        self.started_at = None

    def setup(self):
        if self.running():
            console.print(f"{ts()} [red]stop the loop first[/red]")
            return

        while True:
            data = json.load(open(CONFIG_PATH)) if os.path.exists(CONFIG_PATH) else {}

            options = []
            for k in CONFIG_KEYS:
                v = data.get(k)
                shown = str(v) if v is not None else "not set"
                options.append((k, f"{k:<16} = {shown}"))
            options.append(("all",    "── recapture all ──"))
            options.append(("cancel", "── done / cancel ──"))

            pick = choose("select a config to (re)setup", options)

            if pick is None or pick == "cancel":
                console.print(f"{ts()} [dim]setup closed[/dim]")
                return
            if pick == "all":
                if os.path.exists(CONFIG_PATH):
                    os.remove(CONFIG_PATH)
                    console.print(f"{ts()} [dim]cleared {CONFIG_PATH}[/dim]")
                self.af = Autofisher()
                self.af.log = self._log
                console.print(f"{ts()} [green]all set[/green]")
                continue

            key = pick
            kind, save_name = ITEM_TYPES[key]

            console.print(Panel.fit(
                f"Capturing [bold cyan]{key}[/bold cyan]\n"
                "Press [bold]X[/bold] at the requested spot"
                + (" (top-left, then bottom-right)" if kind == "region" else ""),
                border_style="cyan"))

            if kind == "pos":
                val = get_mouse_pos()
            elif save_name:
                val = get_image(save_name)                    # captures + saves png
            else:
                tl, br = get_area()
                val = (*tl, *br)

            data[key] = list(val) if isinstance(val, tuple) else val
            with open(CONFIG_PATH, "w") as f:
                json.dump(data, f, indent=2)
            console.print(f"{ts()} [green]{key} → {val}[/green]")
            self.af = None  # reload on next /start

    def status(self):
        if not self.running():
            console.print(Panel.fit("[dim]idle — /start to run[/dim]", border_style="dim"))
            return
        elapsed = int(time.time() - self.started_at)
        h, m, s = elapsed // 3600, (elapsed % 3600) // 60, elapsed % 60
        fish = getattr(self.af, "fish", 0)
        console.print(Panel.fit(
            f"[green]RUNNING[/green]   fish: [bold cyan]{fish}[/bold cyan]"
            f"   elapsed: [bold]{h:02d}:{m:02d}:{s:02d}[/bold]",
            border_style="green"))

    def show_config(self):
        if not os.path.exists(CONFIG_PATH):
            console.print(f"{ts()} [red]{CONFIG_PATH} not found — run /setup[/red]")
            return
        data = json.load(open(CONFIG_PATH))
        t = Table(border_style="dim", show_header=True, header_style="bold cyan")
        t.add_column("key"); t.add_column("value", style="magenta")
        for k, v in data.items():
            t.add_row(k, str(v))
        console.print(t)


def help_panel():
    t = Table.grid(padding=(0, 2))
    t.add_column(style=f"{ACCENT} bold", no_wrap=True)
    t.add_column(style="dim")
    for k, v in COMMANDS.items():
        t.add_row(k, v)
    return Panel(t, border_style=BORDER, title=f"[bold]commands[/bold]",
                 title_align="left", padding=(0, 1))


def welcome_panel():
    body = Text.from_markup(
        f"[bold]Growfisher[/bold] [dim]v2 · CLI[/dim]\n"
        f"[dim]type[/dim] [bold {ACCENT}]/[/bold {ACCENT}][dim] to see commands · [/dim]"
        f"[bold {ACCENT}]Ctrl+C[/bold {ACCENT}][dim] to quit[/dim]"
    )
    return Panel(body, border_style=BORDER, padding=(0, 1))


def main():
    console.clear()
    console.print(gradient(BANNER))
    console.print(welcome_panel())
    console.print()

    session = Session()
    while True:
        try:
            cmd = bordered_prompt().lower()
        except (EOFError, KeyboardInterrupt):
            print(); cmd = "/quit"

        if   cmd == "/quit":   session.stop(); console.print(f"[{BORDER}]bye 👋[/]"); break
        elif cmd == "/start":  session.start()
        elif cmd == "/stop":   session.stop()
        elif cmd == "/setup":  session.setup()
        elif cmd == "/status": session.status()
        elif cmd == "/config": session.show_config()
        elif cmd == "/help":   console.print(help_panel())
        elif cmd:              console.print(f"{ts()} [red]unknown:[/red] {cmd}  ([dim]/help[/dim])")


if __name__ == "__main__":
    main()
