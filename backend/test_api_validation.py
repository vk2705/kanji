"""
Isolated tests for the request-validation-limit fixes (architecture review finding
#4). See conftest.py for the temp-DB/TestClient fixtures.
"""
from conftest import register_user


def test_overlong_ascii_password_rejected_cleanly(client):
    """Previously reached bcrypt.hashpw() unhandled and raised ValueError -> 500;
    Credentials.password's Field(max_length=72) now catches this at the Pydantic
    validation layer (422), before the handler body even runs."""
    r = client.post("/auth/register", json={"username": "toolongpw", "password": "a" * 100})
    assert r.status_code == 422, r.text
    assert r.status_code != 500


def test_overlong_multibyte_password_rejected_cleanly(client):
    """72 emoji is 72 *characters* (passes a naive character-count check) but 288
    UTF-8 *bytes* (over bcrypt's real 72-byte limit) -- register()'s explicit
    len(password.encode()) check catches what Field(max_length=72) alone can't."""
    r = client.post("/auth/register", json={"username": "emojipw", "password": "😀" * 72})
    assert r.status_code == 400, r.text
    assert r.status_code != 500


def test_password_at_exactly_72_bytes_still_works(client):
    """Sanity check the fix isn't off-by-one -- exactly 72 ASCII bytes must still
    register successfully."""
    r = client.post("/auth/register", json={"username": "exactlyseventytwo", "password": "a" * 72})
    assert r.status_code == 200, r.text


def test_overlong_username_rejected(client):
    r = client.post("/auth/register", json={"username": "x" * 500, "password": "testpass123"})
    assert r.status_code == 422, r.text


def test_overlong_story_rejected(client):
    register_user(client, "storywriter")
    r = client.post("/kanji", json={"keyword": "story-limit-test", "character": "?", "visibility": "public"})
    kid = r.json()["id"]
    r = client.post("/stories", json={"kanji_id": kid, "story": "x" * 30_000})
    assert r.status_code == 422, r.text


def test_overlong_alias_rejected(client):
    register_user(client, "aliaswriter")
    r = client.post("/kanji", json={"keyword": "alias-limit-test", "character": "?", "visibility": "public"})
    kid = r.json()["id"]
    r = client.post("/aliases", json={"kanji_id": kid, "alias": "x" * 500})
    assert r.status_code == 422, r.text


def test_too_many_decomposition_parts_rejected(client):
    register_user(client, "partswriter")
    r = client.post("/kanji", json={"keyword": "parts-limit-test", "character": "?", "visibility": "public"})
    kid = r.json()["id"]
    r = client.post(f"/kanji/{kid}/decompositions", json={"parts": [f"part{i}" for i in range(100)]})
    assert r.status_code == 422, r.text


def test_overlong_single_part_rejected(client):
    register_user(client, "onepartwriter")
    r = client.post("/kanji", json={"keyword": "onepart-limit-test", "character": "?", "visibility": "public"})
    kid = r.json()["id"]
    r = client.post(f"/kanji/{kid}/decompositions", json={"parts": ["x" * 500]})
    assert r.status_code == 422, r.text


def test_analytics_pageview_path_bounded(client):
    """POST /analytics/pageview needs no auth (analytics.py) -- its `path` field is
    the one attacker-controlled field written to page_views on every call, so it's
    bounded to stop it being used to stuff arbitrarily large strings into the DB."""
    r = client.post("/analytics/pageview", json={"path": "/kanji/rtk1"})
    assert r.status_code == 200, r.text

    r = client.post("/analytics/pageview", json={"path": "/" + "x" * 10_000})
    assert r.status_code == 422, r.text


def test_ordinary_length_inputs_still_work(client):
    """Sanity check the new limits don't reject realistic, normal-sized input."""
    register_user(client, "normaluser")
    r = client.post("/kanji", json={
        "keyword": "a perfectly normal keyword",
        "character": "明",
        "visibility": "public",
    })
    assert r.status_code == 200, r.text
    kid = r.json()["id"]

    r = client.post("/stories", json={
        "kanji_id": kid,
        "story": "A reasonably long mnemonic story, a few sentences of normal prose "
                 "about how this kanji's parts combine to form its meaning.",
    })
    assert r.status_code == 200, r.text

    r = client.post("/aliases", json={"kanji_id": kid, "alias": "a normal alias"})
    assert r.status_code == 200, r.text

    r = client.post(f"/kanji/{kid}/decompositions", json={"parts": ["sun", "moon", "tree"]})
    assert r.status_code == 200, r.text
