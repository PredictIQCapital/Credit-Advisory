"""German number formatting for every client-facing text.

"750.000 EUR" and "10,1%" -- not "750,000 EUR" and "10.1%". A German SME
owner or Steuerberater reading an English-formatted figure has to stop and
translate it, and a misread thousands separator is a factor-1000 error.
"""

from __future__ import annotations


def de(value: float, decimals: int = 0) -> str:
    """Format with German separators: de(1234567.891, 2) -> '1.234.567,89'."""
    s = f"{value:,.{decimals}f}"
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def en(value: float, decimals: int = 0) -> str:
    """The same figure for English readers: en(1234567.891, 2) -> '1,234,567.89'."""
    return f"{value:,.{decimals}f}"


def de_to_en(text: str) -> str:
    """Swap the separators of a German-formatted figure: '1.085.000,5' -> '1,085,000.5'."""
    return text.translate(str.maketrans({",": ".", ".": ","}))
