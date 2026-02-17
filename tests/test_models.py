from models import Game, StarSystem, JumpLine, Ship, Structure


def test_create_game(db_session):
    """Game records go in the admin database."""
    game = Game(name="Test Game", num_players=4, status="setup")
    db_session.add(game)
    db_session.commit()
    db_session.refresh(game)

    assert game.game_id is not None
    assert game.name == "Test Game"
    assert game.num_players == 4
    assert game.status == "setup"


def test_create_star_system(game_db_session):
    """Star systems go in the per-game database."""
    system = StarSystem(
        name="Alpha Centauri",
        x=100.0,
        y=200.0,
        mining_value=5,
        cluster_id=0,
        is_home_system=True,
        is_founders_world=False,
    )
    game_db_session.add(system)
    game_db_session.commit()
    game_db_session.refresh(system)

    assert system.system_id is not None
    assert system.name == "Alpha Centauri"
    assert system.mining_value == 5
    assert system.is_home_system is True


def test_create_jump_line(game_db_session):
    """Jump lines go in the per-game database alongside star systems."""
    sys_a = StarSystem(
        name="A", x=0, y=0, mining_value=3, cluster_id=0,
    )
    sys_b = StarSystem(
        name="B", x=100, y=100, mining_value=7, cluster_id=0,
    )
    game_db_session.add_all([sys_a, sys_b])
    game_db_session.commit()

    jump = JumpLine(
        from_system_id=sys_a.system_id,
        to_system_id=sys_b.system_id,
    )
    game_db_session.add(jump)
    game_db_session.commit()
    game_db_session.refresh(jump)

    assert jump.jump_line_id is not None
    assert jump.from_system_id == sys_a.system_id
    assert jump.to_system_id == sys_b.system_id


def test_order_model_exists(game_db_session):
    """Order model can be instantiated and saved."""
    from models import Order
    sys = StarSystem(name="TestSys", x=0, y=0, mining_value=5, materials=0, cluster_id=0,
                     is_home_system=False, is_founders_world=False, owner_player_index=1)
    game_db_session.add(sys)
    game_db_session.flush()

    order = Order(turn_id=1, player_index=1, order_type="move_ships",
                  source_system_id=sys.system_id, target_system_id=sys.system_id, quantity=3)
    game_db_session.add(order)
    game_db_session.commit()
    assert order.order_id is not None
    assert order.order_type == "move_ships"


def test_order_material_source_model(game_db_session):
    """OrderMaterialSource links to an Order."""
    from models import Order, OrderMaterialSource
    sys = StarSystem(name="TestSys", x=0, y=0, mining_value=5, materials=20, cluster_id=0,
                     is_home_system=False, is_founders_world=False, owner_player_index=1)
    game_db_session.add(sys)
    game_db_session.flush()

    order = Order(turn_id=1, player_index=1, order_type="build_mine",
                  source_system_id=sys.system_id)
    game_db_session.add(order)
    game_db_session.flush()

    src = OrderMaterialSource(order_id=order.order_id, source_system_id=sys.system_id, amount=15)
    game_db_session.add(src)
    game_db_session.commit()
    assert src.id is not None
    assert src.amount == 15


def test_player_turn_status_model(game_db_session):
    """PlayerTurnStatus tracks submission."""
    from models import PlayerTurnStatus
    pts = PlayerTurnStatus(turn_id=1, player_index=1, submitted=False)
    game_db_session.add(pts)
    game_db_session.commit()
    assert pts.id is not None
    assert pts.submitted is False


def test_game_with_db_name(db_session):
    """Game stores the name of its per-game database."""
    game = Game(
        name="Test", num_players=2, status="setup",
        db_name="spacegame_game_1",
    )
    db_session.add(game)
    db_session.commit()
    db_session.refresh(game)

    assert game.db_name == "spacegame_game_1"
