import os
import random

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from auth import create_access_token, get_current_user, hash_password, verify_password
from database import Base, create_game_database, engine, get_db, get_game_session
from map_generator import generate_map
from models import Game, GamePlayer, JumpLine, Order, OrderMaterialSource, PlayerTurnStatus, Ship, StarSystem, Structure, Turn, User

app = FastAPI()

PLAYER_COLORS = [
    '#e74c3c', '#3498db', '#2ecc71', '#f39c12',
    '#9b59b6', '#1abc9c', '#e67e22', '#34495e',
]

# Create admin tables (users, games) on startup
Base.metadata.create_all(bind=engine)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "https://spacegame-front-end.onrender.com"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


# --- Auth models ---

class RegisterRequest(BaseModel):
    username: str
    first_name: str
    last_name: str
    email: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


# --- Auth endpoints ---

@app.post("/auth/register")
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == req.username).first():
        raise HTTPException(status_code=400, detail="Username already taken")
    if db.query(User).filter(User.email == req.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        username=req.username,
        first_name=req.first_name,
        last_name=req.last_name,
        email=req.email,
        password=hash_password(req.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token({"sub": str(user.user_id)})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "user_id": user.user_id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
        },
    }


@app.post("/auth/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username).first()
    if not user or not verify_password(req.password, user.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")

    token = create_access_token({"sub": str(user.user_id)})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "user_id": user.user_id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
        },
    }


@app.get("/auth/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "user_id": current_user.user_id,
        "username": current_user.username,
        "first_name": current_user.first_name,
        "last_name": current_user.last_name,
        "email": current_user.email,
    }


# --- Existing endpoints ---

@app.get("/random")
def get_random_number():
    return {"number": random.randint(1, 100)}


@app.get("/db-health")
def db_health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "connected"}


@app.get("/users")
def get_users(db: Session = Depends(get_db)):
    users = db.query(User).all()
    return [
        {
            "user_id": u.user_id,
            "username": u.username,
            "first_name": u.first_name,
            "last_name": u.last_name,
            "email": u.email,
        }
        for u in users
    ]


# --- Game endpoints ---

class CreateGameRequest(BaseModel):
    name: str
    num_players: int


class GenerateMapRequest(BaseModel):
    seed: int | None = None


def _save_map_to_game_db(game_id: int, map_data: dict, num_players: int):
    """Save generated map data (systems + jump lines) to a game's database,
    then initialize starting ships, structures, and Turn 1."""
    game_db = get_game_session(game_id)
    try:
        game_db.query(JumpLine).delete()
        game_db.query(Ship).delete()
        game_db.query(Structure).delete()
        game_db.query(Turn).delete()
        game_db.query(StarSystem).delete()

        gen_id_to_db_id = {}
        for sys_data in map_data["systems"]:
            system = StarSystem(
                name=sys_data["name"],
                x=sys_data["x"],
                y=sys_data["y"],
                mining_value=sys_data["mining_value"],
                materials=sys_data["materials"],
                cluster_id=sys_data["cluster_id"],
                is_home_system=sys_data["is_home_system"],
                is_founders_world=sys_data["is_founders_world"],
                owner_player_index=sys_data["owner_player_index"],
            )
            game_db.add(system)
            game_db.flush()
            gen_id_to_db_id[sys_data["id"]] = system.system_id

        for jl_data in map_data["jump_lines"]:
            jump = JumpLine(
                from_system_id=gen_id_to_db_id[jl_data["from_id"]],
                to_system_id=gen_id_to_db_id[jl_data["to_id"]],
            )
            game_db.add(jump)

        # Initialize starting pieces on home systems and Founder's World
        for sys_data in map_data["systems"]:
            db_id = gen_id_to_db_id[sys_data["id"]]
            if sys_data["is_home_system"] and sys_data["owner_player_index"] is not None:
                pi = sys_data["owner_player_index"]
                game_db.add(Ship(system_id=db_id, player_index=pi, count=1))
                game_db.add(Structure(system_id=db_id, player_index=pi, structure_type="mine"))
                game_db.add(Structure(system_id=db_id, player_index=pi, structure_type="shipyard"))
            elif sys_data["is_founders_world"]:
                game_db.add(Ship(system_id=db_id, player_index=-1, count=300))

        # Create Turn 1
        game_db.add(Turn(turn_id=1, status="active"))

        # Create PlayerTurnStatus for each player
        for pi in range(1, num_players + 1):
            game_db.add(PlayerTurnStatus(turn_id=1, player_index=pi, submitted=False))

        game_db.commit()
    finally:
        game_db.close()


