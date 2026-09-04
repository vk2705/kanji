"""
Isolated tests for search/parts's depth, source, and script filters (architecture
review finding #3's explicit ask). Fixture kanji are seeded directly via the `conn`
fixture rather than through the create-kanji API, since these tests need precise
multi-level decomposition trees and specific owner/visibility/script combinations
that would be slow and noisy to build one HTTP call at a time.
"""
from conftest import register_user


def _seed_kanji(conn, kid, character, keyword, owner_id=1, visibility="public", script="ja-kanji"):
    conn.execute(
        "INSERT INTO kanji (id, character, keyword, owner_id, visibility, script) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (kid, character, keyword, owner_id, visibility, script)
    )


def _seed_decomposition(conn, kid, owner_id, parts, visibility="public"):
    cur = conn.execute(
        "INSERT INTO decompositions (kanji_id, owner_id, visibility) VALUES (?, ?, ?)",
        (kid, owner_id, visibility)
    )
    decomp_id = cur.lastrowid
    conn.executemany(
        "INSERT INTO parts (kanji_id, part_term, position, decomposition_id) VALUES (?, ?, ?, ?)",
        [(kid, term, i, decomp_id) for i, term in enumerate(parts)]
    )


def _seed_alias(conn, kid, alias, owner_id=1, visibility="public"):
    conn.execute(
        "INSERT INTO aliases (kanji_id, alias, owner_id, visibility) VALUES (?, ?, ?, ?)",
        (kid, alias, owner_id, visibility)
    )


def test_depth_1_is_direct_match_only(conn, client):
    """At depth=1 (the default), a term must appear literally in the kanji's own
    decomposition -- a grandparent relationship (A contains B, B contains C) does
    NOT make A match a search for C."""
    _seed_kanji(conn, "k_a", "A", "kanji-a")
    _seed_kanji(conn, "k_b", "B", "kanji-b")
    _seed_kanji(conn, "k_c", "C", "kanji-c")
    _seed_decomposition(conn, "k_a", 1, ["kanji-b"])
    _seed_decomposition(conn, "k_b", 1, ["kanji-c"])
    _seed_alias(conn, "k_a", "kanji-a")
    _seed_alias(conn, "k_b", "kanji-b")
    _seed_alias(conn, "k_c", "kanji-c")
    conn.commit()

    r = client.post("/search/parts", json={"parts": ["kanji-c"], "depth": 1})
    assert r.status_code == 200, r.text
    ids = {row["id"] for row in r.json()["results"]}
    # k_c matches by self-identity, k_b matches because its own decomposition
    # literally lists "kanji-c" -- both are depth=1 (direct) matches. k_a must NOT
    # match: its own decomposition only lists "kanji-b", reaching "kanji-c" would
    # require walking two levels deep (k_a -> k_b -> kanji-c), past depth=1.
    assert ids == {"k_b", "k_c"}, f"depth=1 should match k_b (direct) and k_c (self-identity), not k_a; got {ids}"


def test_depth_3_reaches_grandparents(conn, client):
    """At depth=3, the same fixture's search for the grandchild term also finds the
    grandparent (search_by_parts's documented depth>1 recursive-reachability
    behavior)."""
    _seed_kanji(conn, "k_a", "A", "kanji-a")
    _seed_kanji(conn, "k_b", "B", "kanji-b")
    _seed_kanji(conn, "k_c", "C", "kanji-c")
    _seed_decomposition(conn, "k_a", 1, ["kanji-b"])
    _seed_decomposition(conn, "k_b", 1, ["kanji-c"])
    _seed_alias(conn, "k_a", "kanji-a")
    _seed_alias(conn, "k_b", "kanji-b")
    _seed_alias(conn, "k_c", "kanji-c")
    conn.commit()

    r = client.post("/search/parts", json={"parts": ["kanji-c"], "depth": 3})
    assert r.status_code == 200, r.text
    ids = {row["id"] for row in r.json()["results"]}
    assert ids == {"k_a", "k_b", "k_c"}, f"depth=3 should reach all three ancestors, got {ids}"


