import os

from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_NAME = "spacegame_admin"
BASE_URL = os.environ["postgresDB"]
DATABASE_URL = BASE_URL + DATABASE_NAME

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

Base = declarative_base()      # Admin tables (users, games)
GameBase = declarative_base()  # Per-game tables (star_systems, jump_lines)

# Cache for game engines to avoid creating new ones per request
_game_engines: dict[int, object] = {}


def get_db():
    """FastAPI dependency that provides an admin database session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_game_db_name(game_id: int) -> str:
    """Return the database name for a specific game."""
    return f"spacegame_game_{game_id}"


def _get_game_engine(game_id: int):
    """Get or create a cached SQLAlchemy engine for a game database."""
    if game_id not in _game_engines:
        db_name = get_game_db_name(game_id)
        game_url = BASE_URL + db_name
        _game_engines[game_id] = create_engine(game_url)
    return _game_engines[game_id]


def create_game_database(game_id: int) -> str:
    """Create a new PostgreSQL database for a game and set up its tables.

    Returns the database name.
    """
    db_name = get_game_db_name(game_id)

    # Connect to the default 'postgres' database to run CREATE DATABASE.
    # CREATE DATABASE cannot run inside a transaction, so we use AUTOCOMMIT.
    postgres_engine = create_engine(BASE_URL + "postgres", isolation_level="AUTOCOMMIT")
    with postgres_engine.connect() as conn:
        conn.execute(text(f"CREATE DATABASE {db_name}"))
    postgres_engine.dispose()

    # Create tables in the new game database
    game_engine = _get_game_engine(game_id)
    GameBase.metadata.create_all(bind=game_engine)

    return db_name


def get_game_session(game_id: int):
    """Get a database session for a specific game's database."""
    game_engine = _get_game_engine(game_id)
    GameSessionLocal = sessionmaker(bind=game_engine, autocommit=False, autoflush=False)
    return GameSessionLocal()


def drop_game_database(game_id: int):
    """Dispose the cached engine and drop the PostgreSQL database for a game."""
    db_name = get_game_db_name(game_id)

    # Dispose and remove the cached engine so connections are closed
    if game_id in _game_engines:
        _game_engines[game_id].dispose()
        del _game_engines[game_id]

    # Connect to the default 'postgres' database and drop the game DB
    postgres_engine = create_engine(BASE_URL + "postgres", isolation_level="AUTOCOMMIT")
    with postgres_engine.connect() as conn:
        # Terminate any remaining connections to the game database before dropping
        conn.execute(text(
            f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname = '{db_name}' AND pid <> pg_backend_pid()"
        ))
        conn.execute(text(f"DROP DATABASE IF EXISTS {db_name}"))
    postgres_engine.dispose()
