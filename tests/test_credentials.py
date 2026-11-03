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