def test_depth_out_of_range_rejected(client):
    r = client.post("/search/parts", json={"parts": ["x"], "depth": 0})
    assert r.status_code == 400, r.text

    r = client.post("/search/parts", json={"parts": ["x"], "depth": 999})
    assert r.status_code == 400, r.text


def test_self_identity_match_independent_of_depth(conn, client):
    """A kanji with no decomposition at all still matches a search for its own
    keyword/alias -- "self-identity" (CLAUDE.md: 'a kanji "is made of" itself')."""
    _seed_kanji(conn, "k_atomic", "囗", "box-shape")
    _seed_alias(conn, "k_atomic", "box-shape")
    conn.commit()

    r = client.post("/search/parts", json={"parts": ["box-shape"], "depth": 1})
    assert r.status_code == 200, r.text
    ids = {row["id"] for row in r.json()["results"]}
    assert "k_atomic" in ids


def test_script_filter_excludes_other_scripts(conn, client):
    """script='ja-kanji' excludes zh-Hans/zh-Hant rows even if they'd otherwise match."""
    _seed_kanji(conn, "k_ja", "日", "sun-ja", script="ja-kanji")
    _seed_kanji(conn, "k_zh", "日", "sun-zh", script="zh-Hans")
    _seed_alias(conn, "k_ja", "sun-shared")
    _seed_alias(conn, "k_zh", "sun-shared")
    conn.commit()

    r = client.post("/search/parts", json={"parts": ["sun-shared"], "script": "ja-kanji", "depth": 1})
    assert r.status_code == 200, r.text
    ids = {row["id"] for row in r.json()["results"]}
    assert ids == {"k_ja"}, f"script=ja-kanji should exclude k_zh, got {ids}"


def test_invalid_script_rejected(client):
    r = client.post("/search/parts", json={"parts": ["x"], "script": "not-a-real-script"})
    assert r.status_code == 400, r.text


def test_source_filter_restricts_which_decomposition_is_consulted(conn, client):
    """sources restricts BOTH which kanji can be returned AND which decompositions
    are consulted for matching (CLAUDE.md's search_by_parts docs) -- both filters key
    off the same source set, so isolating "decomposition provenance" independent of
    "kanji provenance" needs a kanji whose OWN eligibility doesn't change across the
    scopes compared: a system-owned kanji stays eligible under both sources=['system']
    and sources=None (all), so any difference in what matches between those two must
    come from which decomposition got consulted, not which kanji rows qualified."""
    conn.execute(
        "INSERT OR IGNORE INTO users (id, username, auth_provider) VALUES (777, 'community_contributor', 'local')"
    )
    _seed_kanji(conn, "k_x", "X", "kanji-x", owner_id=1, visibility="public")  # system-owned
    _seed_decomposition(conn, "k_x", 1, ["system-term"], visibility="public")
    _seed_decomposition(conn, "k_x", 777, ["community-term"], visibility="public")
    conn.commit()

    # No source restriction: both decompositions are consulted.
    r = client.post("/search/parts", json={"parts": ["system-term"], "depth": 1})
    assert "k_x" in {row["id"] for row in r.json()["results"]}
    r = client.post("/search/parts", json={"parts": ["community-term"], "depth": 1})
    assert "k_x" in {row["id"] for row in r.json()["results"]}

    # sources=['system']: the kanji itself is still eligible (it's system-owned), but
    # the community decomposition's term must no longer match it -- only that
    # decomposition's provenance changed what's being consulted, not the kanji's.
    r = client.post("/search/parts", json={"parts": ["system-term"], "sources": ["system"], "depth": 1})
    assert r.status_code == 200, r.text
    assert "k_x" in {row["id"] for row in r.json()["results"]}

    r = client.post("/search/parts", json={"parts": ["community-term"], "sources": ["system"], "depth": 1})
    assert r.status_code == 200, r.text
    assert "k_x" not in {row["id"] for row in r.json()["results"]}, (
        "sources=['system'] must not consult a community-owned decomposition, "
        "even on an otherwise-eligible system-owned kanji"
    )


