"""
Isolated tests for contribution-endpoint ownership rules (architecture review
finding #3's second-highest priority item) and auth requirements. See conftest.py
for the temp-DB/TestClient fixtures.
"""
from conftest import register_user


def test_write_endpoints_require_auth(client):
    """Every contribution write endpoint 401s for a logged-out caller."""
    r = client.post("/kanji", json={"keyword": "x"})
    assert r.status_code == 401, r.text

    r = client.post("/aliases", json={"kanji_id": "rtk1", "alias": "x"})
    assert r.status_code == 401, r.text

    r = client.post("/stories", json={"kanji_id": "rtk1", "story": "x"})
    assert r.status_code == 401, r.text

    r = client.post("/kanji/rtk1/decompositions", json={"parts": ["a"]})
    assert r.status_code == 401, r.text

    r = client.patch("/kanji/rtk1/visibility", json={"visibility": "public"})
    assert r.status_code == 401, r.text

    r = client.get("/me/contributions")
    assert r.status_code == 401, r.text


def test_cannot_toggle_visibility_of_someone_elses_row(client):
    """A user can't PATCH visibility on a kanji/alias/decomposition/story they
    don't own, even one that's public (public just means readable, not writable
    by anyone)."""
    register_user(client, "owner3")
    r = client.post("/kanji", json={"keyword": "shared-word", "character": "共", "visibility": "public"})
    kid = r.json()["id"]

    client.cookies.clear()
    register_user(client, "meddler")
    r = client.patch(f"/kanji/{kid}/visibility", json={"visibility": "private"})
    assert r.status_code == 403, r.text

    # And the kanji is still public afterward -- the rejected PATCH had no effect.
    r = client.get(f"/kanji/{kid}")
    assert r.status_code == 200, r.text


def test_system_rows_are_immutable(conn, client):
    """owner_id=1 (system) rows can never have their visibility toggled by anyone,
    matching set_visibility()'s owner_id != 1 guard (CLAUDE.md: "set_visibility()
    doubles as the 'system rows are immutable' guard")."""
    conn.execute(
        "INSERT OR IGNORE INTO users (id, username, auth_provider, display_name) "
        "VALUES (1, 'system', 'system', 'Heisig / System')"
    )
    conn.execute(
        "INSERT INTO kanji (id, character, keyword, owner_id, visibility, script) "
        "VALUES ('rtk1', '一', 'one', 1, 'public', 'ja-kanji')"
    )
    conn.commit()

    register_user(client, "regular_user")
    r = client.patch("/kanji/rtk1/visibility", json={"visibility": "private"})
    assert r.status_code == 403, r.text


def test_visibility_toggle_round_trip(client):
    """A user CAN toggle visibility on their own row, in both directions."""
    register_user(client, "toggler")
    r = client.post("/kanji", json={"keyword": "toggle-word", "character": "?", "visibility": "private"})
    kid = r.json()["id"]

    r = client.patch(f"/kanji/{kid}/visibility", json={"visibility": "public"})
    assert r.status_code == 200, r.text

    client.cookies.clear()
    register_user(client, "reader")
    r = client.get(f"/kanji/{kid}")
    assert r.status_code == 200, r.text  # now public, visible to anyone

    client.cookies.clear()
    r = client.post("/auth/login", json={"username": "toggler", "password": "testpass123"})
    assert r.status_code == 200, r.text
    r = client.patch(f"/kanji/{kid}/visibility", json={"visibility": "private"})
    assert r.status_code == 200, r.text


def test_duplicate_username_rejected(client):
    register_user(client, "dupe_user")
    client.cookies.clear()
    r = client.post("/auth/register", json={"username": "dupe_user", "password": "testpass123"})
    assert r.status_code == 409, r.text


def test_duplicate_alias_from_different_owners_is_allowed(client):
    """The schema's UNIQUE(kanji_id, alias, owner_id) (added in _migrate_v1,
    specifically to relax the old UNIQUE(kanji_id, alias)) means two different
    users can each attach the same alias text to the same kanji."""
    register_user(client, "aliaser_a")
    r = client.post("/kanji", json={"keyword": "shared-target", "character": "共", "visibility": "public"})
    kid = r.json()["id"]
    r = client.post("/aliases", json={"kanji_id": kid, "alias": "same-name", "visibility": "public"})
    assert r.status_code == 200, r.text

    client.cookies.clear()
    register_user(client, "aliaser_b")
    r = client.post("/aliases", json={"kanji_id": kid, "alias": "same-name", "visibility": "public"})
    assert r.status_code == 200, r.text


def test_story_upsert_replaces_not_duplicates(client):
    """One editable story per (kanji, owner) -- resubmitting updates it in place
    rather than creating a second row (database.py's upsert_story docstring)."""
    register_user(client, "storyteller")
    r = client.post("/kanji", json={"keyword": "story-word", "character": "?", "visibility": "public"})
    kid = r.json()["id"]

    r = client.post("/stories", json={"kanji_id": kid, "story": "first version"})
    assert r.status_code == 200, r.text
    first_id = r.json()["id"]

    r = client.post("/stories", json={"kanji_id": kid, "story": "revised version"})
    assert r.status_code == 200, r.text
    assert r.json()["id"] == first_id, "resubmitting a story should update the same row, not create a new one"

    r = client.get("/me/contributions")
    stories = [s for s in r.json()["stories"] if s["kanji_id"] == kid]
    assert len(stories) == 1
    assert stories[0]["story"] == "revised version"


def test_add_kanji_creates_findable_alias(client):
    """Regression coverage for the create_kanji_entry fix (2026-08-27ish session):
    a newly created kanji must be findable by its own keyword via text search, not
    just by its generated id -- the bug was that no aliases row was ever inserted
    for a fresh kanji's own keyword."""
    register_user(client, "creator")
    r = client.post("/kanji", json={"keyword": "findable-keyword", "character": "?", "visibility": "public"})
    assert r.status_code == 200, r.text
    kid = r.json()["id"]

    r = client.get("/search/text", params={"q": "findable-keyword"})
    assert r.status_code == 200, r.text
    ids_found = {row["id"] for row in r.json()["results"]}
    assert kid in ids_found
