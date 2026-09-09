"""
Tests for the primitive-picture mechanism (owner request, 2026-09-09).

Some primitives Heisig teaches only exist at codepoints most fonts can't draw —
𭕄 (owl crown, CJK Ext G), 𢦏 (harvest festival, Ext B), 㑒 (Ext A). Substituting
a well-supported lookalike is the mistake this project has undone most often, so
the codepoint stays right and make_primitive_images.py renders a PNG that
attach_primitive_images() points the row at.
"""
import database
from make_primitive_images import needs_image


def _seed(conn, kid, character, owner_id=1):
    conn.execute(
        "INSERT INTO kanji (id, character, keyword, owner_id, visibility, script) "
        "VALUES (?, ?, ?, ?, 'public', 'ja-kanji')",
        (kid, character, "some-keyword", owner_id)
    )


def test_attach_points_system_rows_at_their_committed_picture(conn, tmp_path, monkeypatch):
    monkeypatch.setattr(database, "PRIMITIVE_IMAGE_DIR", tmp_path)
    (tmp_path / "prim-owl.png").write_bytes(b"\x89PNG fake")
    _seed(conn, "prim-owl", "\U0002D544")
    _seed(conn, "prim-no-picture", "\U0002298F")
    conn.commit()

    assert database.attach_primitive_images(conn, commit=True) == 1
    urls = dict(conn.execute("SELECT id, image_url FROM kanji"))
    assert urls["prim-owl"] == "/primitive-images/prim-owl.png"
    assert urls["prim-no-picture"] is None, "only ids with a file on disk get a URL"


def test_attach_is_idempotent_and_never_touches_user_rows(conn, tmp_path, monkeypatch):
    """Re-running must be a no-op, and a user's own kanji that happens to share an id
    shape with a picture file must keep whatever image it already had -- system rows
    are the only ones this manages (set_kanji_image's owner_id != 1 guard is the
    other half of that boundary)."""
    monkeypatch.setattr(database, "PRIMITIVE_IMAGE_DIR", tmp_path)
    (tmp_path / "prim-owl.png").write_bytes(b"\x89PNG fake")
    (tmp_path / "usr9.png").write_bytes(b"\x89PNG fake")
    _seed(conn, "prim-owl", "\U0002D544")
    _seed(conn, "usr9", None, owner_id=2)
    conn.execute("UPDATE kanji SET image_url = '/uploads/usr9.gif' WHERE id = 'usr9'")
    conn.commit()

    database.attach_primitive_images(conn, commit=True)
    assert database.attach_primitive_images(conn, commit=True) == 0, "second run changes nothing"
    urls = dict(conn.execute("SELECT id, image_url FROM kanji"))
    assert urls["usr9"] == "/uploads/usr9.gif", "a user's own upload must not be rewritten"


def test_needs_image_covers_the_unrenderable_blocks_only():
    """The selection rule itself: a picture for a glyph a reader can already see is a
    needless request and a second thing to keep in sync."""
    assert needs_image("\U0002D544"), "𭕄 is CJK Ext G -- effectively no font has it"
    assert needs_image("\U0002298F"), "𢦏 is CJK Ext B"
    assert needs_image("㑒"), "㑒 is CJK Ext A -- patchy, notably on Android"
    assert not needs_image("口"), "口 is in the base CJK block"
    assert not needs_image("忄"), "忄 is a common radical"
    assert not needs_image(None) and not needs_image("")


def test_picture_reaches_the_part_chips_of_a_host(conn, client, tmp_path, monkeypatch):
    """The end-to-end path that matters: a host kanji's decomposition returns the
    picture alongside the part, so the chip can render it instead of an empty box."""
    monkeypatch.setattr(database, "PRIMITIVE_IMAGE_DIR", tmp_path)
    (tmp_path / "prim-owl.png").write_bytes(b"\x89PNG fake")
    _seed(conn, "prim-owl", "\U0002D544")
    _seed(conn, "k_host", "学")
    conn.execute("INSERT INTO aliases (kanji_id, alias, owner_id, visibility) "
                 "VALUES ('prim-owl', 'owl crown', 1, 'public')")
    cur = conn.execute("INSERT INTO decompositions (kanji_id, owner_id, visibility) "
                       "VALUES ('k_host', 1, 'public')")
    conn.execute("INSERT INTO parts (kanji_id, part_term, position, decomposition_id) "
                 "VALUES ('k_host', 'owl crown', 0, ?)", (cur.lastrowid,))
    database.attach_primitive_images(conn, commit=True)

    r = client.get("/kanji/k_host")
    assert r.status_code == 200, r.text
    parts = r.json()["decompositions"][0]["parts_detail"]
    assert [p["image_url"] for p in parts] == ["/primitive-images/prim-owl.png"]
