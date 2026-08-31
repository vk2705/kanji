"""
Isolated migration tests (architecture review finding #3): migrating from each
supported schema version, plus the ordinary end-to-end paths. The fault-injection/
rollback-atomicity test lives in test_regression_fixes.py's check_migration_atomicity()
(added alongside the migrate_schema() atomicity fix, 2026-08-31) rather than here,
since that one intentionally runs against the live-DB-adjacent test convention; these
tests use the same temp-DB/TestClient fixtures as the rest of this isolated suite.
"""
import sqlite3

import database
from database import init_db, migrate_schema, _MIGRATIONS


def test_fresh_db_migrates_to_latest(db_path):
    conn = database.get_db()
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    latest = max(v for v, _ in _MIGRATIONS)
    assert version == latest
    conn.close()


def test_migration_is_idempotent(db_path):
    """Running migrate_schema() again against an already-migrated DB is a safe no-op."""
    conn = database.get_db()
    migrate_schema(conn)  # db_path fixture already migrated once; this should no-op
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    assert version == max(v for v, _ in _MIGRATIONS)
    conn.close()


def test_each_version_migrates_cleanly_in_sequence(tmp_path):
    """Starting from user_version 0 and applying every registered migration in order
    (the real production path for a truly ancient DB, or any DB that was ever at an
    intermediate version) succeeds and lands on the latest version, with every
    expected table present at the end."""
    path = tmp_path / "sequence_test.db"
    saved = database.DB_PATH
    database.DB_PATH = path
    try:
        init_db()
        conn = database.get_db()
        migrate_schema(conn)
        version = conn.execute("PRAGMA user_version").fetchone()[0]
        assert version == max(v for v, _ in _MIGRATIONS)

        expected_tables = {
            "kanji", "aliases", "parts", "users", "sessions", "decompositions",
            "stories", "decomposition_reviews", "page_views", "user_entry_seq",
        }
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert expected_tables <= tables, f"missing: {expected_tables - tables}"
        conn.close()
    finally:
        database.DB_PATH = saved


def test_migrating_from_each_intermediate_version(tmp_path):
    """For each registered version N, simulate a DB that's already at N-1 (by running
    migrate_schema() up through N-1 only, via a filtered _MIGRATIONS list) and confirm
    migrating the rest of the way to latest succeeds cleanly. This is what actually
    exercises the review's "migration from each supported schema version" ask -- each
    individual _migrate_vN function gets run against a DB in exactly the state it
    expects (freshly arrived at version N-1), not just the aggregate 0->latest path."""
    all_migrations = sorted(_MIGRATIONS, key=lambda pair: pair[0])
    latest = all_migrations[-1][0]

    for target_version, _ in all_migrations:
        path = tmp_path / f"from_v{target_version - 1}.db"
        saved_path = database.DB_PATH
        saved_migrations = list(database._MIGRATIONS)
        try:
            database.DB_PATH = path
            init_db()
            conn = database.get_db()

            # Advance to target_version - 1 using only the earlier migrations.
            database._MIGRATIONS[:] = [
                (v, fn) for v, fn in all_migrations if v < target_version
            ]
            migrate_schema(conn)
            pre_version = conn.execute("PRAGMA user_version").fetchone()[0]
            assert pre_version == target_version - 1

            # Now run the real, full migration set the rest of the way.
            database._MIGRATIONS[:] = all_migrations
            migrate_schema(conn)
            post_version = conn.execute("PRAGMA user_version").fetchone()[0]
            assert post_version == latest, (
                f"migrating from v{target_version - 1} through v{target_version} "
                f"onward landed at {post_version}, expected {latest}"
            )
            conn.close()
        finally:
            database.DB_PATH = saved_path
            database._MIGRATIONS[:] = saved_migrations


def test_v1_creates_reserved_system_user(db_path):
    """_migrate_v1 must always create the id=1 'system' account (CLAUDE.md: "id=1 in
    users is a reserved system account... immutable to normal users by construction")."""
    conn = database.get_db()
    row = conn.execute("SELECT id, username, auth_provider FROM users WHERE id = 1").fetchone()
    assert row is not None
    assert row["username"] == "system"
    assert row["auth_provider"] == "system"
    conn.close()


def test_migrated_aliases_table_allows_same_alias_different_owners(db_path):
    """_migrate_v1 rebuilds aliases from UNIQUE(kanji_id, alias) to
    UNIQUE(kanji_id, alias, owner_id) -- confirm the new constraint actually is what
    ends up live, not just that the rebuild ran without erroring."""
    conn = database.get_db()
    conn.execute(
        "INSERT INTO kanji (id, character, keyword, owner_id, visibility, script) "
        "VALUES ('test1', '?', 'test', 1, 'public', 'ja-kanji')"
    )
    conn.execute(
        "INSERT INTO users (id, username, auth_provider) VALUES (500, 'u500', 'local')"
    )
    conn.execute(
        "INSERT INTO users (id, username, auth_provider) VALUES (501, 'u501', 'local')"
    )
    conn.execute(
        "INSERT INTO aliases (kanji_id, alias, owner_id, visibility) VALUES ('test1', 'dup', 500, 'public')"
    )
    conn.execute(
        "INSERT INTO aliases (kanji_id, alias, owner_id, visibility) VALUES ('test1', 'dup', 501, 'public')"
    )
    conn.commit()  # would raise IntegrityError if the old, stricter UNIQUE survived

    # But the same (kanji_id, alias, owner_id) triple twice must still be rejected.
    try:
        conn.execute(
            "INSERT INTO aliases (kanji_id, alias, owner_id, visibility) VALUES ('test1', 'dup', 500, 'private')"
        )
        conn.commit()
        assert False, "expected UNIQUE(kanji_id, alias, owner_id) to reject an exact duplicate"
    except sqlite3.IntegrityError:
        pass
    conn.close()
