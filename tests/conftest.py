import os

# Set dummy DB URL before importing database module (which reads env var at import time)
os.environ.setdefault("postgresDB", "sqlite:///")

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from database import Base, GameBase
from database import get_db
import main


# Admin DB (SQLite for testing)
admin_engine = create_engine(
    "sqlite:///./test_admin.db", connect_args={"check_same_thread": False}
)
AdminSession = sessionmaker(autocommit=False, autoflush=False, bind=admin_engine)

# Game DB (SQLite for testing — single shared DB for all test games)
game_engine = create_engine(
    "sqlite:///./test_game.db", connect_args={"check_same_thread": False}
)
GameSession = sessionmaker(autocommit=False, autoflush=False, bind=game_engine)


@pytest.fixture(autouse=True)
def setup_dbs():
    """Create all tables before each test, drop them after."""
    Base.metadata.create_all(bind=admin_engine)
    GameBase.metadata.create_all(bind=game_engine)
    yield
    GameBase.metadata.drop_all(bind=game_engine)
    Base.metadata.drop_all(bind=admin_engine)


@pytest.fixture
def db_session():
    """Provide an admin database session."""
    session = AdminSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def game_db_session():
    """Provide a game database session."""
    session = GameSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(monkeypatch):
    """Provide a FastAPI test client with mocked DB dependencies."""
    def override_get_db():
        session = AdminSession()
        try:
            yield session
        finally:
            session.close()

    main.app.dependency_overrides[get_db] = override_get_db

    # Mock game database functions on the main module (where they're imported)
    def mock_create_game_db(game_id):
        return f"test_game"

    def mock_get_game_session(game_id):
        return GameSession()

    monkeypatch.setattr(main, "create_game_database", mock_create_game_db)
    monkeypatch.setattr(main, "get_game_session", mock_get_game_session)

    # Also patch get_game_session in turn_resolver (it imports directly)
    import turn_resolver
    monkeypatch.setattr(turn_resolver, "get_game_session", mock_get_game_session)

    yield TestClient(main.app)
    main.app.dependency_overrides.clear()


@pytest.fixture
def auth_headers(client):
    """Register a test user via the API and return auth headers."""
    response = client.post("/auth/register", json={
        "username": "testuser",
        "first_name": "Test",
        "last_name": "User",
        "email": "test@example.com",
        "password": "testpass",
    })
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_headers_2(client):
    """Register a second test user via the API and return auth headers."""
    response = client.post("/auth/register", json={
        "username": "testuser2",
        "first_name": "Test2",
        "last_name": "User2",
        "email": "test2@example.com",
        "password": "testpass2",
    })
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}
