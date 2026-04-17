#!/usr/bin/env python3
"""lilly_search_limitless — search Ryan's local Limitless lifelog archive.

Thin wrapper over `scripts/limitless_search.py search` in the homegrown_lilly
repo. Queries a local SQLite+FTS5 cache of Limitless lifelogs (populated by
limitless_sync.py), so retrieval works offline and survives the inevitable
Limitless sunset post-Meta-acquisition.

Same rationale as lilly_search_emails: fact-extraction is lossy; the raw
transcript is source-of-truth for what Ryan actually said aloud.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

from tools.registry import registry, tool_error


LILLY_DIR = Path(os.environ.get("LILLY_DIR", "/home/ryan/homegrown_lilly"))
LILLY_PY = str(LILLY_DIR / ".venv" / "bin" / "python")
SEARCH_SCRIPT = str(LILLY_DIR / "scripts" / "limitless_search.py")


SEARCH_LIMITLESS_SCHEMA = {
    "name": "lilly_search_limitless",
    "description": (
        "Search Ryan's Limitless pendant recordings (local SQLite+FTS5 "
        "archive) for spoken content. Use this to confirm what Ryan or "
        "someone in his environment said aloud — family conversations, "
        "phone calls, meetings, verbal decisions. Returns matching lifelog "
        "snippets with timestamps and title. More reliable than the "
        "extracted fact graph for recent conversations or anything the "
        "fact-extractor may have dropped.\n\n"
        "Three search modes (default 'hybrid' gives the best quality):\n"
        "  - 'hybrid' — RRF fusion of lexical FTS5 + semantic embeddings\n"
        "  - 'semantic' — embedding-only, for paraphrase-heavy queries "
        "(\"Ryan turning down offers\" matches \"decided to pass\")\n"
        "  - 'lexical' — FTS5 only, for exact-term queries and when you "
        "need since_days / starred_only filters\n\n"
        "Lexical/hybrid query syntax (FTS5):\n"
        "  - Keywords: \"akasa interview\"\n"
        "  - Phrase: '\"decided to pass\"'\n"
        "  - Boolean: \"harry OR sarah\"\n"
        "  - Proximity: \"recruiter NEAR job\"\n\n"
        "Semantic mode uses natural language — no special syntax."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Query string.",
            },
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
                "description": (
                    "Lexical mode only: restrict to lifelogs from last N days."
                ),
            },
            "starred_only": {
                "type": "boolean",
                "description": "Lexical mode only: restrict to starred lifelogs.",
                "default": False,
            },
        },
        "required": ["query"],
    },
}


def lilly_search_limitless(
    query: str,
    mode: str = "hybrid",
    limit: int = 10,
    since_days: int | None = None,
    starred_only: bool = False,
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
    if since_days and mode == "lexical":
        cmd.extend(["--since-days", str(int(since_days))])
    if starred_only and mode == "lexical":
        cmd.append("--starred")

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    except subprocess.TimeoutExpired:
        return tool_error("limitless search timed out after 15s")
    except FileNotFoundError:
        return tool_error(f"limitless_search.py not available at {SEARCH_SCRIPT}")

    if r.returncode != 0:
        return tool_error(
            f"limitless search failed (exit {r.returncode}): {r.stderr.strip()[:400]}"
        )

    raw = r.stdout.strip()
    if not raw:
        return json.dumps({"query": query, "count": 0, "results": []})

    # limitless_search.py already emits a JSON object; pass it through unchanged.
    try:
        json.loads(raw)  # validate
    except json.JSONDecodeError:
        return json.dumps(
            {"query": query, "raw_stdout": raw[:4000], "warning": "non-JSON output"}
        )
    return raw


def check_lilly_search_limitless_requirements() -> bool:
    """Tool is available iff the search wrapper and its venv exist."""
    return Path(SEARCH_SCRIPT).exists() and Path(LILLY_PY).exists()


registry.register(
    name="lilly_search_limitless",
    toolset="lilly",
    schema=SEARCH_LIMITLESS_SCHEMA,
    handler=lambda args, **kw: lilly_search_limitless(
        query=args.get("query", ""),
        mode=args.get("mode", "hybrid"),
        limit=args.get("limit", 10),
        since_days=args.get("since_days"),
        starred_only=args.get("starred_only", False),
        task_id=kw.get("task_id"),
    ),
    check_fn=check_lilly_search_limitless_requirements,
    emoji="🎙️",
)
