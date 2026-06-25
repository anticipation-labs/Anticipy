"""CREATE real, printable artifacts — the 'make the actual thing' capability the product was missing.

The product could decide/read/draft, but never CREATE an artifact or DO a real-world action (the door-sign
test: hear it -> infer -> make the sign -> print it). This module is the create + fulfillment legs:
  make_sign(...)      -> render a real, printable letter-size PDF sign (returns the file path)
  prepare_print(pdf)  -> find the default printer + build the print command WITHOUT running it
  send_to_print(pdf)  -> actually print (only ever called after an explicit human YES — physical action)

Physical printing is a real-world action (paper/ink) -> it follows the autonomy line: PREPARE + ask, never
auto-print. send_to_print is the YES leg only.
"""
from __future__ import annotations

import os
import subprocess
import textwrap


def _artifacts_dir() -> str:
    base = os.environ.get("ANTICIPY_ARTIFACTS_DIR") or os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "engine", ".anticipy-data", "artifacts")
    os.makedirs(base, exist_ok=True)
    return base


def make_sign(headline: str, sub: str = "", out_path: str | None = None, slug: str = "sign") -> str:
    """Render a REAL printable letter-size PDF sign (big centered headline + sub line, bordered).
    Returns the path to the created file. Pure local generation — no network."""
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.lib import colors
    from reportlab.pdfgen import canvas

    out_path = out_path or os.path.join(_artifacts_dir(), f"{slug}.pdf")
    W, H = letter
    c = canvas.Canvas(out_path, pagesize=letter)

    # thick border
    c.setLineWidth(8)
    c.setStrokeColor(colors.black)
    c.rect(0.6 * inch, 0.6 * inch, W - 1.2 * inch, H - 1.2 * inch)

    # headline: wrap to fit, draw big + centered
    headline = (headline or "").strip().upper()
    lines = textwrap.wrap(headline, width=14) or [headline]
    font_size = 90 if max((len(l) for l in lines), default=0) <= 11 else 64
    c.setFont("Helvetica-Bold", font_size)
    y = H / 2 + (len(lines) - 1) * font_size * 0.6 + 0.7 * inch
    for line in lines:
        c.drawCentredString(W / 2, y, line)
        y -= font_size * 1.15

    # sub line(s)
    sub = (sub or "").strip()
    if sub:
        c.setFont("Helvetica", 28)
        sy = y - 0.4 * inch
        for sline in (textwrap.wrap(sub, width=40) or [sub]):
            c.drawCentredString(W / 2, sy, sline)
            sy -= 34

    c.showPage()
    c.save()
    return out_path


def list_printers() -> list[str]:
    try:
        out = subprocess.run(["lpstat", "-a"], capture_output=True, text=True, timeout=5).stdout
        return [ln.split()[0] for ln in out.splitlines() if ln.strip()]
    except Exception:
        return []


def default_printer() -> str | None:
    try:
        out = subprocess.run(["lpstat", "-d"], capture_output=True, text=True, timeout=5).stdout
        if ":" in out:
            p = out.split(":", 1)[1].strip()
            return p or None
    except Exception:
        pass
    return None


def prepare_print(pdf_path: str) -> dict:
    """Build the print job WITHOUT running it — physical printing is a real-world action that follows the
    autonomy line (PREPARE, then ask). Returns the target printer, the exact command, and readiness."""
    printer = default_printer()
    cmd = ["lp"] + (["-d", printer] if printer else []) + [pdf_path]
    return {
        "printer": printer,
        "printers_available": list_printers(),
        "command": " ".join(cmd),
        "artifact": pdf_path,
        "ready": bool(printer and os.path.exists(pdf_path)),
    }


def send_to_print(pdf_path: str, printer: str | None = None) -> dict:
    """ACTUALLY print — the YES leg only (call after an explicit human confirm). Returns the lp result."""
    printer = printer or default_printer()
    cmd = ["lp"] + (["-d", printer] if printer else []) + [pdf_path]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    return {"printer": printer, "command": " ".join(cmd), "ok": r.returncode == 0,
            "stdout": r.stdout.strip(), "stderr": r.stderr.strip()}
