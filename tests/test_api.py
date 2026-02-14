from models import GamePlayer


def test_create_game(client, auth_headers):
    response = client.post("/games", json={
        "name": "Test Game",
        "num_players": 4,
    }, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "game_id" in data
    assert data["name"] == "Test Game"
    assert data["status"] == "open"
    assert data["player_count"] == 1
    assert "creator_id" in data


def test_create_game_auto_joins_creator(client, auth_headers, db_session):
    response = client.post("/games", json={
        "name": "Auto Join Test",
        "num_players": 4,
    }, headers=auth_headers)
    game_id = response.json()["game_id"]

    # Check GamePlayer row exists
    player = db_session.query(GamePlayer).filter(
        GamePlayer.game_id == game_id
    ).first()
    assert player is not None
    assert player.player_index == 1


def test_create_game_without_auth(client):
    response = client.post("/games", json={
        "name": "Test Game",
        "num_players": 4,
    })
    assert response.status_code == 401


def test_create_game_invalid_players(client, auth_headers):
    response = client.post("/games", json={
        "name": "Bad Game",
        "num_players": 1,
    }, headers=auth_headers)
    assert response.status_code == 400

    response = client.post("/games", json={
        "name": "Bad Game",
        "num_players": 9,
    }, headers=auth_headers)
    assert response.status_code == 400


def test_list_games(client, auth_headers, auth_headers_2):
    # Create a game as user 1
    client.post("/games", json={
        "name": "User1 Game",
        "num_players": 4,
    }, headers=auth_headers)

    # List games as user 2
    response = client.get("/games", headers=auth_headers_2)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "User1 Game"
    assert data[0]["player_count"] == 1
    assert data[0]["is_member"] is False

    # List games as user 1
    response = client.get("/games", headers=auth_headers)
    data = response.json()
    assert data[0]["is_member"] is True


def test_join_game(client, auth_headers, auth_headers_2):
    # Create a 4-player game as user 1
    game_resp = client.post("/games", json={
        "name": "Join Test",
        "num_players": 4,
    }, headers=auth_headers)
    game_id = game_resp.json()["game_id"]

    # Join as user 2
    response = client.post(f"/games/{game_id}/join", headers=auth_headers_2)
    assert response.status_code == 200
    data = response.json()
    assert data["player_index"] == 2
    assert data["status"] == "open"


def test_join_2_player_game_triggers_auto_start(client, auth_headers, auth_headers_2):
    # Create a 2-player game as user 1
    game_resp = client.post("/games", json={
        "name": "2P Game",
        "num_players": 2,
    }, headers=auth_headers)
    game_id = game_resp.json()["game_id"]

    # Join as user 2 — should trigger map generation
    response = client.post(f"/games/{game_id}/join", headers=auth_headers_2)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "active"


def test_join_already_joined(client, auth_headers):
    game_resp = client.post("/games", json={
        "name": "Double Join",
        "num_players": 4,
    }, headers=auth_headers)
    game_id = game_resp.json()["game_id"]

    # Creator already joined — try joining again
    response = client.post(f"/games/{game_id}/join", headers=auth_headers)
    assert response.status_code == 400
    assert "Already joined" in response.json()["detail"]


def test_join_full_game(client, auth_headers, auth_headers_2):
    # Create a 2-player game, user 1 is already in
    game_resp = client.post("/games", json={
        "name": "Full Game",
        "num_players": 2,
    }, headers=auth_headers)
    game_id = game_resp.json()["game_id"]

    # User 2 joins — fills the game
    client.post(f"/games/{game_id}/join", headers=auth_headers_2)

    # Register user 3 and try to join
    reg_resp = client.post("/auth/register", json={
        "username": "testuser3",
        "first_name": "Test3",
        "last_name": "User3",
        "email": "test3@example.com",
        "password": "testpass3",
    })
    headers_3 = {"Authorization": f"Bearer {reg_resp.json()['access_token']}"}
    response = client.post(f"/games/{game_id}/join", headers=headers_3)
    assert response.status_code == 400
    assert "not open" in response.json()["detail"] or "full" in response.json()["detail"]


def test_express_start(client, auth_headers, monkeypatch):
    import main

    # Mock dev mode check
    monkeypatch.setattr(main, "_is_dev_mode", lambda: True)

    # Create test_user accounts
    for i in range(1, 4):
        client.post("/auth/register", json={
            "username": f"test_user{i}",
            "first_name": f"Test{i}",
            "last_name": f"User{i}",
            "email": f"test_user{i}@example.com",
            "password": "testpass",
        })

    response = client.post("/games/express-start", json={
        "name": "Express Game",
        "num_players": 4,
    }, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "active"
    assert data["num_players"] == 4


def test_express_start_blocked_in_prod(client, auth_headers, monkeypatch):
    import main
    monkeypatch.setattr(main, "_is_dev_mode", lambda: False)

    response = client.post("/games/express-start", json={
        "name": "Should Fail",
        "num_players": 2,
    }, headers=auth_headers)
    assert response.status_code == 403


def test_generate_map(client, auth_headers):
    # Create game first
    game_resp = client.post("/games", json={
        "name": "Map Test",
        "num_players": 4,
    }, headers=auth_headers)
    game_id = game_resp.json()["game_id"]

    # Generate map
    response = client.post(f"/games/{game_id}/generate-map", json={"seed": 42}, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "generated"


def test_get_map(client, auth_headers):
    # Create game and generate map
    game_resp = client.post("/games", json={
        "name": "Map Test",
        "num_players": 4,
    }, headers=auth_headers)
    game_id = game_resp.json()["game_id"]
    client.post(f"/games/{game_id}/generate-map", json={"seed": 42}, headers=auth_headers)

    # Get map (public — no auth needed)
    response = client.get(f"/games/{game_id}/map")
    assert response.status_code == 200
    data = response.json()
    assert "systems" in data
    assert "jump_lines" in data
    assert len(data["systems"]) > 0
    assert any(s["is_founders_world"] for s in data["systems"])
    # Every system should have a materials field
    for s in data["systems"]:
        assert "materials" in s


def test_get_map_before_generation(client, auth_headers):
    game_resp = client.post("/games", json={
        "name": "Empty",
        "num_players": 2,
    }, headers=auth_headers)
    game_id = game_resp.json()["game_id"]
    response = client.get(f"/games/{game_id}/map")
    assert response.status_code == 404
