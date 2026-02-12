def test_create_game(client):
    response = client.post("/games", json={
        "name": "Test Game",
        "num_players": 4,
    })
    assert response.status_code == 200
    data = response.json()
    assert "game_id" in data
    assert data["name"] == "Test Game"


def test_generate_map(client):
    # Create game first
    game_resp = client.post("/games", json={
        "name": "Map Test",
        "num_players": 4,
    })
    game_id = game_resp.json()["game_id"]

    # Generate map
    response = client.post(f"/games/{game_id}/generate-map", json={"seed": 42})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "generated"


def test_get_map(client):
    # Create game and generate map
    game_resp = client.post("/games", json={
        "name": "Map Test",
        "num_players": 4,
    })
    game_id = game_resp.json()["game_id"]
    client.post(f"/games/{game_id}/generate-map", json={"seed": 42})

    # Get map
    response = client.get(f"/games/{game_id}/map")
    assert response.status_code == 200
    data = response.json()
    assert "systems" in data
    assert "jump_lines" in data
    assert len(data["systems"]) > 0
    assert any(s["is_founders_world"] for s in data["systems"])


def test_get_map_before_generation(client):
    game_resp = client.post("/games", json={
        "name": "Empty",
        "num_players": 2,
    })
    game_id = game_resp.json()["game_id"]
    response = client.get(f"/games/{game_id}/map")
    assert response.status_code == 404
