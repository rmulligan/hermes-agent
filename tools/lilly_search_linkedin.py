#!/usr/bin/env python3
"""lilly_search_linkedin — hybrid search over Ryan's LinkedIn messages.

Same architecture as lilly_search_emails and lilly_search_limitless: queries
a local SQLite+FTS5+embeddings cache populated by linkedin_sync.py via the
Voyager API through CDP Chrome.
"""

import json
import os
import subprocess
from pathlib import Path

from tools.registry import registry, tool_error

LILLY_DIR = Path(os.environ.get("LILLY_DIR", "/home/ryan/homegrown_lilly"))
LILLY_PY = str(LILLY_DIR / ".venv" / "bin" / "python")
SEARCH_SCRIPT = str(LILLY_DIR / "scripts" / "linkedin_search.py")

SCHEMA = {
    "name": "lilly_search_linkedin",
    "description": (
        "Search Ryan's LinkedIn message archive (local cache with FTS5 + "
        "embeddings) for recruiter conversations, InMail threads, and "
        "networking exchanges. Use when you need to confirm what a "
        "recruiter said, check the status of a LinkedIn conversation, or "
        "find a specific person's messages.\n\n"
        "Three modes: 'hybrid' (default, RRF fusion), 'semantic' "
        "(paraphrase matching), 'lexical' (exact terms)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Query string."},
            "mode": {
                "type": "string",
                "enum": ["lexical", "semantic", "hybrid"],
                "default": "hybrid",
            },
            "limit": {"type": "integer", "default": 10},
            "since_days": {"type": "integer",
                           "description": "Lexical only: restrict to last N days."},
        },
        "required": ["query"],
    },
}


def lilly_search_linkedin(query="", mode="hybrid", limit=10,
                          since_days=None, task_id=None):
    if not query or not query.strip():
        return tool_error("query is required")
    limit = max(1, min(int(limit or 10), 50))
    cmd = [LILLY_PY, SEARCH_SCRIPT, "search", query,
           "--limit", str(limit), "--mode", mode or "hybrid"]
    if since_days and mode == "lexical":
        cmd.extend(["--since-days", str(int(since_days))])
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return tool_error("linkedin search timed out")
    except FileNotFoundError:
        return tool_error(f"linkedin_search.py not found at {SEARCH_SCRIPT}")
    if r.returncode != 0:
        return tool_error(f"exit {r.returncode}: {r.stderr[:400]}")
    return r.stdout.strip() or json.dumps({"query": query, "count": 0, "results": []})


def check_requirements():
    return Path(SEARCH_SCRIPT).exists() and Path(LILLY_PY).exists()


registry.register(
    name="lilly_search_linkedin",
    toolset="lilly",
    schema=SCHEMA,
    handler=lambda args, **kw: lilly_search_linkedin(
        query=args.get("query", ""),
        mode=args.get("mode", "hybrid"),
        limit=args.get("limit", 10),
        since_days=args.get("since_days"),
        task_id=kw.get("task_id"),
    ),
    check_fn=check_requirements,
    emoji="💼",
)
