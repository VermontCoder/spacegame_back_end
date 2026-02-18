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


def test_get_map(client, auth_headers, monkeypatch):
    import main
    monkeypatch.setattr(main, "_is_dev_mode", lambda: True)
    client.post("/auth/register", json={
        "username": "test_user1", "first_name": "T1", "last_name": "U1",
        "email": "tu1@example.com", "password": "p",
    })
    game_resp = client.post("/games/express-start", json={
        "name": "Map Test", "num_players": 2,
    }, headers=auth_headers)
    game_id = game_resp.json()["game_id"]

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


def test_get_turn_status_returns_all_players(client, auth_headers, game_db_session, monkeypatch):
    """GET /games/{id}/turns/1/status returns submission status for all players."""
    import main
    monkeypatch.setattr(main, "_is_dev_mode", lambda: True)

    for i in range(1, 2):
        client.post("/auth/register", json={
            "username": f"test_user{i}",
            "first_name": f"Test{i}",
            "last_name": f"User{i}",
            "email": f"test_user{i}@example.com",
            "password": "testpass",
        })

    game_resp = client.post("/games/express-start", json={
        "name": "Status Test", "num_players": 2,
    }, headers=auth_headers)
    game_id = game_resp.json()["game_id"]

    resp = client.get(f"/games/{game_id}/turns/1/status", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    for entry in data:
        assert "player_index" in entry
        assert "username" in entry
        assert entry["submitted"] is False


def _setup_2p_game(client, auth_headers, monkeypatch):
    """Helper: create a 2-player express-start game and return game_id."""
    import main
    monkeypatch.setattr(main, "_is_dev_mode", lambda: True)
    for i in range(1, 2):
        client.post("/auth/register", json={
            "username": f"test_user{i}", "first_name": f"T{i}",
            "last_name": f"U{i}", "email": f"tu{i}@example.com", "password": "p",
        })
    resp = client.post("/games/express-start", json={
        "name": "Order Test", "num_players": 2,
    }, headers=auth_headers)
    return resp.json()["game_id"]


def test_create_move_order_success(client, auth_headers, game_db_session, monkeypatch):
    """POST move_ships order succeeds for valid adjacent move."""
    game_id = _setup_2p_game(client, auth_headers, monkeypatch)

    # Find player 1's home system and an adjacent system
    from models import Ship, JumpLine
    ship = game_db_session.query(Ship).filter(Ship.player_index == 1).first()
    home_id = ship.system_id
    jl = game_db_session.query(JumpLine).filter(
        (JumpLine.from_system_id == home_id) | (JumpLine.to_system_id == home_id)
    ).first()
    target_id = jl.to_system_id if jl.from_system_id == home_id else jl.from_system_id

    resp = client.post(f"/games/{game_id}/turns/1/orders", json={
        "order_type": "move_ships",
        "source_system_id": home_id,
        "target_system_id": target_id,
        "quantity": 1,
    }, headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["order_type"] == "move_ships"
    assert data["order_id"] is not None


def test_create_move_order_not_adjacent(client, auth_headers, game_db_session, monkeypatch):
    """POST move_ships to non-adjacent system fails."""
    game_id = _setup_2p_game(client, auth_headers, monkeypatch)

    from models import Ship, StarSystem, JumpLine
    ship = game_db_session.query(Ship).filter(Ship.player_index == 1).first()
    home_id = ship.system_id

    # Find a system NOT adjacent to home
    adjacent_ids = set()
    for jl in game_db_session.query(JumpLine).filter(
        (JumpLine.from_system_id == home_id) | (JumpLine.to_system_id == home_id)
    ).all():
        adjacent_ids.add(jl.to_system_id if jl.from_system_id == home_id else jl.from_system_id)

    non_adjacent = game_db_session.query(StarSystem).filter(
        StarSystem.system_id != home_id,
        ~StarSystem.system_id.in_(adjacent_ids)
    ).first()

    if non_adjacent:
        resp = client.post(f"/games/{game_id}/turns/1/orders", json={
            "order_type": "move_ships",
            "source_system_id": home_id,
            "target_system_id": non_adjacent.system_id,
            "quantity": 1,
        }, headers=auth_headers)
        assert resp.status_code == 400


def test_create_move_order_exceeds_ships(client, auth_headers, game_db_session, monkeypatch):
    """POST move_ships with quantity > available ships fails."""
    game_id = _setup_2p_game(client, auth_headers, monkeypatch)

    from models import Ship, JumpLine
    ship = game_db_session.query(Ship).filter(Ship.player_index == 1).first()
    home_id = ship.system_id
    jl = game_db_session.query(JumpLine).filter(
        (JumpLine.from_system_id == home_id) | (JumpLine.to_system_id == home_id)
    ).first()
    target_id = jl.to_system_id if jl.from_system_id == home_id else jl.from_system_id

    resp = client.post(f"/games/{game_id}/turns/1/orders", json={
        "order_type": "move_ships",
        "source_system_id": home_id,
        "target_system_id": target_id,
        "quantity": 999,
    }, headers=auth_headers)
    assert resp.status_code == 400


def test_get_orders_returns_player_orders(client, auth_headers, game_db_session, monkeypatch):
    """GET /orders returns the current player's orders."""
    game_id = _setup_2p_game(client, auth_headers, monkeypatch)

    from models import Ship, JumpLine
    ship = game_db_session.query(Ship).filter(Ship.player_index == 1).first()
    home_id = ship.system_id
    jl = game_db_session.query(JumpLine).filter(
        (JumpLine.from_system_id == home_id) | (JumpLine.to_system_id == home_id)
    ).first()
    target_id = jl.to_system_id if jl.from_system_id == home_id else jl.from_system_id

    client.post(f"/games/{game_id}/turns/1/orders", json={
        "order_type": "move_ships", "source_system_id": home_id,
        "target_system_id": target_id, "quantity": 1,
    }, headers=auth_headers)

    resp = client.get(f"/games/{game_id}/turns/1/orders", headers=auth_headers)
    assert resp.status_code == 200
    orders = resp.json()
    assert len(orders) == 1
    assert orders[0]["order_type"] == "move_ships"


def test_delete_order_success(client, auth_headers, game_db_session, monkeypatch):
    """DELETE /orders/{id} removes the order."""
    game_id = _setup_2p_game(client, auth_headers, monkeypatch)

    from models import Ship, JumpLine
    ship = game_db_session.query(Ship).filter(Ship.player_index == 1).first()
    home_id = ship.system_id
    jl = game_db_session.query(JumpLine).filter(
        (JumpLine.from_system_id == home_id) | (JumpLine.to_system_id == home_id)
    ).first()
    target_id = jl.to_system_id if jl.from_system_id == home_id else jl.from_system_id

    create_resp = client.post(f"/games/{game_id}/turns/1/orders", json={
        "order_type": "move_ships", "source_system_id": home_id,
        "target_system_id": target_id, "quantity": 1,
    }, headers=auth_headers)
    order_id = create_resp.json()["order_id"]

    del_resp = client.delete(f"/games/{game_id}/turns/1/orders/{order_id}", headers=auth_headers)
    assert del_resp.status_code == 200

    get_resp = client.get(f"/games/{game_id}/turns/1/orders", headers=auth_headers)
    assert len(get_resp.json()) == 0


def test_submit_turn_success(client, auth_headers, game_db_session, monkeypatch):
    """POST /submit marks player as submitted."""
    game_id = _setup_2p_game(client, auth_headers, monkeypatch)

    resp = client.post(f"/games/{game_id}/turns/1/submit", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["submitted"] is True

    # Verify in status endpoint
    status_resp = client.get(f"/games/{game_id}/turns/1/status", headers=auth_headers)
    statuses = status_resp.json()
    p1 = [s for s in statuses if s["player_index"] == 1][0]
    assert p1["submitted"] is True


def test_submit_turn_prevents_new_orders(client, auth_headers, game_db_session, monkeypatch):
    """After submitting, creating new orders fails."""
    game_id = _setup_2p_game(client, auth_headers, monkeypatch)

    client.post(f"/games/{game_id}/turns/1/submit", headers=auth_headers)

    from models import Ship, JumpLine
    ship = game_db_session.query(Ship).filter(Ship.player_index == 1).first()
    home_id = ship.system_id
    jl = game_db_session.query(JumpLine).filter(
        (JumpLine.from_system_id == home_id) | (JumpLine.to_system_id == home_id)
    ).first()
    target_id = jl.to_system_id if jl.from_system_id == home_id else jl.from_system_id

    resp = client.post(f"/games/{game_id}/turns/1/orders", json={
        "order_type": "move_ships", "source_system_id": home_id,
        "target_system_id": target_id, "quantity": 1,
    }, headers=auth_headers)
    assert resp.status_code == 400


def test_submit_turn_prevents_delete(client, auth_headers, game_db_session, monkeypatch):
    """After submitting, deleting orders fails."""
    game_id = _setup_2p_game(client, auth_headers, monkeypatch)

    from models import Ship, JumpLine
    ship = game_db_session.query(Ship).filter(Ship.player_index == 1).first()
    home_id = ship.system_id
    jl = game_db_session.query(JumpLine).filter(
        (JumpLine.from_system_id == home_id) | (JumpLine.to_system_id == home_id)
    ).first()
    target_id = jl.to_system_id if jl.from_system_id == home_id else jl.from_system_id

    create_resp = client.post(f"/games/{game_id}/turns/1/orders", json={
        "order_type": "move_ships", "source_system_id": home_id,
        "target_system_id": target_id, "quantity": 1,
    }, headers=auth_headers)
    order_id = create_resp.json()["order_id"]

    client.post(f"/games/{game_id}/turns/1/submit", headers=auth_headers)

    del_resp = client.delete(f"/games/{game_id}/turns/1/orders/{order_id}", headers=auth_headers)
    assert del_resp.status_code == 400
