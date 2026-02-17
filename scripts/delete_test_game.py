"""
delete_test_game.py
-------------------
Removes the test mid-game scenario created by create_test_game.py.

Deletes the most recent game named "test mid-game" (or pass a game_id
as the first argument to target a specific game).

Usage (from back_end/ with venv active and postgresDB set):
    python scripts/delete_test_game.py          # deletes most recent
    python scripts/delete_test_game.py 11       # deletes game #11
"""

import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from models import Game, GamePlayer

GAME_NAME = "test mid-game"


def main():
    base_url = os.environ["postgresDB"]
    admin_url = base_url + "spacegame_admin"

    admin_engine = create_engine(admin_url)
    AdminSession = sessionmaker(bind=admin_engine)
    db = AdminSession()

    try:
        if len(sys.argv) > 1:
            game_id = int(sys.argv[1])
            game = db.query(Game).filter(Game.game_id == game_id).first()
            if not game:
                print(f"ERROR: game #{game_id} not found")
                sys.exit(1)
        else:
            game = (
                db.query(Game)
                .filter(Game.name == GAME_NAME)
                .order_by(Game.game_id.desc())
                .first()
            )
            if not game:
                print(f"ERROR: no game named '{GAME_NAME}' found")
                sys.exit(1)

        game_id = game.game_id
        db_name = game.db_name
        print(f"Deleting game #{game_id}: {game.name} (db: {db_name})")

        # Remove admin records
        db.query(GamePlayer).filter(GamePlayer.game_id == game_id).delete()
        db.query(Game).filter(Game.game_id == game_id).delete()
        db.commit()
        print("Removed game_players and game from admin DB")
    finally:
        db.close()
    admin_engine.dispose()

    # Drop game database
    if db_name:
        postgres_engine = create_engine(base_url + "postgres", isolation_level="AUTOCOMMIT")
        with postgres_engine.connect() as conn:
            # Terminate any open connections first
            conn.execute(text(
                f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                f"WHERE datname = '{db_name}' AND pid <> pg_backend_pid()"
            ))
            conn.execute(text(f"DROP DATABASE IF EXISTS {db_name}"))
        postgres_engine.dispose()
        print(f"Dropped database: {db_name}")

    print("Done.")


if __name__ == "__main__":
    main()
