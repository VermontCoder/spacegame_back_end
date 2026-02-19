from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text, func
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
    status = Column(String(20), nullable=False, default="open")
    seed = Column(Integer, nullable=True)
    db_name = Column(String(100), nullable=True)
    creator_id = Column(Integer, ForeignKey("users.user_id"), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    current_turn = Column(Integer, nullable=True)
    winner_player_index = Column(Integer, nullable=True)

    creator = relationship("User", backref="games")
    players = relationship("GamePlayer", back_populates="game")


class GamePlayer(Base):
    __tablename__ = "game_players"

    game_player_id = Column(Integer, primary_key=True, autoincrement=True)
    game_id = Column(Integer, ForeignKey("games.game_id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    player_index = Column(Integer, nullable=False)
    joined_at = Column(DateTime, server_default=func.now())

    game = relationship("Game", back_populates="players")
    user = relationship("User", backref="game_memberships")


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


class Ship(GameBase):
    __tablename__ = "ships"

    ship_id = Column(Integer, primary_key=True, autoincrement=True)
    system_id = Column(Integer, ForeignKey("star_systems.system_id"), nullable=False)
    player_index = Column(Integer, nullable=False)  # -1 = neutral (Founder's World)
    count = Column(Integer, nullable=False, default=0)

    system = relationship("StarSystem", backref="ships")


class Structure(GameBase):
    __tablename__ = "structures"

    structure_id = Column(Integer, primary_key=True, autoincrement=True)
    system_id = Column(Integer, ForeignKey("star_systems.system_id"), nullable=False)
    player_index = Column(Integer, nullable=False)
    structure_type = Column(String(20), nullable=False)  # "mine" or "shipyard"

    system = relationship("StarSystem", backref="structures")


class Turn(GameBase):
    __tablename__ = "turns"

    turn_id = Column(Integer, primary_key=True)  # 1-based, not autoincrement
    status = Column(String(20), nullable=False, default="active")  # "active" or "resolved"
    resolved_at = Column(DateTime, nullable=True)


class Order(GameBase):
    __tablename__ = "orders"

    order_id = Column(Integer, primary_key=True, autoincrement=True)
    turn_id = Column(Integer, nullable=False)
    player_index = Column(Integer, nullable=False)
    order_type = Column(String(20), nullable=False)
    source_system_id = Column(Integer, ForeignKey("star_systems.system_id"), nullable=False)
    target_system_id = Column(Integer, ForeignKey("star_systems.system_id"), nullable=True)
    quantity = Column(Integer, nullable=True)

    source_system = relationship("StarSystem", foreign_keys=[source_system_id])
    target_system = relationship("StarSystem", foreign_keys=[target_system_id])
    material_sources = relationship("OrderMaterialSource", back_populates="order", cascade="all, delete-orphan")


class OrderMaterialSource(GameBase):
    __tablename__ = "order_material_sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(Integer, ForeignKey("orders.order_id"), nullable=False)
    source_system_id = Column(Integer, ForeignKey("star_systems.system_id"), nullable=False)
    amount = Column(Integer, nullable=False)

    order = relationship("Order", back_populates="material_sources")
    source_system = relationship("StarSystem")


class PlayerTurnStatus(GameBase):
    __tablename__ = "player_turn_status"

    id = Column(Integer, primary_key=True, autoincrement=True)
    turn_id = Column(Integer, nullable=False)
    player_index = Column(Integer, nullable=False)
    submitted = Column(Boolean, nullable=False, default=False)
    submitted_at = Column(DateTime, nullable=True)


class CombatLog(GameBase):
    __tablename__ = "combat_logs"

    log_id = Column(Integer, primary_key=True, autoincrement=True)
    turn_id = Column(Integer, nullable=False, index=True)
    system_id = Column(Integer, ForeignKey("star_systems.system_id"), nullable=False)
    round_number = Column(Integer, nullable=False)
    description = Column(Text, nullable=False)
    combatants_json = Column(Text, nullable=False)


class TurnSnapshot(GameBase):
    __tablename__ = "turn_snapshots"

    snapshot_id = Column(Integer, primary_key=True, autoincrement=True)
    turn_id = Column(Integer, nullable=False, unique=True)
    systems_json = Column(Text, nullable=False)
    ships_json = Column(Text, nullable=False)
    structures_json = Column(Text, nullable=False)
    orders_json = Column(Text, nullable=False)