def test_text_search_is_whole_word_only(conn, client):
    """search_by_substring's LIKE '% q %' whole-word pattern (CLAUDE.md): "hat" matches
    "bamboo hat" but not "hatchet" or "what"."""
    _seed_kanji(conn, "k_hat", "帽", "bamboo hat")
    _seed_kanji(conn, "k_hatchet", "斧", "hatchet")
    _seed_kanji(conn, "k_what", "何", "what")
    conn.commit()

    r = client.get("/search/text", params={"q": "hat"})
    assert r.status_code == 200, r.text
    ids = {row["id"] for row in r.json()["results"]}
    assert ids == {"k_hat"}, f"expected only the whole-word 'hat' match, got {ids}"


def test_private_decomposition_only_visible_to_its_owner_in_search(conn, client):
    """A private decomposition's part terms don't leak into parts-search results for
    other viewers, matching the visibility model described in CLAUDE.md."""
    _seed_kanji(conn, "k_priv", "秘", "private-target", owner_id=1, visibility="public")
    conn.commit()  # release the write lock before the API call below opens its own connection
    register_user(client, "privater")
    owner_row = conn.execute("SELECT id FROM users WHERE username = 'privater'").fetchone()
    owner_id = owner_row["id"]
    _seed_decomposition(conn, "k_priv", owner_id, ["only-i-can-see-this"], visibility="private")
    conn.commit()

    # Owner sees it via their own session.
    r = client.post("/search/parts", json={"parts": ["only-i-can-see-this"], "depth": 1})
    assert r.status_code == 200, r.text
    assert "k_priv" in {row["id"] for row in r.json()["results"]}

    # A different user does not.
    client.cookies.clear()
    register_user(client, "outsider3")
    r = client.post("/search/parts", json={"parts": ["only-i-can-see-this"], "depth": 1})
    assert r.status_code == 200, r.text
    assert "k_priv" not in {row["id"] for row in r.json()["results"]}

    # Nor does an anonymous caller.
    client.cookies.clear()
    r = client.post("/search/parts", json={"parts": ["only-i-can-see-this"], "depth": 1})
    assert r.status_code == 200, r.text
    assert "k_priv" not in {row["id"] for row in r.json()["results"]}


def test_suggest_matches_substring_anywhere_not_just_whole_word(conn, client):
    """/search/suggest is for autocomplete mid-keystroke, so unlike search_by_substring
    (whole-word, for final search precision) it must match a query appearing anywhere
    inside a name -- a user typing "ate" hasn't necessarily reached a word boundary."""
    _seed_kanji(conn, "k_gate", "門", "gatehouse")
    conn.commit()
    r = client.get("/search/suggest", params={"q": "ate"})
    assert r.status_code == 200, r.text
    assert "gatehouse" in r.json()["suggestions"]


def test_suggest_splits_comma_separated_synonym_lists(conn, client):
    """A keyword/alias can itself be a comma-separated synonym list (e.g. "one,
    floor, ceiling, minus") -- suggestions must be the individual names, not the
    whole joined string."""
    _seed_kanji(conn, "k_syn", "多", "many, plentiful, abundant")
    conn.commit()
    r = client.get("/search/suggest", params={"q": "plent"})
    assert r.status_code == 200, r.text
    assert r.json()["suggestions"] == ["plentiful"]


def test_suggest_prefix_matches_rank_before_mid_word_matches(conn, client):
    _seed_kanji(conn, "k_ate1", "亜", "plate")
    _seed_kanji(conn, "k_ate2", "亙", "ateam")
    conn.commit()
    r = client.get("/search/suggest", params={"q": "ate"})
    assert r.status_code == 200, r.text
    suggestions = r.json()["suggestions"]
    assert suggestions.index("ateam") < suggestions.index("plate")


def test_suggest_excludes_private_terms(conn, client):
    """Suggestions only ever come from the shared public vocabulary -- a private
    term one user invented isn't a useful (or visible) suggestion for anyone else
    typing into the same bounded input."""
    _seed_kanji(conn, "k_hidden", "隠", "hiddenword", visibility="private")
    conn.commit()
    r = client.get("/search/suggest", params={"q": "hidden"})
    assert r.status_code == 200, r.text
    assert "hiddenword" not in r.json()["suggestions"]


def test_suggest_requires_nonempty_query(conn, client):
    r = client.get("/search/suggest", params={"q": ""})
    assert r.status_code == 422