def _generate_and_save_map(game: Game, db: Session):
    """Generate map with random seed, save to game DB, set status to active."""
    seed = random.randint(0, 2**31)
    map_data = generate_map(game.num_players, seed=seed)
    _save_map_to_game_db(game.game_id, map_data, game.num_players)
    game.seed = seed
    game.status = "active"
    game.current_turn = 1
    db.commit()


@app.post("/games")
def create_game(req: CreateGameRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if req.num_players < 2 or req.num_players > 8:
        raise HTTPException(status_code=400, detail="num_players must be between 2 and 8")

    game = Game(name=req.name, num_players=req.num_players, status="open", creator_id=current_user.user_id)
    db.add(game)
    db.commit()
    db.refresh(game)

    # Create per-game database
    db_name = create_game_database(game.game_id)
    game.db_name = db_name
    db.commit()

    # Auto-join creator as player 1
    player = GamePlayer(game_id=game.game_id, user_id=current_user.user_id, player_index=1)
    db.add(player)
    db.commit()

    return {
        "game_id": game.game_id,
        "name": game.name,
        "num_players": game.num_players,
        "status": game.status,
        "player_count": 1,
        "creator_id": game.creator_id,
    }


@app.get("/games")
def list_games(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    games = db.query(Game).all()
    result = []
    for g in games:
        player_count = db.query(GamePlayer).filter(GamePlayer.game_id == g.game_id).count()
        is_member = db.query(GamePlayer).filter(
            GamePlayer.game_id == g.game_id, GamePlayer.user_id == current_user.user_id
        ).first() is not None
        creator_username = g.creator.username if g.creator else None
        result.append({
            "game_id": g.game_id,
            "name": g.name,
            "num_players": g.num_players,
            "player_count": player_count,
            "status": g.status,
            "creator_username": creator_username,
            "created_at": g.created_at.isoformat() if g.created_at else None,
            "is_member": is_member,
        })
    return result


@app.get("/games/{game_id}/players")
def get_game_players(game_id: int, db: Session = Depends(get_db)):
    game = db.query(Game).filter(Game.game_id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    players = (
        db.query(GamePlayer, User)
        .join(User, GamePlayer.user_id == User.user_id)
        .filter(GamePlayer.game_id == game_id)
        .order_by(GamePlayer.player_index)
        .all()
    )
    return [
        {"player_index": gp.player_index, "username": u.username}
        for gp, u in players
    ]


@app.post("/games/{game_id}/join")
def join_game(game_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    game = db.query(Game).filter(Game.game_id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    if game.status != "open":
        raise HTTPException(status_code=400, detail="Game is not open for joining")

    existing = db.query(GamePlayer).filter(
        GamePlayer.game_id == game_id, GamePlayer.user_id == current_user.user_id
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="Already joined this game")

    player_count = db.query(GamePlayer).filter(GamePlayer.game_id == game_id).count()
    if player_count >= game.num_players:
        raise HTTPException(status_code=400, detail="Game is full")

    next_index = player_count + 1
    player = GamePlayer(game_id=game_id, user_id=current_user.user_id, player_index=next_index)
    db.add(player)
    db.commit()

    # Check if game is now full — auto-generate map
    new_count = db.query(GamePlayer).filter(GamePlayer.game_id == game_id).count()
    if new_count >= game.num_players:
        _generate_and_save_map(game, db)

    return {"game_id": game_id, "player_index": next_index, "status": game.status}


def _is_dev_mode() -> bool:
    """Check if we're running in dev mode based on the database URL."""
    base_url = os.environ.get("postgresDB", "")
    return "localhost" in base_url or "127.0.0.1" in base_url


@app.post("/games/express-start")
def express_start(req: CreateGameRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if not _is_dev_mode():
        raise HTTPException(status_code=403, detail="Express start is only available in dev mode")
    if req.num_players < 2 or req.num_players > 8:
        raise HTTPException(status_code=400, detail="num_players must be between 2 and 8")

    # Create game
    game = Game(name=req.name, num_players=req.num_players, status="open", creator_id=current_user.user_id)
    db.add(game)
    db.commit()
    db.refresh(game)

    db_name = create_game_database(game.game_id)
    game.db_name = db_name
    db.commit()

    # Add creator as player 1
    db.add(GamePlayer(game_id=game.game_id, user_id=current_user.user_id, player_index=1))
    db.commit()

    # Fill remaining slots with test_user accounts
    test_users = db.query(User).filter(User.username.like("test_user%")).order_by(User.user_id).all()
    needed = req.num_players - 1
    if len(test_users) < needed:
        raise HTTPException(status_code=400, detail=f"Need {needed} test_user accounts but only found {len(test_users)}")

    for i, tu in enumerate(test_users[:needed]):
        db.add(GamePlayer(game_id=game.game_id, user_id=tu.user_id, player_index=i + 2))
    db.commit()

    # Generate map and set active
    _generate_and_save_map(game, db)

    return {"game_id": game.game_id, "name": game.name, "status": game.status, "num_players": game.num_players}


@app.post("/games/{game_id}/generate-map")
def generate_game_map(game_id: int, req: GenerateMapRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    game = db.query(Game).filter(Game.game_id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    seed = req.seed if req.seed is not None else random.randint(0, 2**31)
    map_data = generate_map(game.num_players, seed=seed)

    game.seed = seed
    game.status = "map_generated"
    db.commit()

    _save_map_to_game_db(game_id, map_data, game.num_players)

    return {"status": "generated", "seed": seed, "num_systems": len(map_data["systems"])}


@app.get("/games/{game_id}/map")
def get_game_map(game_id: int, db: Session = Depends(get_db)):
    game = db.query(Game).filter(Game.game_id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    # Get a session to the game's database
    game_db = get_game_session(game_id)
    try:
        systems = game_db.query(StarSystem).all()
        if not systems:
            raise HTTPException(status_code=404, detail="Map not generated yet")

        jump_lines = game_db.query(JumpLine).all()
        ships = game_db.query(Ship).all()
        structures = game_db.query(Structure).all()

        # Build players array from admin DB
        player_rows = (
            db.query(GamePlayer, User)
            .join(User, GamePlayer.user_id == User.user_id)
            .filter(GamePlayer.game_id == game_id)
            .order_by(GamePlayer.player_index)
            .all()
        )

        # Find home system names for each player
        home_systems = {s.owner_player_index: s.name for s in systems if s.is_home_system}

        players = [
            {
                "player_index": gp.player_index,
                "username": u.username,
                "color": PLAYER_COLORS[gp.player_index % len(PLAYER_COLORS)],
                "home_system_name": home_systems.get(gp.player_index),
            }
            for gp, u in player_rows
        ]

        return {
            "game_id": game_id,
            "game_name": game.name,
            "num_players": game.num_players,
            "seed": game.seed,
            "status": game.status,
            "current_turn": game.current_turn,
            "systems": [
                {
                    "system_id": s.system_id,
                    "name": s.name,
                    "x": s.x,
                    "y": s.y,
                    "mining_value": s.mining_value,
                    "materials": s.materials,
                    "cluster_id": s.cluster_id,
                    "is_home_system": s.is_home_system,
                    "is_founders_world": s.is_founders_world,
                    "owner_player_index": s.owner_player_index,
                }
                for s in systems
            ],
            "jump_lines": [
                {
                    "jump_line_id": jl.jump_line_id,
                    "from_system_id": jl.from_system_id,
                    "to_system_id": jl.to_system_id,
                }
                for jl in jump_lines
            ],
            "ships": [
                {
                    "ship_id": sh.ship_id,
                    "system_id": sh.system_id,
                    "player_index": sh.player_index,
                    "count": sh.count,
                }
                for sh in ships
            ],
            "structures": [
                {
                    "structure_id": st.structure_id,
                    "system_id": st.system_id,
                    "player_index": st.player_index,
                    "structure_type": st.structure_type,
                }
                for st in structures
            ],
            "players": players,
        }
    finally:
        game_db.close()


def _get_player_index(game_id: int, user_id: int, db: Session) -> int:
    """Look up the player_index for a user in a game. Raises 403 if not a member."""
    gp = db.query(GamePlayer).filter(
        GamePlayer.game_id == game_id, GamePlayer.user_id == user_id
    ).first()
    if not gp:
        raise HTTPException(status_code=403, detail="You are not a player in this game")
    return gp.player_index


@app.get("/games/{game_id}/turns/{turn_id}/status")
def get_turn_status(game_id: int, turn_id: int, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    game = db.query(Game).filter(Game.game_id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    game_db = get_game_session(game_id)
    try:
        statuses = game_db.query(PlayerTurnStatus).filter(
            PlayerTurnStatus.turn_id == turn_id
        ).order_by(PlayerTurnStatus.player_index).all()

        # Build username lookup from admin DB
        player_rows = (
            db.query(GamePlayer, User)
            .join(User, GamePlayer.user_id == User.user_id)
            .filter(GamePlayer.game_id == game_id)
            .all()
        )
        username_map = {gp.player_index: u.username for gp, u in player_rows}

        return [
            {
                "player_index": s.player_index,
                "username": username_map.get(s.player_index, f"Player {s.player_index}"),
                "submitted": s.submitted,
            }
            for s in statuses
        ]
    finally:
        game_db.close()
