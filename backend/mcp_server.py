"""
mcp_server.py — public, read-only MCP server exposing this project's kanji/hanzi
shape-search and decomposition lookup as MCP tools, for kanjimcp.alteon.help.

Runs as its OWN process/systemd unit (kanji-mcp.service), separate from the main
API (kanji-backend.service) — see DEPLOY_README.md's MCP section. It imports
database.py directly and opens its own short-lived read connections via
database.get_db(); it never writes, and every call passes viewer_id=None, so it
can only ever see public rows — same visibility a logged-out website visitor gets
(see CLAUDE.md's Visibility model). No auth: this mirrors the site's own public
search/detail endpoints, just as an MCP tool surface instead of HTTP+JSON.

Run directly for local testing (defaults to 127.0.0.1:8100):
    ./venv/bin/python3 mcp_server.py
"""
import os

import database

from mcp.server.mcpserver import MCPServer

mcp = MCPServer(
    name="kanji",
    title="Kanji & Hanzi Decomposition",
    instructions=(
        "Look up Japanese kanji / Chinese hanzi by shape. search_by_parts finds "
        "characters built from a given set of named components (e.g. ['sun', "
        "'moon'] -> 明); get_decomposition returns a character's own breakdown "
        "into components, recursively. Component names are English keywords, "
        "not readings — this is a shape/structure search, not a dictionary."
    ),
)


def _kanji_summary(row: dict) -> dict:
    return {
        "id": row["id"],
        "character": row["character"],
        "keyword": row["keyword"],
        "frame": row.get("frame"),
        "stroke_count": row.get("stroke_count"),
    }


@mcp.tool()
def search_by_parts(
    parts: list[str],
    script: str | None = None,
    depth: int = 1,
) -> list[dict]:
    """Find kanji/hanzi built from ALL of the given component names (e.g.
    ["sun", "moon"] -> 明/bright). A component name is an English keyword or
    alias of a primitive or a taught kanji, not a reading.

    parts: component names to search for, ALL of which must be present.
    script: optional study-language filter — one of "ja-kanji", "zh-Hans",
        "zh-Hant". Omit to search across all scripts.
    depth: how many decomposition levels to recurse through when checking
        whether a component is "present" (1-5, default 1 = the component must
        appear directly in the character's own decomposition). Higher depth
        also matches components nested inside components; results grow fast
        with depth for common components like "mouth".

    Returns up to 200 matches, each {id, character, keyword, frame, stroke_count}.
    """
    if script is not None and script not in database.SCRIPT_VISIBILITY:
        raise ValueError(f"script must be one of {sorted(database.SCRIPT_VISIBILITY)}, got {script!r}")
    conn = database.get_db()
    try:
        results = database.search_by_parts(conn, parts, viewer_id=None, script=script, depth=depth)
        return [_kanji_summary(r) for r in results[:200]]
    finally:
        conn.close()


@mcp.tool()
def get_decomposition(kanji_or_id: str) -> dict:
    """Look up one kanji/hanzi by character glyph, id (e.g. "rtk145"), or exact
    keyword/alias, and return its full public decomposition: the character
    itself plus every publicly visible decomposition of it (a character can
    have more than one, e.g. a structural one alongside Heisig's own), each a
    list of component parts. Each part that itself has a further breakdown
    includes it under "sub_decompositions", recursively.

    Raises if no public kanji/hanzi matches kanji_or_id.
    """
    conn = database.get_db()
    try:
        detail = database.get_kanji_detail(conn, kanji_or_id, viewer_id=None)
        if detail is None:
            raise ValueError(f"no public kanji/hanzi found for {kanji_or_id!r}")
        return {
            "id": detail["id"],
            "character": detail["character"],
            "keyword": detail["keyword"],
            "script": detail["script"],
            "onyomi": detail.get("onyomi"),
            "kunyomi": detail.get("kunyomi"),
            "pinyin": detail.get("pinyin"),
            "decompositions": detail["decompositions"],
        }
    finally:
        conn.close()


@mcp.tool()
def search_by_text(query: str, script: str | None = None) -> list[dict]:
    """Find kanji/hanzi whose id, keyword, or any alias contains `query` as a
    whole word (e.g. "hat" matches "hat"/"bamboo hat" but not "hate"). This is
    a keyword/name search, the same as the website's text-search tab — use
    search_by_parts instead for shape-based lookup.

    script: optional study-language filter, one of "ja-kanji", "zh-Hans",
        "zh-Hant". Omit to search across all scripts.

    Returns up to 200 matches, each {id, character, keyword, frame, stroke_count}.
    """
    if script is not None and script not in database.SCRIPT_VISIBILITY:
        raise ValueError(f"script must be one of {sorted(database.SCRIPT_VISIBILITY)}, got {script!r}")
    conn = database.get_db()
    try:
        results = database.search_by_substring(conn, query, viewer_id=None, script=script)
        return [_kanji_summary(r) for r in results[:200]]
    finally:
        conn.close()


app = mcp.streamable_http_app(stateless_http=True)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("KANJI_MCP_PORT", "8100"))
    uvicorn.run(app, host="127.0.0.1", port=port)
