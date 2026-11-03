from app.credentials import connect, issue, lookup, revoke


def test_credentials_expire_revoke_and_follow_user_status(tmp_path):
    file = tmp_path / "auth.db"
    token, digest = issue(file, "ws", "owner", ["approval:read"])
    assert lookup(file, token)["user_id"] == "owner"
    assert lookup(file, "unknown") is None
    assert revoke(file, digest) == 1
    assert lookup(file, token) is None
    token, digest = issue(file, "ws", "owner", ["approval:read"])
    db = connect(file)
    with db:
        db.execute("UPDATE auth_tokens SET expires_at=0 WHERE hash=?", (digest,))
    assert lookup(file, token) is None
    token, digest = issue(file, "ws", "owner", ["approval:read"])
    with db:
        db.execute("UPDATE auth_users SET active=0 WHERE user_id=?", ("owner",))
    db.close()
    assert lookup(file, token) is None
    assert token.encode() not in file.read_bytes()


def test_disabling_revokes_all_tokens_without_affecting_other_workspaces(tmp_path):
    from app.credentials import set_user_active, list_users
    import pytest
    file = tmp_path / "auth.db"
    first, _ = issue(file, "one", "alice", ["approval:read"])
    second, _ = issue(file, "one", "alice", ["approval:decide"])
    other, _ = issue(file, "two", "alice", ["approval:read"])
    assert set_user_active(file, "one", "alice", False) == 1
    assert lookup(file, first) is None and lookup(file, second) is None
    assert lookup(file, other) is not None
    with pytest.raises(ValueError, match="disabled"):
        issue(file, "one", "alice", ["approval:read"])
    assert set_user_active(file, "one", "alice", True) == 1
    assert lookup(file, first) is None
    fresh, _ = issue(file, "one", "alice", ["approval:read"])
    assert lookup(file, fresh) is not None
    assert len(list_users(file)) == 2


def test_lookup_never_creates_a_misconfigured_database(tmp_path):
    import sqlite3
    import pytest
    file = tmp_path / "missing.db"
    with pytest.raises(sqlite3.OperationalError):
        lookup(file, "unknown")
    assert not file.exists()
