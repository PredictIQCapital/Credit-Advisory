"""Text from PDFs, without sending them anywhere.

Two paths, tried in order:

  1. PyMuPDF (`pip install pymupdf`), if installed: handles almost every
     digitally created PDF, including DATEV and tax-software exports.
  2. A minimal built-in reader for simple, text-based PDFs (literal strings in
     uncompressed or Flate-compressed content streams). It exists so the
     product works with zero dependencies and so the tests are deterministic.

Scanned PDFs contain images, not text; neither path reads them. Those need the
AI provider (vision) or manual entry -- the caller is told which.
"""

from __future__ import annotations

import re
import zlib

_STREAM = re.compile(rb"<<(.*?)>>\s*stream\r?\n(.*?)\r?\nendstream", re.S)
_TOKEN = re.compile(rb"\((?:\\.|[^\\)])*\)|\[[^\]]*\]\s*TJ|T\*|Td|TD|Tm|ET|'|\"")


def _unescape(raw: bytes) -> str:
    out = bytearray()
    i = 0
    while i < len(raw):
        c = raw[i]
        if c == 0x5C and i + 1 < len(raw):          # backslash
            n = raw[i + 1]
            if n in b"nrtbf":
                out += {ord("n"): b"\n", ord("r"): b"\r", ord("t"): b"\t",
                        ord("b"): b"\b", ord("f"): b"\f"}[n]
                i += 2
            elif 0x30 <= n <= 0x37:                  # octal
                j = i + 1
                while j < len(raw) and j < i + 4 and 0x30 <= raw[j] <= 0x37:
                    j += 1
                out.append(int(raw[i + 1:j], 8) & 0xFF)
                i = j
            else:
                out.append(n)
                i += 2
        else:
            out.append(c)
            i += 1
    return out.decode("latin-1")


def _builtin(data: bytes) -> str:
    lines: list[str] = []
    for header, body in _STREAM.findall(data):
        if b"/FlateDecode" in header:
            try:
                body = zlib.decompress(body)
            except zlib.error:
                continue
        elif b"/Filter" in header:
            continue                                  # images, other encodings
        if b"Tj" not in body and b"TJ" not in body:
            continue
        current: list[str] = []
        for tok in _TOKEN.findall(body):
            if tok.startswith(b"("):
                current.append(_unescape(tok[1:-1]))
            elif tok.endswith(b"TJ"):
                parts = re.findall(rb"\((?:\\.|[^\\)])*\)", tok)
                current.append("".join(_unescape(p[1:-1]) for p in parts))
            else:                                     # a line break operator
                if current:
                    lines.append("".join(current))
                    current = []
        if current:
            lines.append("".join(current))
    return "\n".join(lines)


def pdf_to_text(data: bytes) -> tuple[str, str]:
    """Return (text, method). Empty text means: no extractable text layer."""
    if not data.startswith(b"%PDF"):
        return "", "kein PDF"
    try:
        import pymupdf  # type: ignore[import-not-found]

        with pymupdf.open(stream=data, filetype="pdf") as doc:
            text = "\n".join(page.get_text() for page in doc)
        if text.strip():
            return text, "pymupdf"
    except Exception:  # noqa: BLE001 - optional dependency, any failure -> fallback
        pass
    text = _builtin(data)
    return text, "builtin"
