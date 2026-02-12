import random

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from database import Base, create_game_database, engine, get_db, get_game_session
from map_generator import generate_map
from models import Game, JumpLine, StarSystem, User

app = FastAPI()

# Create admin tables (users, games) on startup
Base.metadata.create_all(bind=engine)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "https://spacegame-front-end.onrender.com"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


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


@app.post("/games")
def create_game(req: CreateGameRequest, db: Session = Depends(get_db)):
    game = Game(name=req.name, num_players=req.num_players)
    db.add(game)
    db.commit()
    db.refresh(game)

    # Create per-game database
    db_name = create_game_database(game.game_id)
    game.db_name = db_name
    db.commit()

    return {"game_id": game.game_id, "name": game.name, "num_players": game.num_players}


@app.post("/games/{game_id}/generate-map")
def generate_game_map(game_id: int, req: GenerateMapRequest, db: Session = Depends(get_db)):
    game = db.query(Game).filter(Game.game_id == game_id).first()
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    # Get a session to the game's database
    game_db = get_game_session(game_id)
    try:
        # Clear any existing map data
        game_db.query(JumpLine).delete()
        game_db.query(StarSystem).delete()

        # Generate map
        seed = req.seed if req.seed is not None else random.randint(0, 2**31)
        map_data = generate_map(game.num_players, seed=seed)

        # Store seed on game record (in admin DB)
        game.seed = seed
        game.status = "map_generated"
        db.commit()

        # Save systems (map generator IDs to DB IDs)
        gen_id_to_db_id = {}
        for sys_data in map_data["systems"]:
            system = StarSystem(
                name=sys_data["name"],
                x=sys_data["x"],
                y=sys_data["y"],
                mining_value=sys_data["mining_value"],
                cluster_id=sys_data["cluster_id"],
                is_home_system=sys_data["is_home_system"],
                is_founders_world=sys_data["is_founders_world"],
                owner_player_index=sys_data["owner_player_index"],
            )
            game_db.add(system)
            game_db.flush()  # Get the DB-assigned ID
            gen_id_to_db_id[sys_data["id"]] = system.system_id

        # Save jump lines
        for jl_data in map_data["jump_lines"]:
            jump = JumpLine(
                from_system_id=gen_id_to_db_id[jl_data["from_id"]],
                to_system_id=gen_id_to_db_id[jl_data["to_id"]],
            )
            game_db.add(jump)

        game_db.commit()
    finally:
        game_db.close()

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

        return {
            "game_id": game_id,
            "game_name": game.name,
            "num_players": game.num_players,
            "seed": game.seed,
            "systems": [
                {
                    "system_id": s.system_id,
                    "name": s.name,
                    "x": s.x,
                    "y": s.y,
                    "mining_value": s.mining_value,
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
        }
    finally:
        game_db.close()
