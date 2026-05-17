"""Anticipy desktop entry point (PyInstaller --windowed target).

A double-clickable, no-Terminal Tkinter window that runs the REAL
new pipeline locally in-process (no server): app.e2e.flow.run_flow
(synthetic-wearer-voice -> local parakeet ASR + audio stack ->
frozen reasoning via OpenRouter cloud -> proactive_day -> comms ->
a real proposal). Big models are cloud via OpenRouter exactly as
the engine does; only the small audio models are local and are
fetched on first run into the user-writable data dir.

No hardcoded /Users/ paths: the data dir comes from
platform_adapter.data_dir() (env/HOME based) and bundle resources
via sys._MEIPASS. The OpenRouter key is read from the user config
~/.anticipy/.env (the exact file platform_adapter already loads);
if missing, the window asks for it once and writes it there.
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

CONFIG = Path(os.path.expanduser("~/.anticipy/.env"))


def _have_key() -> bool:
    if os.environ.get("OPENROUTER_API_KEY", "").startswith("sk-or-"):
        return True
    if CONFIG.exists():
        for line in CONFIG.read_text().splitlines():
            if line.strip().startswith("OPENROUTER_API_KEY="):
                v = line.split("=", 1)[1].strip().strip('"').strip("'")
                if v.startswith("sk-or-"):
                    os.environ["OPENROUTER_API_KEY"] = v
                    return True
    return False


def _save_key(k: str) -> None:
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    existing = ""
    if CONFIG.exists():
        existing = "\n".join(
            ln for ln in CONFIG.read_text().splitlines()
            if not ln.strip().startswith("OPENROUTER_API_KEY="))
    CONFIG.write_text(
        (existing + "\n" if existing else "")
        + f'OPENROUTER_API_KEY={k.strip()}\n')
    os.environ["OPENROUTER_API_KEY"] = k.strip()


def main() -> None:
    import tkinter as tk
    from tkinter import scrolledtext

    root = tk.Tk()
    root.title("Anticipy")
    root.geometry("760x620")
    root.configure(bg="#0C0C0C")

    head = tk.Label(root, text="Anticipy", fg="#F5F0EB", bg="#0C0C0C",
                    font=("Georgia", 26))
    head.pack(pady=(22, 4))
    sub = tk.Label(root,
                   text="Listening, then resolving what it means.",
                   fg="#8A8A8A", bg="#0C0C0C", font=("Helvetica", 13))
    sub.pack()

    out = scrolledtext.ScrolledText(
        root, width=88, height=24, bg="#161616", fg="#FAFAFA",
        insertbackground="#FAFAFA", relief="flat", font=("Menlo", 11))
    out.pack(padx=20, pady=18, fill="both", expand=True)

    def log(s: str) -> None:
        out.insert("end", s + "\n")
        out.see("end")
        root.update_idletasks()

    def need_key_ui() -> None:
        log("First run: paste your OpenRouter API key (sk-or-...).")
        frm = tk.Frame(root, bg="#0C0C0C")
        frm.pack(pady=6)
        ent = tk.Entry(frm, width=54, show="*")
        ent.pack(side="left", padx=6)

        def submit() -> None:
            k = ent.get().strip()
            if k.startswith("sk-or-"):
                _save_key(k)
                frm.destroy()
                threading.Thread(target=run_pipeline,
                                  daemon=True).start()
            else:
                log("That does not look like an sk-or- key.")
        tk.Button(frm, text="Save and run", command=submit).pack(
            side="left")

    def run_pipeline() -> None:
        log("Starting the real pipeline (this takes about a minute,")
        log("nothing is mocked)...")
        try:
            here = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
            if str(here) not in sys.path:
                sys.path.insert(0, str(here))
            from app.e2e.flow import run_flow

            fr = run_flow(do_mic=True)
            log("")
            log("Heard: " + (fr.transcript or "(none)"))
            log("Reasoning decision: " + (fr.engine_decision or "n/a"))
            log("")
            log("PROPOSAL: " + (fr.proposal or "(no proposal)"))
            log("")
            for s in fr.stages:
                tag = "real" if s.real else (
                    "gated" if s.gated else "fail")
                log(f"  [{tag}] {s.name}: {s.detail}")
        except Exception as e:
            import traceback
            log("ERROR: " + repr(e))
            log(traceback.format_exc())

    def boot() -> None:
        if _have_key():
            threading.Thread(target=run_pipeline, daemon=True).start()
        else:
            need_key_ui()

    root.after(400, boot)
    root.mainloop()


if __name__ == "__main__":
    main()
