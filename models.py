from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer, String, func
)
from sqlalchemy.orm import relationship

from database import Base, GameBase


# --- Admin tables (spacegame_admin database) ---

class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), nullable=False, unique=True)
    first_name = Column(String(50), nullable=False)
    last_name = Column(String(50), nullable=False)
    email = Column(String(100), nullable=False, unique=True)
    password = Column(String(255), nullable=False)


class Game(Base):
    __tablename__ = "games"

    game_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    num_players = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False, default="setup")
    seed = Column(Integer, nullable=True)
    db_name = Column(String(100), nullable=True)
    creator_id = Column(Integer, ForeignKey("users.user_id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    creator = relationship("User", backref="games")


# --- Per-game tables (spacegame_game_{id} databases) ---

class StarSystem(GameBase):
    __tablename__ = "star_systems"

    system_id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), nullable=False)
    x = Column(Float, nullable=False)
    y = Column(Float, nullable=False)
    mining_value = Column(Integer, nullable=False, default=0)
    materials = Column(Integer, nullable=False, default=0)
    cluster_id = Column(Integer, nullable=False)
    is_home_system = Column(Boolean, nullable=False, default=False)
    is_founders_world = Column(Boolean, nullable=False, default=False)
    owner_player_index = Column(Integer, nullable=True)


class JumpLine(GameBase):
    __tablename__ = "jump_lines"

    jump_line_id = Column(Integer, primary_key=True, autoincrement=True)
    from_system_id = Column(Integer, ForeignKey("star_systems.system_id"), nullable=False)
    to_system_id = Column(Integer, ForeignKey("star_systems.system_id"), nullable=False)

    from_system = relationship("StarSystem", foreign_keys=[from_system_id])
    to_system = relationship("StarSystem", foreign_keys=[to_system_id])
