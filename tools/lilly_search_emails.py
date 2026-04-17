#!/usr/bin/env python3
"""lilly_search_emails — hybrid search over Ryan's email archive.

Thin wrapper around `scripts/email_search.py search` in the homegrown_lilly
repo. Queries a local SQLite+FTS5+embeddings cache (populated by
email_sync.py), so retrieval works offline and supports semantic matching
for paraphrase-heavy queries that keyword-only search would miss.

Earlier implementation wrapped `mu_search.py` (keyword-only via the mu
binary, now retired). The current implementation hits lilly's own cache
so the muse can call the tool in all three modes (lexical / semantic /
hybrid) through the same entry point, with no dependency on an external
indexer.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

from tools.registry import registry, tool_error


LILLY_DIR = Path(os.environ.get("LILLY_DIR", "/home/ryan/homegrown_lilly"))
LILLY_PY = str(LILLY_DIR / ".venv" / "bin" / "python")
SEARCH_SCRIPT = str(LILLY_DIR / "scripts" / "email_search.py")


SEARCH_EMAILS_SCHEMA = {
    "name": "lilly_search_emails",
    "description": (
        "Search Ryan's email archive (local SQLite+FTS5+embeddings) for "
        "messages matching a query. Use this for source-of-truth retrieval "
        "of anything email-mediated: job application status, decisions, "
        "conversations with a specific person, interview scheduling. More "
        "reliable than the extracted fact graph for recent or outbound "
        "messages.\n\n"
        "Three search modes (default 'hybrid'):\n"
        "  - 'hybrid' — RRF fusion of lexical FTS5 + semantic embeddings; "
        "best general-purpose\n"
        "  - 'semantic' — embedding-only, for paraphrase queries "
        "(\"Ryan turning down offers\" matches \"decided to pass\")\n"
        "  - 'lexical' — FTS5 only, exact-term queries, supports "
        "since_days and from_filter\n\n"
        "Lexical / hybrid query syntax (FTS5):\n"
        "  - Keywords: \"akasa interview\"\n"
        "  - Phrase: '\"decided to pass\"'\n"
        "  - Boolean: \"harry OR sarah\"\n"
        "  - Column-scoped: \"subject: interview from: akasa\"\n\n"
        "Semantic mode takes natural language — no special syntax."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Query string."},
            "mode": {
                "type": "string",
                "enum": ["lexical", "semantic", "hybrid"],
                "description": "Search mode (default hybrid).",
                "default": "hybrid",
            },
            "limit": {
                "type": "integer",
                "description": "Max results (default 10, capped at 50).",
                "default": 10,
            },
            "since_days": {
                "type": "integer",
                "description": "Lexical mode only: restrict to last N days.",
            },
            "from_filter": {
                "type": "string",
                "description": (
                    "Lexical mode only: substring match on sender "
                    "(e.g. 'akasa.com', 'harry')."
                ),
            },
        },
        "required": ["query"],
    },
}


def lilly_search_emails(
    query: str,
    mode: str = "hybrid",
    limit: int = 10,
    since_days: int | None = None,
    from_filter: str | None = None,
    task_id=None,
) -> str:
    if not query or not query.strip():
        return tool_error("query is required")
    if mode not in ("lexical", "semantic", "hybrid"):
        mode = "hybrid"
    try:
        limit = max(1, min(int(limit), 50))
    except (TypeError, ValueError):
        limit = 10

    cmd = [LILLY_PY, SEARCH_SCRIPT, "search", query,
           "--limit", str(limit), "--mode", mode]
    if mode == "lexical":
        if since_days:
            cmd.extend(["--since-days", str(int(since_days))])
        if from_filter:
            cmd.extend(["--from", from_filter])

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return tool_error("email search timed out after 30s")
    except FileNotFoundError:
        return tool_error(f"email_search.py not available at {SEARCH_SCRIPT}")

    if r.returncode != 0:
        return tool_error(
            f"email search failed (exit {r.returncode}): {r.stderr.strip()[:400]}"
        )

    raw = r.stdout.strip()
    if not raw:
        return json.dumps({"query": query, "mode": mode, "count": 0, "results": []})

    try:
        json.loads(raw)  # validate
    except json.JSONDecodeError:
        return json.dumps(
            {"query": query, "raw_stdout": raw[:4000], "warning": "non-JSON output"}
        )
    return raw


def check_lilly_search_emails_requirements() -> bool:
    return Path(SEARCH_SCRIPT).exists() and Path(LILLY_PY).exists()


registry.register(
    name="lilly_search_emails",
    toolset="lilly",
    schema=SEARCH_EMAILS_SCHEMA,
    handler=lambda args, **kw: lilly_search_emails(
        query=args.get("query", ""),
        mode=args.get("mode", "hybrid"),
        limit=args.get("limit", 10),
        since_days=args.get("since_days"),
        from_filter=args.get("from_filter"),
        task_id=kw.get("task_id"),
    ),
    check_fn=check_lilly_search_emails_requirements,
    emoji="📧",
)
