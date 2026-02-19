import json
import random
from datetime import datetime, timezone

from models import (
    CombatLog, Game, GamePlayer, Order, OrderMaterialSource,
    PlayerTurnStatus, Ship, StarSystem, Structure, Turn, TurnSnapshot,
)
from database import get_game_session


def _get_or_create_ship(game_db, system_id, player_index):
    ship = game_db.query(Ship).filter(
        Ship.system_id == system_id, Ship.player_index == player_index
    ).first()
    if not ship:
        ship = Ship(system_id=system_id, player_index=player_index, count=0)
        game_db.add(ship)
        game_db.flush()
    return ship


def _snap_systems(game_db):
    systems = game_db.query(StarSystem).all()
    return [
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
    ]


def _snap_ships(game_db):
    ships = game_db.query(Ship).filter(Ship.count > 0).all()
    return [
        {
            "ship_id": s.ship_id,
            "system_id": s.system_id,
            "player_index": s.player_index,
            "count": s.count,
        }
        for s in ships
    ]


def _snap_structures(game_db):
    structures = game_db.query(Structure).all()
    return [
        {
            "structure_id": s.structure_id,
            "system_id": s.system_id,
            "player_index": s.player_index,
            "structure_type": s.structure_type,
        }
        for s in structures
    ]


def _snap_orders(orders):
    result = []
    for o in orders:
        d = {
            "order_id": o.order_id,
            "turn_id": o.turn_id,
            "player_index": o.player_index,
            "order_type": o.order_type,
            "source_system_id": o.source_system_id,
            "target_system_id": o.target_system_id,
            "quantity": o.quantity,
        }
        if o.order_type == "build_mine":
            d["material_sources"] = [
                {"system_id": ms.source_system_id, "amount": ms.amount}
                for ms in o.material_sources
            ]
        result.append(d)
    return result


def _save_turn_snapshot(game_db, turn_id, orders):
    snap = TurnSnapshot(
        turn_id=turn_id,
        systems_json=json.dumps(_snap_systems(game_db)),
        ships_json=json.dumps(_snap_ships(game_db)),
        structures_json=json.dumps(_snap_structures(game_db)),
        orders_json=json.dumps(_snap_orders(orders) if orders else []),
    )
    game_db.add(snap)


