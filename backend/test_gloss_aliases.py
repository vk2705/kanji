import database


def test_insert_gloss_aliases_preserves_phrase_and_adds_each_term(conn):
    conn.execute(
        "INSERT INTO kanji (id, character, keyword, owner_id, visibility, script) "
        "VALUES ('k_woman', '女', 'woman, girl', 1, 'public', 'zh-Hani')"
    )
    database._insert_gloss_aliases(conn, "k_woman", "woman, girl")

    aliases = {row["alias"] for row in conn.execute(
        "SELECT alias FROM aliases WHERE kanji_id = 'k_woman'"
    )}
    assert aliases == {"woman, girl", "woman", "girl"}