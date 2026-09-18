"""Report rendering: client report, HTML, letters, printable forms, summaries."""

from .html import markdown_to_html
from .report import render_markdown
from .summary import result_summary

__all__ = ["markdown_to_html", "render_markdown", "result_summary"]
