"""Tests for Phase 1: initial game state (ships, structures, turns)."""

from models import Ship, Structure, Turn


def test_express_start_creates_initial_ships(client, auth_headers, game_db_session, monkeypatch):
    """Each home system gets 1 ship, Founder's World gets 300 neutral ships."""
    import main
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
        "name": "State Test",
        "num_players": 4,
    }, headers=auth_headers)
    assert response.status_code == 200

    # Check ships in game DB
    all_ships = game_db_session.query(Ship).all()
    assert len(all_ships) >= 5  # 4 home ships + 1 FW ship

    # Find the FW ship (player_index = -1)
    fw_ships = [s for s in all_ships if s.player_index == -1]
    assert len(fw_ships) == 1
    assert fw_ships[0].count == 300

    # Each player should have exactly 1 ship on their home system
    player_ships = [s for s in all_ships if s.player_index >= 0]
    assert len(player_ships) == 4
    for s in player_ships:
        assert s.count == 1


def test_express_start_creates_initial_structures(client, auth_headers, game_db_session, monkeypatch):
    """Each home system gets a mine and a shipyard."""
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

    response = client.post("/games/express-start", json={
        "name": "Struct Test",
        "num_players": 2,
    }, headers=auth_headers)
    assert response.status_code == 200

    structures = game_db_session.query(Structure).all()
    mines = [s for s in structures if s.structure_type == "mine"]
    yards = [s for s in structures if s.structure_type == "shipyard"]

    # 2 players → 2 mines and 2 shipyards
    assert len(mines) == 2
    assert len(yards) == 2

    # Each mine+yard should be on the same system as the player's ship
    for mine in mines:
        matching_yard = [y for y in yards if y.system_id == mine.system_id and y.player_index == mine.player_index]
        assert len(matching_yard) == 1


def test_express_start_creates_turn_1(client, auth_headers, game_db_session, monkeypatch):
    """Express start creates Turn 1 with status 'active'."""
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

    client.post("/games/express-start", json={
        "name": "Turn Test",
        "num_players": 2,
    }, headers=auth_headers)

    turns = game_db_session.query(Turn).all()
    assert len(turns) == 1
    assert turns[0].turn_id == 1
    assert turns[0].status == "active"


def test_map_endpoint_includes_ships_and_structures(client, auth_headers, monkeypatch):
    """GET /games/{id}/map should include ships, structures, players, current_turn."""
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
        "name": "Map API Test",
        "num_players": 2,
    }, headers=auth_headers)
    game_id = game_resp.json()["game_id"]

    response = client.get(f"/games/{game_id}/map")
    assert response.status_code == 200
    data = response.json()

    # Check new fields exist
    assert "ships" in data
    assert "structures" in data
    assert "players" in data
    assert "current_turn" in data
    assert "status" in data

    assert data["current_turn"] == 1
    assert data["status"] == "active"

    # Ships should exist
    assert len(data["ships"]) >= 3  # 2 player ships + 1 FW ship

    # Structures should exist
    assert len(data["structures"]) >= 4  # 2 mines + 2 yards

    # Players should have color and username
    assert len(data["players"]) == 2
    for p in data["players"]:
        assert "username" in p
        assert "color" in p
        assert "player_index" in p
        assert "home_system_name" in p


def test_express_start_creates_player_turn_status(client, auth_headers, game_db_session, monkeypatch):
    """Express start creates a PlayerTurnStatus row per player for Turn 1."""
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

    client.post("/games/express-start", json={
        "name": "PTS Test",
        "num_players": 2,
    }, headers=auth_headers)

    from models import PlayerTurnStatus
    statuses = game_db_session.query(PlayerTurnStatus).all()
    assert len(statuses) == 2
    for s in statuses:
        assert s.turn_id == 1
        assert s.submitted is False


def test_map_endpoint_players_have_correct_colors(client, auth_headers, monkeypatch):
    """Player colors should be assigned from PLAYER_COLORS by player_index."""
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
        "name": "Color Test",
        "num_players": 2,
    }, headers=auth_headers)
    game_id = game_resp.json()["game_id"]

    response = client.get(f"/games/{game_id}/map")
    data = response.json()

    # Check colors are from the expected palette
    expected_colors = ['#e74c3c', '#3498db', '#2ecc71', '#f39c12',
                       '#9b59b6', '#1abc9c', '#e67e22', '#34495e']
    for p in data["players"]:
        assert p["color"] in expected_colors
