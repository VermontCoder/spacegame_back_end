def test_create_game(client, auth_headers):
    response = client.post("/games", json={
        "name": "Test Game",
        "num_players": 4,
    }, headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "game_id" in data
    assert data["name"] == "Test Game"
    assert "creator_id" in data


def test_create_game_without_auth(client):
    response = client.post("/games", json={
        "name": "Test Game",
        "num_players": 4,
    })
    assert response.status_code == 401


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
