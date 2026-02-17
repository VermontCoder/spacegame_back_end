"""
create_test_game.py
-------------------
Creates a mid-game test scenario directly in the database.

5 players (test_user_0 … test_user_4), each with:
  - A home system (mine + shipyard)
  - 2–3 captured adjacent systems (some with mines/yards)
  - 24 ships spread across their systems
  - 50 materials in every system

The map is a pentagon: FW at centre, homes at the corners, expansion
systems further out, with border jump-lines connecting neighbouring
clusters so the game is fully connected.

Usage (from back_end/ with venv active and postgresDB set):
    python scripts/create_test_game.py
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import psycopg2
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from database import GameBase, get_game_db_name
from models import (
    StarSystem, JumpLine, Ship, Structure, Turn, PlayerTurnStatus,
    Game, GamePlayer, User,
)
from database import Base

GAME_NAME = "test mid-game"
NUM_PLAYERS = 5
MATERIALS = 50

# ---------------------------------------------------------------------------
# Map layout (viewBox 1440×840)
# ---------------------------------------------------------------------------
#
#   Index  Name              x     y   mining  cluster  home   FW   owner
SYSTEMS = [
    # FW
    dict(idx=0,  name="Founder's World", x=720, y=420, mv=0,  cl=0,  home=False, fw=True,  owner=None),
    # Home systems
    dict(idx=1,  name="Sargas",          x=720, y=195, mv=5,  cl=1,  home=True,  fw=False, owner=1),
    dict(idx=2,  name="Castor",          x=933, y=327, mv=5,  cl=2,  home=True,  fw=False, owner=2),
    dict(idx=3,  name="Spica",           x=862, y=558, mv=5,  cl=3,  home=True,  fw=False, owner=3),
    dict(idx=4,  name="Sirius",          x=578, y=558, mv=5,  cl=4,  home=True,  fw=False, owner=4),
    dict(idx=5,  name="Arcturus",        x=507, y=327, mv=5,  cl=5,  home=True,  fw=False, owner=5),
    # Player 1 expansions (3 systems)
    dict(idx=6,  name="Antares",         x=565, y=115, mv=4,  cl=1,  home=False, fw=False, owner=1),
    dict(idx=7,  name="Shaula",          x=875, y=115, mv=6,  cl=1,  home=False, fw=False, owner=1),
    dict(idx=8,  name="Lesath",          x=720, y=68,  mv=3,  cl=1,  home=False, fw=False, owner=1),
    # Player 2 expansions (3 systems)
    dict(idx=9,  name="Pollux",          x=1065,y=228, mv=4,  cl=2,  home=False, fw=False, owner=2),
    dict(idx=10, name="Procyon",         x=1085,y=418, mv=7,  cl=2,  home=False, fw=False, owner=2),
    dict(idx=11, name="Alhena",          x=998, y=155, mv=3,  cl=2,  home=False, fw=False, owner=2),
    # Player 3 expansions (2 systems)
    dict(idx=12, name="Mimosa",          x=1002,y=648, mv=5,  cl=3,  home=False, fw=False, owner=3),
    dict(idx=13, name="Acrux",           x=802, y=708, mv=3,  cl=3,  home=False, fw=False, owner=3),
    # Player 4 expansions (2 systems)
    dict(idx=14, name="Kaus Australis",  x=618, y=708, mv=6,  cl=4,  home=False, fw=False, owner=4),
    dict(idx=15, name="Nunki",           x=418, y=648, mv=4,  cl=4,  home=False, fw=False, owner=4),
    # Player 5 expansions (2 systems)
    dict(idx=16, name="Dubhe",           x=365, y=418, mv=5,  cl=5,  home=False, fw=False, owner=5),
    dict(idx=17, name="Merak",           x=365, y=218, mv=3,  cl=5,  home=False, fw=False, owner=5),
]

# Jump lines as (from_idx, to_idx)
JUMP_LINES = [
    # FW to all homes
    (0, 1), (0, 2), (0, 3), (0, 4), (0, 5),
    # Player 1 cluster
    (1, 6), (1, 7), (1, 8), (6, 8), (7, 8),
    # Player 2 cluster
    (2, 9), (2, 10), (2, 11), (9, 11), (10, 11),
    # Player 3 cluster
    (3, 12), (3, 13), (12, 13),
    # Player 4 cluster
    (4, 14), (4, 15), (14, 15),
    # Player 5 cluster
    (5, 16), (5, 17), (16, 17),
    # Border connections (neighbouring clusters touch)
    (6, 17),   # P1 ↔ P5 (top-left)
    (7, 11),   # P1 ↔ P2 (top-right)
    (10, 12),  # P2 ↔ P3 (right)
    (13, 14),  # P3 ↔ P4 (bottom)
    (15, 16),  # P4 ↔ P5 (left)
]

# Structures: (system_idx, structure_type)
# Rules: home systems get mine+yard; some expansions get mine or mine+yard
STRUCTURES = [
    # Player 1
    (1, "mine"), (1, "shipyard"),  # Sargas (home)
    (6, "mine"),                   # Antares: mine only
    (7, "mine"), (7, "shipyard"),  # Shaula: mine+yard
    # Lesath (8): nothing
    # Player 2
    (2, "mine"), (2, "shipyard"),  # Castor (home)
    (9, "mine"),                   # Pollux: mine only
    (10, "mine"), (10, "shipyard"),# Procyon: mine+yard
    # Alhena (11): nothing
    # Player 3
    (3, "mine"), (3, "shipyard"),  # Spica (home)
    (12, "mine"),                  # Mimosa: mine only
    # Acrux (13): nothing
    # Player 4
    (4, "mine"), (4, "shipyard"),  # Sirius (home)
    (14, "mine"), (14, "shipyard"),# Kaus Australis: mine+yard
    # Nunki (15): nothing
    # Player 5
    (5, "mine"), (5, "shipyard"),  # Arcturus (home)
    (16, "mine"),                  # Dubhe: mine only
    # Merak (17): nothing
]

# Ships: (system_idx, player_index, count)
SHIPS = [
    (0,  -1, 300),  # FW: 300 neutral
    # Player 1 – 24 total across 4 systems
    (1,   1, 8),
    (6,   1, 6),
    (7,   1, 6),
    (8,   1, 4),
    # Player 2 – 24 total
    (2,   2, 8),
    (9,   2, 6),
    (10,  2, 6),
    (11,  2, 4),
    # Player 3 – 24 total
    (3,   3, 10),
    (12,  3, 8),
    (13,  3, 6),
    # Player 4 – 24 total
    (4,   4, 10),
    (14,  4, 8),
    (15,  4, 6),
    # Player 5 – 24 total
    (5,   5, 10),
    (16,  5, 8),
    (17,  5, 6),
]


def main():
    base_url = os.environ["postgresDB"]
    admin_url = base_url + "spacegame_admin"

    # --- Admin DB: create game + game_players ---
    admin_engine = create_engine(admin_url)
    AdminSession = sessionmaker(bind=admin_engine)
    db = AdminSession()

    try:
        # Find test users 0-4
        users = (
            db.query(User)
            .filter(User.username.in_([f"test_user_{i}" for i in range(NUM_PLAYERS)]))
            .order_by(User.username)
            .all()
        )
        if len(users) < NUM_PLAYERS:
            print(f"ERROR: need {NUM_PLAYERS} test_user accounts, found {len(users)}")
            sys.exit(1)

        # Create game record
        creator = next(u for u in users if u.username == "test_user_0")
        game = Game(
            name=GAME_NAME,
            num_players=NUM_PLAYERS,
            status="active",
            creator_id=creator.user_id,
            current_turn=1,
        )
        db.add(game)
        db.flush()
        game_id = game.game_id
        print(f"Created game #{game_id}: {GAME_NAME}")

        # Assign player_index 1-5 to test_user_0 … test_user_4
        for i, user in enumerate(users):
            db.add(GamePlayer(game_id=game_id, user_id=user.user_id, player_index=i + 1))

        db.commit()
    finally:
        db.close()
    admin_engine.dispose()

    # --- Create game database ---
    postgres_engine = create_engine(base_url + "postgres", isolation_level="AUTOCOMMIT")
    db_name = get_game_db_name(game_id)
    with postgres_engine.connect() as conn:
        conn.execute(text(f"CREATE DATABASE {db_name}"))
    postgres_engine.dispose()
    print(f"Created database: {db_name}")

    # Update game.db_name
    admin_engine = create_engine(admin_url)
    AdminSession = sessionmaker(bind=admin_engine)
    db = AdminSession()
    try:
        game = db.query(Game).filter(Game.game_id == game_id).first()
        game.db_name = db_name
        db.commit()
    finally:
        db.close()
    admin_engine.dispose()

    # --- Populate game database ---
    game_engine = create_engine(base_url + db_name)
    GameBase.metadata.create_all(bind=game_engine)
    GameSession = sessionmaker(bind=game_engine)
    gdb = GameSession()

    try:
        # Insert systems
        idx_to_id = {}
        for s in SYSTEMS:
            sys_obj = StarSystem(
                name=s["name"],
                x=float(s["x"]),
                y=float(s["y"]),
                mining_value=s["mv"],
                materials=MATERIALS,
                cluster_id=s["cl"],
                is_home_system=s["home"],
                is_founders_world=s["fw"],
                owner_player_index=s["owner"],
            )
            gdb.add(sys_obj)
            gdb.flush()
            idx_to_id[s["idx"]] = sys_obj.system_id

        # Insert jump lines
        for from_idx, to_idx in JUMP_LINES:
            gdb.add(JumpLine(
                from_system_id=idx_to_id[from_idx],
                to_system_id=idx_to_id[to_idx],
            ))

        # Insert structures
        for sys_idx, stype in STRUCTURES:
            owner = next(s["owner"] for s in SYSTEMS if s["idx"] == sys_idx)
            gdb.add(Structure(
                system_id=idx_to_id[sys_idx],
                player_index=owner,
                structure_type=stype,
            ))

        # Insert ships
        for sys_idx, player_idx, count in SHIPS:
            gdb.add(Ship(
                system_id=idx_to_id[sys_idx],
                player_index=player_idx,
                count=count,
            ))

        # Turn 1 (active)
        gdb.add(Turn(turn_id=1, status="active"))

        # PlayerTurnStatus for each player
        for pi in range(1, NUM_PLAYERS + 1):
            gdb.add(PlayerTurnStatus(turn_id=1, player_index=pi, submitted=False))

        gdb.commit()
        print(f"Game database populated: {len(SYSTEMS)} systems, {len(JUMP_LINES)} jump lines")
        print(f"\nGame #{game_id} ready. Navigate to /game/{game_id}/map to test.")
    finally:
        gdb.close()
    game_engine.dispose()


if __name__ == "__main__":
    main()