def resolve_turn(game_id, turn_id, admin_db):
    game_db = get_game_session(game_id)
    try:
        # Fetch all orders for this turn
        orders = game_db.query(Order).filter(Order.turn_id == turn_id).all()

        # Step 1 — Build mines
        for o in orders:
            if o.order_type != "build_mine":
                continue
            game_db.add(Structure(
                system_id=o.source_system_id,
                player_index=o.player_index,
                structure_type="mine",
            ))
            for ms in o.material_sources:
                sys = game_db.query(StarSystem).filter(
                    StarSystem.system_id == ms.source_system_id
                ).first()
                sys.materials -= ms.amount

        # Step 2 — Build shipyards
        for o in orders:
            if o.order_type != "build_shipyard":
                continue
            game_db.add(Structure(
                system_id=o.source_system_id,
                player_index=o.player_index,
                structure_type="shipyard",
            ))
            # Shipyard cost is deducted from the source system directly (no material_sources)
            src = game_db.query(StarSystem).filter(
                StarSystem.system_id == o.source_system_id
            ).first()
            src.materials -= 30

        # Step 3 — Build ships
        for o in orders:
            if o.order_type != "build_ships":
                continue
            # Deduct materials from source system
            src = game_db.query(StarSystem).filter(
                StarSystem.system_id == o.source_system_id
            ).first()
            src.materials -= o.quantity
            ship = _get_or_create_ship(game_db, o.source_system_id, o.player_index)
            ship.count += o.quantity

        # Step 4 — Move ships
        for o in orders:
            if o.order_type != "move_ships":
                continue
            src_ship = _get_or_create_ship(game_db, o.source_system_id, o.player_index)
            src_ship.count -= o.quantity
            tgt_ship = _get_or_create_ship(game_db, o.target_system_id, o.player_index)
            tgt_ship.count += o.quantity

        game_db.flush()

        # Step 5 — Combat
        all_systems = game_db.query(StarSystem).all()
        for sys in all_systems:
            ships_here = game_db.query(Ship).filter(
                Ship.system_id == sys.system_id, Ship.count > 0
            ).all()
            players_present = {s.player_index for s in ships_here}
            if len(players_present) < 2:
                continue

            current = {s.player_index: s.count for s in ships_here}
            round_num = 1
            active = {p for p in current if current[p] > 0}

            while len(active) > 1:
                # Roll hits: each ship has 50% chance to hit
                hits = {}
                for p in active:
                    hits[p] = sum(1 for _ in range(current[p]) if random.random() < 0.5)

                ships_before = {p: current[p] for p in active}

                if len(active) == 2:
                    p0, p1 = list(active)
                    losses = {
                        p0: min(hits[p1], current[p0]),
                        p1: min(hits[p0], current[p1]),
                    }
                else:
                    losses = {p: 0 for p in active}
                    for attacker, h in hits.items():
                        opponents = [p for p in active if p != attacker and current[p] > 0]
                        if not opponents:
                            continue
                        pool = [p for p in opponents for _ in range(current[p])]
                        for _ in range(h):
                            if pool:
                                target = random.choice(pool)
                                losses[target] += 1

                for p in active:
                    current[p] = max(0, current[p] - losses.get(p, 0))

                combatants = [
                    {
                        "player_index": p,
                        "ships_before": ships_before[p],
                        "hits_scored": hits[p],
                        "ships_after": current[p],
                    }
                    for p in active
                ]
                game_db.add(CombatLog(
                    turn_id=turn_id,
                    system_id=sys.system_id,
                    round_number=round_num,
                    description=f"Round {round_num}",
                    combatants_json=json.dumps(combatants),
                ))

                round_num += 1
                active = {p for p in active if current[p] > 0}

            # Update ship rows
            for p, count in current.items():
                ship = _get_or_create_ship(game_db, sys.system_id, p)
                ship.count = count

            # Flush so the DB sees updated counts before the bulk delete
            game_db.flush()

            # Delete zero-count ships
            game_db.query(Ship).filter(
                Ship.system_id == sys.system_id, Ship.count == 0
            ).delete()

        game_db.flush()

        # Step 6 — Ownership changes
        for sys in all_systems:
            ships_here = game_db.query(Ship).filter(
                Ship.system_id == sys.system_id, Ship.count > 0
            ).all()
            players_with_ships = {s.player_index for s in ships_here}
            if len(players_with_ships) == 1:
                new_owner = list(players_with_ships)[0]
                if new_owner != sys.owner_player_index:
                    sys.owner_player_index = new_owner
                    # Transfer structures
                    for struct in game_db.query(Structure).filter(
                        Structure.system_id == sys.system_id
                    ).all():
                        struct.player_index = new_owner

        # Step 7 — Mine production
        for sys in all_systems:
            if sys.owner_player_index is None:
                continue
            mine = game_db.query(Structure).filter(
                Structure.system_id == sys.system_id,
                Structure.structure_type == "mine",
                Structure.player_index == sys.owner_player_index,
            ).first()
            if mine:
                sys.materials += sys.mining_value

        # Step 8 — Save snapshot
        _save_turn_snapshot(game_db, turn_id, orders)

        # Step 9 — Finalize
        turn = game_db.query(Turn).filter(Turn.turn_id == turn_id).first()
        turn.status = "resolved"
        turn.resolved_at = datetime.now(timezone.utc)
        game_db.commit()

        # Create next turn
        next_turn_id = turn_id + 1
        game_db.add(Turn(turn_id=next_turn_id, status="active"))

        # Get player count from admin DB
        game = admin_db.query(Game).filter(Game.game_id == game_id).first()
        player_count = admin_db.query(GamePlayer).filter(
            GamePlayer.game_id == game_id
        ).count()

        for i in range(1, player_count + 1):
            game_db.add(PlayerTurnStatus(
                turn_id=next_turn_id, player_index=i, submitted=False
            ))
        game_db.commit()

        # Update admin DB
        game.current_turn = next_turn_id

        # Victory check
        fw = game_db.query(StarSystem).filter(
            StarSystem.is_founders_world == True
        ).first()
        if fw and fw.owner_player_index is not None and fw.owner_player_index != -1:
            game.status = "completed"
            game.winner_player_index = fw.owner_player_index

        admin_db.commit()
    finally:
        game_db.close()
