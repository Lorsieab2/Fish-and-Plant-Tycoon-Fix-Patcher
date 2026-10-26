"""The Game Mechanics window (Tools tab -> "Game Mechanics...").

One tab per game. Each tab has links to its groups, 4 per row, and one
read-only scrolling page. Text is Segoe UI 10, headings Segoe UI 12 bold, and
labels Segoe UI 9 bold in their colours, as in the Virtual Villagers and
Virtual Families patchers. Only one window is open at a time; Close or
Escape closes it. It reads nothing but the patcher's own manifests.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

import game_mechanics as gm

LABEL_COLOURS = {"VERIFIED-E": "#1b6e20", "VERIFIED-C": "#245a9a", "UNCONFIRMED": "#b00020"}
TITLES = {"fish": "Fish Tycoon", "plant": "Plant Tycoon"}

_open_window: tk.Toplevel | None = None


def open_window(parent: tk.Misc, game_id: str = "fish") -> tk.Toplevel:
    global _open_window
    if _open_window is not None and _open_window.winfo_exists():
        _open_window.deiconify()
        _open_window.lift()
        _open_window.focus_set()
        return _open_window
    window = tk.Toplevel(parent)
    window.title("Game Mechanics")
    window.geometry("980x760")
    window.minsize(640, 420)
    _open_window = window

    notebook = ttk.Notebook(window)
    notebook.pack(fill="both", expand=True, padx=10, pady=(10, 0))
    tabs = {}
    for gid in gm.GAMES:
        frame = ttk.Frame(notebook, padding=8)
        notebook.add(frame, text=TITLES[gid])
        _build_tab(frame, gm.load_page(gid))
        tabs[gid] = frame
    if game_id in tabs:
        notebook.select(tabs[game_id])

    bottom = ttk.Frame(window, padding=(10, 8))
    bottom.pack(fill="x")
    ttk.Button(bottom, text="Close", command=window.destroy).pack(side="right")
    window.bind("<Escape>", lambda _e: window.destroy())
    window.focus_set()
    return window


def _build_tab(frame: ttk.Frame, page: gm.GamePage) -> None:
    links = ttk.Frame(frame)
    links.pack(fill="x", pady=(0, 6))
    body = ttk.Frame(frame)
    body.pack(fill="both", expand=True)
    text = tk.Text(body, wrap="word", font=("Segoe UI", 10), padx=10, pady=8, relief="flat",
                   borderwidth=1, highlightthickness=0, cursor="arrow")
    scroll = ttk.Scrollbar(body, orient="vertical", command=text.yview)
    text.configure(yscrollcommand=scroll.set)
    scroll.pack(side="right", fill="y")
    text.pack(side="left", fill="both", expand=True)

    text.tag_configure("title", font=("Segoe UI", 14, "bold"), spacing3=6)
    text.tag_configure("heading", font=("Segoe UI", 12, "bold"), spacing1=12, spacing3=4)
    text.tag_configure("text", spacing3=6)
    text.tag_configure("bullet", lmargin1=8, lmargin2=26, spacing1=2)
    text.tag_configure("sub", lmargin1=30, lmargin2=44)
    text.tag_configure("patched", lmargin1=30, lmargin2=44, foreground="#5a3d00")
    for label, colour in LABEL_COLOURS.items():
        text.tag_configure(label, font=("Segoe UI", 9, "bold"), foreground=colour)

    anchors: list[tuple[str, str]] = []
    for style, line in gm.render_lines(page):
        if style == "heading":
            mark = f"group{len(anchors)}"
            text.mark_set(mark, "end-1c")
            text.mark_gravity(mark, "left")
            anchors.append((line, mark))
            text.insert("end", line + "\n", "heading")
        elif style == "bullet":
            label, _, rest = line[1:].partition("] ")
            text.insert("end", "• ", "bullet")
            text.insert("end", label, ("bullet", label))
            text.insert("end", " " + rest + "\n", "bullet")
        elif style in ("sub", "patched"):
            text.insert("end", "– " + line + "\n", style)
        else:
            text.insert("end", line + "\n", style)
    text.configure(state="disabled")

    columns = 4
    for index, (title, mark) in enumerate(anchors):
        link = tk.Label(links, text=title, fg="#0057c2", cursor="hand2", font=("Segoe UI", 9, "underline"),
                        anchor="w")
        link.grid(row=index // columns, column=index % columns, sticky="w", padx=(0, 18), pady=1)
        link.bind("<Button-1>", lambda _e, m=mark: text.yview(m))
    for column in range(columns):
        links.columnconfigure(column, weight=1)
