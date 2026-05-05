def test_register(client):
    resp = client.post("/api/auth/register", json={
        "username": "testuser",
        "email": "test@example.com",
        "password": "test1234"
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["username"] == "testuser"
    assert data["role"] == "contributor"


def test_register_duplicate(client):
    client.post("/api/auth/register", json={
        "username": "testuser", "email": "test@example.com", "password": "test1234"
    })
    resp = client.post("/api/auth/register", json={
        "username": "testuser", "email": "test2@example.com", "password": "test1234"
    })
    assert resp.status_code == 400


def test_login(client):
    client.post("/api/auth/register", json={
        "username": "testuser", "email": "test@example.com", "password": "test1234"
    })
    resp = client.post("/api/auth/login", json={
        "username": "testuser", "password": "test1234"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data


def test_login_wrong_password(client):
    client.post("/api/auth/register", json={
        "username": "testuser", "email": "test@example.com", "password": "test1234"
    })
    resp = client.post("/api/auth/login", json={
        "username": "testuser", "password": "wrong"
    })
    assert resp.status_code == 401


def test_me(client):
    client.post("/api/auth/register", json={
        "username": "testuser", "email": "test@example.com", "password": "test1234"
    })
    login_resp = client.post("/api/auth/login", json={
        "username": "testuser", "password": "test1234"
    })
    token = login_resp.json()["access_token"]
    resp = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["username"] == "testuser"
