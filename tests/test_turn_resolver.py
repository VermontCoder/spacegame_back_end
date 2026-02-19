"""Tests for Phase 3: turn resolution engine."""

import json
import random

from models import (
    CombatLog, JumpLine, Order, OrderMaterialSource, PlayerTurnStatus,
    Ship, StarSystem, Structure, Turn, TurnSnapshot,
)


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
        "name": "Resolver Test", "num_players": 2,
    }, headers=auth_headers)
    return resp.json()["game_id"]


def test_resolve_creates_next_turn(client, auth_headers, game_db_session, monkeypatch):
    """After resolution, turn 1 is 'resolved' and turn 2 is 'active'."""
    game_id = _setup_2p_game(client, auth_headers, monkeypatch)

    # Force resolve via endpoint
    resp = client.post(f"/games/{game_id}/force-resolve", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "resolved"

    turns = game_db_session.query(Turn).order_by(Turn.turn_id).all()
    assert len(turns) == 2
    assert turns[0].turn_id == 1
    assert turns[0].status == "resolved"
    assert turns[0].resolved_at is not None
    assert turns[1].turn_id == 2
    assert turns[1].status == "active"


def test_resolve_build_mine(client, auth_headers, game_db_session, monkeypatch):
    """Mine structure appears and materials are deducted after resolution."""
    game_id = _setup_2p_game(client, auth_headers, monkeypatch)

    # Find player 1's home system and an adjacent owned-by-nobody system
    ship = game_db_session.query(Ship).filter(Ship.player_index == 1).first()
    home_id = ship.system_id
    home_sys = game_db_session.query(StarSystem).filter(StarSystem.system_id == home_id).first()

    # Set enough materials on home system
    home_sys.materials = 50
    game_db_session.commit()

    # Find an adjacent system to build mine on — give it to player 1
    jl = game_db_session.query(JumpLine).filter(
        (JumpLine.from_system_id == home_id) | (JumpLine.to_system_id == home_id)
    ).first()
    target_id = jl.to_system_id if jl.from_system_id == home_id else jl.from_system_id
    target_sys = game_db_session.query(StarSystem).filter(StarSystem.system_id == target_id).first()
    target_sys.owner_player_index = 1
    game_db_session.commit()

    # Create build_mine order directly in game DB
    order = Order(
        turn_id=1, player_index=1, order_type="build_mine",
        source_system_id=target_id,
    )
    game_db_session.add(order)
    game_db_session.flush()
    game_db_session.add(OrderMaterialSource(
        order_id=order.order_id, source_system_id=home_id, amount=15,
    ))
    game_db_session.commit()

    client.post(f"/games/{game_id}/force-resolve", headers=auth_headers)

    # Check mine was created
    game_db_session.expire_all()
    mine = game_db_session.query(Structure).filter(
        Structure.system_id == target_id, Structure.structure_type == "mine",
    ).first()
    assert mine is not None
    assert mine.player_index == 1

    # Check materials deducted
    home_sys = game_db_session.query(StarSystem).filter(StarSystem.system_id == home_id).first()
    assert home_sys.materials < 50


def test_resolve_build_shipyard(client, auth_headers, game_db_session, monkeypatch):
    """Shipyard appears and 30 materials deducted after resolution."""
    game_id = _setup_2p_game(client, auth_headers, monkeypatch)

    ship = game_db_session.query(Ship).filter(Ship.player_index == 1).first()
    home_id = ship.system_id
    home_sys = game_db_session.query(StarSystem).filter(StarSystem.system_id == home_id).first()

    # Find an adjacent non-home system to build on (avoid player 2's home which has ships)
    jls = game_db_session.query(JumpLine).filter(
        (JumpLine.from_system_id == home_id) | (JumpLine.to_system_id == home_id)
    ).all()
    target_id = None
    target_sys = None
    for jl in jls:
        adj_id = jl.to_system_id if jl.from_system_id == home_id else jl.from_system_id
        adj_sys = game_db_session.query(StarSystem).filter(StarSystem.system_id == adj_id).first()
        if not adj_sys.is_home_system and not adj_sys.is_founders_world:
            target_id = adj_id
            target_sys = adj_sys
            break
    assert target_id is not None, "No non-home adjacent system found"
    target_sys.owner_player_index = 1
    target_sys.materials = 50
    game_db_session.add(Structure(system_id=target_id, player_index=1, structure_type="mine"))
    game_db_session.commit()

    order = Order(
        turn_id=1, player_index=1, order_type="build_shipyard",
        source_system_id=target_id,
    )
    game_db_session.add(order)
    game_db_session.commit()

    client.post(f"/games/{game_id}/force-resolve", headers=auth_headers)

    game_db_session.expire_all()
    yard = game_db_session.query(Structure).filter(
        Structure.system_id == target_id, Structure.structure_type == "shipyard",
    ).first()
    assert yard is not None

    target_sys = game_db_session.query(StarSystem).filter(StarSystem.system_id == target_id).first()
    # 50 - 30 (shipyard cost) + mining_value (mine production adds it back)
    assert target_sys.materials == 50 - 30 + target_sys.mining_value


def test_resolve_build_ships(client, auth_headers, game_db_session, monkeypatch):
    """Ship count increases and materials deducted after resolution."""
    game_id = _setup_2p_game(client, auth_headers, monkeypatch)

    ship = game_db_session.query(Ship).filter(Ship.player_index == 1).first()
    home_id = ship.system_id
    home_sys = game_db_session.query(StarSystem).filter(StarSystem.system_id == home_id).first()
    home_sys.materials = 20
    game_db_session.commit()

    initial_count = ship.count

    order = Order(
        turn_id=1, player_index=1, order_type="build_ships",
        source_system_id=home_id, quantity=5,
    )
    game_db_session.add(order)
    game_db_session.commit()

    client.post(f"/games/{game_id}/force-resolve", headers=auth_headers)

    game_db_session.expire_all()
    ship = game_db_session.query(Ship).filter(
        Ship.system_id == home_id, Ship.player_index == 1,
    ).first()
    assert ship.count == initial_count + 5

    home_sys = game_db_session.query(StarSystem).filter(StarSystem.system_id == home_id).first()
    # 20 - 5 (ship cost) + mining_value (mine production)
    assert home_sys.materials == 20 - 5 + home_sys.mining_value


def test_resolve_move_ships(client, auth_headers, game_db_session, monkeypatch):
    """Ships move from source to target system."""
    game_id = _setup_2p_game(client, auth_headers, monkeypatch)

    ship = game_db_session.query(Ship).filter(Ship.player_index == 1).first()
    home_id = ship.system_id
    ship.count = 5
    game_db_session.commit()

    jl = game_db_session.query(JumpLine).filter(
        (JumpLine.from_system_id == home_id) | (JumpLine.to_system_id == home_id)
    ).first()
    target_id = jl.to_system_id if jl.from_system_id == home_id else jl.from_system_id

    order = Order(
        turn_id=1, player_index=1, order_type="move_ships",
        source_system_id=home_id, target_system_id=target_id, quantity=3,
    )
    game_db_session.add(order)
    game_db_session.commit()

    client.post(f"/games/{game_id}/force-resolve", headers=auth_headers)

    game_db_session.expire_all()
    src_ship = game_db_session.query(Ship).filter(
        Ship.system_id == home_id, Ship.player_index == 1,
    ).first()
    tgt_ship = game_db_session.query(Ship).filter(
        Ship.system_id == target_id, Ship.player_index == 1,
    ).first()
    assert src_ship.count == 2
    assert tgt_ship is not None
    assert tgt_ship.count == 3


def test_resolve_combat_reduces_ships(client, auth_headers, game_db_session, monkeypatch):
    """Two players fighting results in fewer total ships."""
    game_id = _setup_2p_game(client, auth_headers, monkeypatch)
    random.seed(42)

    # Find a neutral system and place both players' ships there
    neutral = game_db_session.query(StarSystem).filter(
        StarSystem.owner_player_index == None,
        StarSystem.is_founders_world == False,
    ).first()

    game_db_session.add(Ship(system_id=neutral.system_id, player_index=1, count=10))
    game_db_session.add(Ship(system_id=neutral.system_id, player_index=2, count=10))
    game_db_session.commit()

    client.post(f"/games/{game_id}/force-resolve", headers=auth_headers)

    game_db_session.expire_all()
    ships = game_db_session.query(Ship).filter(
        Ship.system_id == neutral.system_id, Ship.count > 0,
    ).all()
    total = sum(s.count for s in ships)
    assert total < 20  # combat must have reduced ships

    # Combat logs should exist
    logs = game_db_session.query(CombatLog).filter(
        CombatLog.system_id == neutral.system_id,
    ).all()
    assert len(logs) > 0


def test_resolve_combat_ownership_changes(client, auth_headers, game_db_session, monkeypatch):
    """Winner of combat takes system ownership and structures transfer."""
    game_id = _setup_2p_game(client, auth_headers, monkeypatch)

    # Use the API's game session (same factory the resolver uses) to add ships
    import main
    api_game_db = main.get_game_session(game_id)

    neutral = api_game_db.query(StarSystem).filter(
        StarSystem.owner_player_index == None,
        StarSystem.is_founders_world == False,
    ).first()
    neutral_id = neutral.system_id

    # Give player 1 overwhelming advantage
    api_game_db.add(Ship(system_id=neutral_id, player_index=1, count=50))
    api_game_db.add(Ship(system_id=neutral_id, player_index=2, count=1))
    api_game_db.commit()
    api_game_db.close()

    resp = client.post(f"/games/{game_id}/force-resolve", headers=auth_headers)
    assert resp.status_code == 200

    # Check via snapshot endpoint (uses a fresh session internally)
    snap_resp = client.get(f"/games/{game_id}/turns/1/snapshot", headers=auth_headers)
    assert snap_resp.status_code == 200
    data = snap_resp.json()

    # Check combat happened at that system
    combat_at_neutral = [l for l in data["combat_logs"] if l["system_id"] == neutral_id]
    assert len(combat_at_neutral) > 0

    # Check ships — only player 1 should remain
    ships_at_neutral = [s for s in data["ships"] if s["system_id"] == neutral_id]
    assert len(ships_at_neutral) == 1, f"Expected 1 ship group, got {ships_at_neutral}"
    assert ships_at_neutral[0]["player_index"] == 1

    target_sys = [s for s in data["systems"] if s["system_id"] == neutral_id][0]
    assert target_sys["owner_player_index"] == 1


def test_resolve_mine_production_adds_materials(client, auth_headers, game_db_session, monkeypatch):
    """Owned system with mine produces materials."""
    game_id = _setup_2p_game(client, auth_headers, monkeypatch)

    # Player 1 home system has a mine already
    ship = game_db_session.query(Ship).filter(Ship.player_index == 1).first()
    home_id = ship.system_id
    home_sys = game_db_session.query(StarSystem).filter(StarSystem.system_id == home_id).first()
    initial_materials = home_sys.materials
    mining_value = home_sys.mining_value

    client.post(f"/games/{game_id}/force-resolve", headers=auth_headers)

    game_db_session.expire_all()
    home_sys = game_db_session.query(StarSystem).filter(StarSystem.system_id == home_id).first()
    assert home_sys.materials == initial_materials + mining_value


def test_resolve_snapshot_saved(client, auth_headers, game_db_session, monkeypatch):
    """TurnSnapshot row is created after resolution."""
    game_id = _setup_2p_game(client, auth_headers, monkeypatch)

    client.post(f"/games/{game_id}/force-resolve", headers=auth_headers)

    game_db_session.expire_all()
    snap = game_db_session.query(TurnSnapshot).filter(TurnSnapshot.turn_id == 1).first()
    assert snap is not None
    systems = json.loads(snap.systems_json)
    ships = json.loads(snap.ships_json)
    assert len(systems) > 0
    assert len(ships) > 0


def test_resolve_turn0_snapshot_exists(client, auth_headers, game_db_session, monkeypatch):
    """After express-start, snapshot with turn_id=0 exists."""
    _setup_2p_game(client, auth_headers, monkeypatch)

    snap = game_db_session.query(TurnSnapshot).filter(TurnSnapshot.turn_id == 0).first()
    assert snap is not None
    systems = json.loads(snap.systems_json)
    assert len(systems) > 0
    orders = json.loads(snap.orders_json)
    assert orders == []


def test_all_submit_triggers_resolve(client, auth_headers, auth_headers_2, game_db_session, monkeypatch):
    """Both players submitting triggers turn resolution."""
    import main
    monkeypatch.setattr(main, "_is_dev_mode", lambda: True)

    # Register user2 as test_user1 for the express start
    # auth_headers_2 already registered testuser2
    # We need to register test_user1 for the express start
    client.post("/auth/register", json={
        "username": "test_user1", "first_name": "T1",
        "last_name": "U1", "email": "tu1@example.com", "password": "p",
    })

    # Create 2-player game where testuser is player 1 and testuser2 is player 2
    game_resp = client.post("/games", json={
        "name": "Submit Test", "num_players": 2,
    }, headers=auth_headers)
    game_id = game_resp.json()["game_id"]
    client.post(f"/games/{game_id}/join", headers=auth_headers_2)

    # Player 1 submits
    resp1 = client.post(f"/games/{game_id}/turns/1/submit", headers=auth_headers)
    assert resp1.status_code == 200
    assert resp1.json()["turn_resolved"] is False

    # Player 2 submits — should trigger resolution
    resp2 = client.post(f"/games/{game_id}/turns/1/submit", headers=auth_headers_2)
    assert resp2.status_code == 200
    assert resp2.json()["turn_resolved"] is True

    # Verify turn advanced
    turns = game_db_session.query(Turn).order_by(Turn.turn_id).all()
    assert len(turns) == 2
    assert turns[0].status == "resolved"
    assert turns[1].status == "active"


def test_force_resolve_endpoint(client, auth_headers, game_db_session, monkeypatch):
    """POST /force-resolve returns 200 and advances turn."""
    game_id = _setup_2p_game(client, auth_headers, monkeypatch)

    resp = client.post(f"/games/{game_id}/force-resolve", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "resolved"
    assert data["turn_id"] == 1


def test_snapshot_endpoint(client, auth_headers, game_db_session, monkeypatch):
    """GET /turns/0/snapshot returns correct initial state data."""
    game_id = _setup_2p_game(client, auth_headers, monkeypatch)

    resp = client.get(f"/games/{game_id}/turns/0/snapshot", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["turn_id"] == 0
    assert "systems" in data
    assert "ships" in data
    assert "structures" in data
    assert "orders" in data
    assert "combat_logs" in data
    assert data["orders"] == []
    assert len(data["systems"]) > 0


def test_victory_detection(client, auth_headers, game_db_session, db_session, monkeypatch):
    """Placing ships on FW and resolving sets game to completed."""
    game_id = _setup_2p_game(client, auth_headers, monkeypatch)

    # Find Founder's World
    fw = game_db_session.query(StarSystem).filter(StarSystem.is_founders_world == True).first()
    assert fw is not None

    # Remove neutral ships from FW
    game_db_session.query(Ship).filter(Ship.system_id == fw.system_id).delete()
    # Place player 1 ships on FW
    game_db_session.add(Ship(system_id=fw.system_id, player_index=1, count=10))
    game_db_session.commit()

    client.post(f"/games/{game_id}/force-resolve", headers=auth_headers)

    # Check game status in admin DB
    from models import Game
    game = db_session.query(Game).filter(Game.game_id == game_id).first()
    assert game.status == "completed"
    assert game.winner_player_index == 1
