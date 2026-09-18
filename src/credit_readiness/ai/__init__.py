"""AI layer: reading documents and explaining results. Never scoring.

See providers.py for the provider choice and docs/ai-and-data-protection.md
for the data-protection rules that govern it.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from .explain import explain, template_explanation, violates_guardrails
from .extraction import FIELDS, ExtractionResult, check_figures, parse_confirmed, to_statements
from .providers import AIError, AnthropicProvider, RulesProvider, get_provider

AI_LOG = "ai_log.json"


def log_ai_use(store, case_id: str, provider, purpose: str, ok: bool,
               detail: str = "", input_bytes: bytes = b"", actor: str = "") -> None:
    """Record every AI call per case: what, when, which provider, by whom.

    Only a hash of the input is stored, never the content itself -- the log
    proves what was processed without becoming a second copy of the data.
    """
    raw = store.read_artifact(case_id, AI_LOG)
    entries = json.loads(raw) if raw else []
    entries.append({
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "purpose": purpose,
        "provider": provider.info.key,
        "model": provider.info.model,
        "external": provider.info.external,
        "input_sha256": hashlib.sha256(input_bytes).hexdigest() if input_bytes else None,
        "ok": ok,
        "detail": detail[:300],
        "actor": actor,
    })
    store.write_artifact(case_id, AI_LOG, json.dumps(entries, indent=2, ensure_ascii=False))


__all__ = [
    "AIError", "AnthropicProvider", "ExtractionResult", "FIELDS", "RulesProvider",
    "check_figures", "explain", "get_provider", "log_ai_use", "parse_confirmed",
    "template_explanation", "to_statements", "violates_guardrails",
]
