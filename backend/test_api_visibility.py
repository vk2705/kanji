"""
Isolated visibility-boundary tests: private-entry visibility through aliases,
and anonymous/owner/unrelated-user read access — architecture review finding #3's
highest-priority item, and the exact bug class the resolve_alias() privacy leak
(fixed 2026-08-31) belongs to. See conftest.py for the temp-DB/TestClient fixtures.
"""
from conftest import register_user


def test_private_kanji_not_visible_to_others(client, conn):
    """A private kanji is invisible to everyone but its owner."""
    register_user(client, "owner")
    r = client.post("/kanji", json={"keyword": "secret-word", "character": "私", "visibility": "private"})
    assert r.status_code == 200, r.text
    kid = r.json()["id"]

    # Owner can see it.
    r = client.get(f"/kanji/{kid}")
    assert r.status_code == 200, r.text

    # A different logged-in user cannot.
    client.cookies.clear()
    register_user(client, "outsider")
    r = client.get(f"/kanji/{kid}")
    assert r.status_code == 404, r.text

    # Anonymous cannot either.
    client.cookies.clear()
    r = client.get(f"/kanji/{kid}")
    assert r.status_code == 404, r.text


def test_public_alias_on_private_kanji_does_not_leak_the_kanji(client):
    """Regression coverage (isolated, not just the live-DB check in
    test_regression_fixes.py) for the 2026-08-31 resolve_alias() privacy leak: an
    owner can make just an *alias* public while keeping the kanji itself private,
    and that alias must not let an unrelated user read or write to the kanji."""
    register_user(client, "owner")
    r = client.post("/kanji", json={"keyword": "leak-test-kanji", "character": "?", "visibility": "private"})
    assert r.status_code == 200, r.text
    kid = r.json()["id"]

    r = client.post("/aliases", json={"kanji_id": kid, "alias": "leak-test-alias", "visibility": "private"})
    assert r.status_code == 200, r.text

    # add_alias's response doesn't include the new alias row's id (only kanji_id +
    # the alias text) -- /me/contributions is the actual way a client discovers it
    # to PATCH its visibility.
    r = client.get("/me/contributions")
    assert r.status_code == 200, r.text
    alias_row = next(a for a in r.json()["aliases"] if a["alias"] == "leak-test-alias")

    r = client.patch(f"/aliases/{alias_row['id']}/visibility", json={"visibility": "public"})
    assert r.status_code == 200, r.text

    # Switch to an unrelated user, who only knows the *alias* (not the real id --
    # that's the whole point: an attacker who happened to see/guess the alias term
    # should never learn or use the real id it resolves to).
    client.cookies.clear()
    register_user(client, "attacker")

    # Detail lookup by the real id is correctly hidden...
    r = client.get(f"/kanji/{kid}")
    assert r.status_code == 404, r.text
    # ...and so is lookup by the public alias term itself (get_kanji_detail's own
    # extra visibility recheck on the resolved id catches this even if resolve_alias
    # itself leaked -- kept as a read-path sanity check, not the main assertion here).
    r = client.get("/kanji/leak-test-alias")
    assert r.status_code == 404, r.text

    # Text search should not surface the private kanji just because its alias is public.
    r = client.get("/search/text", params={"q": "leak-test-alias"})
    assert r.status_code == 200, r.text
    ids_found = {row["id"] for row in r.json()["results"]}
    assert kid not in ids_found, "private kanji leaked into text search via its public alias"

    # The write endpoints (add alias/decomposition/story) must all 404 when addressed
    # by the public alias term, not silently succeed against someone else's private
    # kanji -- this is the actual exploit path: contributions.py's _visible_kanji_id()
    # has no independent recheck the way get_kanji_detail does, so it depends entirely
    # on resolve_alias() itself refusing to resolve the alias for this viewer.
    r = client.post("/aliases", json={"kanji_id": "leak-test-alias", "alias": "attacker-alias", "visibility": "public"})
    assert r.status_code == 404, r.text

    r = client.post("/kanji/leak-test-alias/decompositions", json={"parts": ["one", "two"]})
    assert r.status_code == 404, r.text

    r = client.post("/stories", json={"kanji_id": "leak-test-alias", "story": "an attacker's story"})
    assert r.status_code == 404, r.text


def test_owner_private_alias_does_not_leak_to_others(client):
    """The inverse of the above: a *private* alias must not resolve for anyone but
    the owner either (sanity check that the fix didn't overcorrect into hiding
    legitimately-owned data from its own owner)."""
    register_user(client, "owner2")
    r = client.post("/kanji", json={"keyword": "priv-alias-kanji", "character": "?", "visibility": "private"})
    kid = r.json()["id"]
    r = client.post("/aliases", json={"kanji_id": kid, "alias": "priv-only-alias", "visibility": "private"})
    assert r.status_code == 200, r.text

    # Owner can still resolve their own kanji by its own alias.
    r = client.get(f"/kanji/{kid}")
    assert r.status_code == 200, r.text

    client.cookies.clear()
    register_user(client, "outsider2")
    r = client.get("/search/text", params={"q": "priv-only-alias"})
    assert r.status_code == 200, r.text
    assert kid not in {row["id"] for row in r.json()["results"]}


def test_public_kanji_visible_to_anonymous(client):
    """Sanity check: making this stricter didn't break the ordinary public case."""
    register_user(client, "publisher")
    r = client.post("/kanji", json={"keyword": "public-word", "character": "公", "visibility": "public"})
    assert r.status_code == 200, r.text
    kid = r.json()["id"]

    client.cookies.clear()
    r = client.get(f"/kanji/{kid}")
    assert r.status_code == 200, r.text
    assert r.json()["character"] == "公"
