from auth import hash_password, verify_password


def test_hash_and_verify_password():
    hashed = hash_password("mypassword")
    assert verify_password("mypassword", hashed)
    assert not verify_password("wrongpassword", hashed)


def test_register_success(client):
    response = client.post("/auth/register", json={
        "username": "newuser",
        "first_name": "New",
        "last_name": "User",
        "email": "new@example.com",
        "password": "secret123",
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["username"] == "newuser"


def test_register_duplicate_username(client):
    payload = {
        "username": "dupeuser",
        "first_name": "A",
        "last_name": "B",
        "email": "a@example.com",
        "password": "pass",
    }
    client.post("/auth/register", json=payload)
    response = client.post("/auth/register", json={
        **payload,
        "email": "different@example.com",
    })
    assert response.status_code == 400
    assert "Username" in response.json()["detail"]


def test_register_duplicate_email(client):
    payload = {
        "username": "user1",
        "first_name": "A",
        "last_name": "B",
        "email": "same@example.com",
        "password": "pass",
    }
    client.post("/auth/register", json=payload)
    response = client.post("/auth/register", json={
        **payload,
        "username": "user2",
    })
    assert response.status_code == 400
    assert "Email" in response.json()["detail"]


def test_login_success(client):
    # Register first
    client.post("/auth/register", json={
        "username": "loginuser",
        "first_name": "L",
        "last_name": "U",
        "email": "login@example.com",
        "password": "mypass",
    })
    response = client.post("/auth/login", json={
        "username": "loginuser",
        "password": "mypass",
    })
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["user"]["username"] == "loginuser"


def test_login_wrong_password(client):
    client.post("/auth/register", json={
        "username": "wrongpw",
        "first_name": "W",
        "last_name": "P",
        "email": "wp@example.com",
        "password": "correct",
    })
    response = client.post("/auth/login", json={
        "username": "wrongpw",
        "password": "incorrect",
    })
    assert response.status_code == 401


def test_login_nonexistent_user(client):
    response = client.post("/auth/login", json={
        "username": "noone",
        "password": "anything",
    })
    assert response.status_code == 401


def test_me_with_valid_token(client, auth_headers):
    response = client.get("/auth/me", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["username"] == "testuser"
    assert "password" not in data


def test_me_without_token(client):
    response = client.get("/auth/me")
    assert response.status_code == 401


def test_me_with_invalid_token(client):
    response = client.get("/auth/me", headers={"Authorization": "Bearer invalid.token.here"})
    assert response.status_code == 401
