import math
import random

import networkx as nx


STAR_NAMES = [
    "Sol", "Alpha Centauri", "Sirius", "Vega", "Arcturus", "Rigel",
    "Betelgeuse", "Procyon", "Altair", "Deneb", "Polaris", "Capella",
    "Aldebaran", "Antares", "Spica", "Regulus", "Castor", "Pollux",
    "Fomalhaut", "Canopus", "Achernar", "Bellatrix", "Elnath", "Mintaka",
    "Alnitak", "Alnilam", "Saiph", "Mira", "Rasalhague", "Kochab",
    "Dubhe", "Merak", "Phecda", "Megrez", "Alioth", "Alkaid", "Thuban",
    "Etamin", "Rastaban", "Alderamin", "Schedar", "Caph", "Mirfak",
    "Algol", "Hamal", "Sheratan", "Menkar", "Zaurak", "Rana", "Cursa",
    "Arneb", "Nihal", "Wezen", "Aludra", "Furud", "Mirzam", "Naos",
    "Regor", "Avior", "Aspidiske", "Miaplacidus", "Atria", "Peacock",
    "Alnair", "Ankaa", "Diphda", "Markab", "Algenib", "Enif", "Biham",
    "Sadalmelik", "Sadalsuud", "Skat", "Nashira", "Dabih", "Algedi",
    "Nunki", "Kaus Australis", "Sargas", "Shaula", "Lesath", "Graffias",
    "Dschubba", "Zubenelgenubi", "Zubeneschamali", "Unukalhai", "Kornephoros",
    "Yed Prior", "Sabik", "Cebalrai", "Marfik", "Tarazed", "Sadr",
    "Gienah", "Albireo", "Sualocin", "Rotanev", "Alphecca", "Gemma",
]


def _roll_mining_value(rng: random.Random) -> int:
    """Roll 2d6-2 for mining value (range 0-10)."""
    return rng.randint(1, 6) + rng.randint(1, 6) - 2


def _build_clusters(num_players: int, rng: random.Random) -> list[dict]:
    """Create player home clusters and neutral clusters."""
    clusters = []
    for i in range(num_players):
        clusters.append({
            "id": i,
            "is_home_cluster": True,
            "player_index": i + 1,
            "system_ids": [],
        })
    num_neutral = max(1, rng.randint(1, max(1, num_players // 2 + 1)))
    for i in range(num_neutral):
        clusters.append({
            "id": num_players + i,
            "is_home_cluster": False,
            "player_index": None,
            "system_ids": [],
        })
    return clusters


def _distribute_systems(
    num_systems: int, clusters: list[dict], rng: random.Random
) -> None:
    """Assign system IDs to clusters. System 0 is Founder's World (no cluster).
    Mutates clusters in place, adding IDs to system_ids lists."""
    player_clusters = [c for c in clusters if c["is_home_cluster"]]
    neutral_clusters = [c for c in clusters if not c["is_home_cluster"]]
    min_per_player = 3
    min_per_neutral = 1

    next_id = 1  # 0 is Founder's World
    for cluster in player_clusters:
        for _ in range(min_per_player):
            cluster["system_ids"].append(next_id)
            next_id += 1
    for cluster in neutral_clusters:
        for _ in range(min_per_neutral):
            cluster["system_ids"].append(next_id)
            next_id += 1

    reserved = 1 + (min_per_player * len(player_clusters)) + (min_per_neutral * len(neutral_clusters))
    remaining = num_systems - reserved
    for _ in range(max(0, remaining)):
        cluster = rng.choice(clusters)
        cluster["system_ids"].append(next_id)
        next_id += 1


def _build_graph(clusters: list[dict], rng: random.Random) -> nx.Graph:
    """Build a connected graph respecting the 1-4 degree constraint."""
    G = nx.Graph()
    G.add_node(0)  # Founder's World

    for cluster in clusters:
        for sid in cluster["system_ids"]:
            G.add_node(sid)

    # Intra-cluster edges (spanning tree + extras)
    for cluster in clusters:
        ids = list(cluster["system_ids"])
        if len(ids) < 2:
            continue
        rng.shuffle(ids)
        for i in range(1, len(ids)):
            G.add_edge(ids[i - 1], ids[i], weight=1.0)
        # Add 1-2 extra intra-cluster edges where degree allows
        max_extra = min(2, len(ids) * (len(ids) - 1) // 2 - (len(ids) - 1))
        for _ in range(max(0, max_extra)):
            candidates = [
                (a, b) for a in ids for b in ids
                if a < b and not G.has_edge(a, b)
                and G.degree(a) < 4 and G.degree(b) < 4
            ]
            if not candidates:
                break
            a, b = rng.choice(candidates)
            G.add_edge(a, b, weight=1.0)

    # Inter-cluster edges: player clusters form a ring, neutral clusters bridge adjacent pairs
    player_cluster_list = [c for c in clusters if c["is_home_cluster"]]
    neutral_cluster_list = [c for c in clusters if not c["is_home_cluster"]]
    rng.shuffle(player_cluster_list)
    n_players = len(player_cluster_list)

    # Connect player clusters in a ring
    for i in range(n_players):
        c1 = player_cluster_list[i]
        c2 = player_cluster_list[(i + 1) % n_players]
        candidates_1 = [s for s in c1["system_ids"] if G.degree(s) < 4]
        candidates_2 = [s for s in c2["system_ids"] if G.degree(s) < 4]
        if candidates_1 and candidates_2:
            a = rng.choice(candidates_1)
            b = rng.choice(candidates_2)
            G.add_edge(a, b, weight=1.0)

    # Assign each neutral cluster to bridge two adjacent player clusters in the ring
    for i, neutral in enumerate(neutral_cluster_list):
        pc1 = player_cluster_list[i % n_players]
        pc2 = player_cluster_list[(i + 1) % n_players]
        neutral["bridge_pair"] = (pc1["id"], pc2["id"])
        for pc in [pc1, pc2]:
            nc_candidates = [s for s in neutral["system_ids"] if G.degree(s) < 4]
            pc_candidates = [s for s in pc["system_ids"] if G.degree(s) < 4]
            if nc_candidates and pc_candidates:
                a = rng.choice(nc_candidates)
                b = rng.choice(pc_candidates)
                if not G.has_edge(a, b):
                    G.add_edge(a, b, weight=1.0)

    # Connect Founder's World to one system per cluster (up to degree 4)
    for cluster in clusters:
        if G.degree(0) >= 4:
            break
        candidates = [s for s in cluster["system_ids"] if G.degree(s) < 4]
        if candidates:
            target = rng.choice(candidates)
            G.add_edge(0, target, weight=1.0)

    # If Founder's World has no connections yet, force at least one
    if G.degree(0) == 0:
        all_systems = [n for n in G.nodes if n != 0 and G.degree(n) < 4]
        if all_systems:
            G.add_edge(0, rng.choice(all_systems), weight=1.0)

    # Ensure global connectivity — add bridges if needed
    components = list(nx.connected_components(G))
    while len(components) > 1:
        comp_a = components[0]
        comp_b = components[1]
        candidates_a = [n for n in comp_a if G.degree(n) < 4]
        candidates_b = [n for n in comp_b if G.degree(n) < 4]
        if candidates_a and candidates_b:
            a = rng.choice(candidates_a)
            b = rng.choice(candidates_b)
            G.add_edge(a, b, weight=1.0)
        else:
            # Fallback: allow degree 5 temporarily to ensure connectivity
            a = rng.choice(list(comp_a))
            b = rng.choice(list(comp_b))
            G.add_edge(a, b, weight=1.0)
        components = list(nx.connected_components(G))

    return G


def _ensure_safe_paths(
    G: nx.Graph, clusters: list[dict], rng: random.Random
) -> None:
    """Ensure every player can reach Founder's World (node 0) without
    passing through another player's home cluster. Adds jump lines as needed."""
    # Build system -> owner lookup (None = neutral/FW)
    system_owner: dict[int, int | None] = {0: None}
    for cluster in clusters:
        owner = cluster["player_index"] if cluster["is_home_cluster"] else None
        for sid in cluster["system_ids"]:
            system_owner[sid] = owner

    # Identify home system for each player (first system in their cluster)
    player_home: dict[int, int] = {}
    for cluster in clusters:
        if cluster["is_home_cluster"] and cluster["system_ids"]:
            player_home[cluster["player_index"]] = cluster["system_ids"][0]

    for player_idx, home_id in player_home.items():
        # Safe nodes: own cluster + neutral clusters + Founder's World
        safe_nodes = {
            sid for sid, owner in system_owner.items()
            if owner is None or owner == player_idx
        }
        safe_sub = G.subgraph(safe_nodes)

        if nx.has_path(safe_sub, home_id, 0):
            continue  # Already has a safe path

        # Find which safe nodes are reachable from the player's home
        player_reachable = nx.node_connected_component(safe_sub, home_id)
        # Find which safe nodes are reachable from Founder's World
        fw_reachable = nx.node_connected_component(safe_sub, 0)

        # Add a jump line bridging player's reachable safe nodes to FW's reachable safe nodes
        candidates = [
            (a, b)
            for a in player_reachable
            for b in fw_reachable
            if G.degree(a) < 4 and G.degree(b) < 4 and not G.has_edge(a, b)
        ]
        if candidates:
            a, b = min(candidates, key=lambda pair: (G.degree(pair[0]) + G.degree(pair[1])))
            G.add_edge(a, b, weight=1.0)
        else:
            # Fallback: allow exceeding degree constraint to guarantee safe path
            for a in player_reachable:
                for b in fw_reachable:
                    if not G.has_edge(a, b):
                        G.add_edge(a, b, weight=1.0)
                        break
                else:
                    continue
                break


def _compute_layout(
    G: nx.Graph, clusters: list[dict], rng: random.Random
) -> dict[int, tuple[float, float]]:
    """Force-directed layout with cluster bias. Returns {node_id: (x, y)}."""
    # Place cluster centers: player clusters on outer ring, neutral on inner ring
    player_clusters = [c for c in clusters if c["is_home_cluster"]]
    neutral_clusters = [c for c in clusters if not c["is_home_cluster"]]

    cluster_centers = {}
    for i, cluster in enumerate(player_clusters):
        angle = 2 * math.pi * i / len(player_clusters)
        cx = 0.5 + 0.2 * math.cos(angle)
        cy = 0.5 + 0.2 * math.sin(angle)
        cluster_centers[cluster["id"]] = (cx, cy)

    for i, cluster in enumerate(neutral_clusters):
        if "bridge_pair" in cluster:
            pc1_id, pc2_id = cluster["bridge_pair"]
            cx1, cy1 = cluster_centers[pc1_id]
            cx2, cy2 = cluster_centers[pc2_id]
            cx = (cx1 + cx2) / 2
            cy = (cy1 + cy2) / 2
        else:
            angle = 2 * math.pi * i / max(1, len(neutral_clusters)) + math.pi / 6
            cx = 0.5 + 0.15 * math.cos(angle)
            cy = 0.5 + 0.15 * math.sin(angle)
        cluster_centers[cluster["id"]] = (cx, cy)

    # Initial positions: systems near their cluster center + jitter
    initial_pos = {0: (0.5, 0.5)}  # Founder's World at center
    for cluster in clusters:
        cx, cy = cluster_centers[cluster["id"]]
        for sid in cluster["system_ids"]:
            jx = rng.uniform(-0.05, 0.05)
            jy = rng.uniform(-0.05, 0.05)
            initial_pos[sid] = (cx + jx, cy + jy)

    # Run force-directed layout with Founder's World pinned at center
    pos = nx.spring_layout(
        G,
        pos=initial_pos,
        fixed=[0],
        iterations=150,
        seed=rng.randint(0, 2**31),
        k=0.5 / math.sqrt(G.number_of_nodes()),
    )

    # Scale to 0-1600 x 0-1200 with padding
    padding = 80
    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    range_x = max_x - min_x or 1
    range_y = max_y - min_y or 1

    scaled = {}
    for node_id, (x, y) in pos.items():
        sx = padding + (x - min_x) / range_x * (1600 - 2 * padding)
        sy = padding + (y - min_y) / range_y * (1200 - 2 * padding)
        scaled[node_id] = (round(float(sx), 2), round(float(sy), 2))

    return scaled


def _assign_names(num_systems: int, rng: random.Random) -> list[str]:
    """Generate unique star names. Uses real names, falls back to generated."""
    names = list(STAR_NAMES)
    rng.shuffle(names)
    # Founder's World gets index 0
    result = ["Founder's World"]
    for i in range(1, num_systems):
        if i - 1 < len(names):
            result.append(names[i - 1])
        else:
            result.append(f"System {i}")
    return result


def generate_map(num_players: int, seed: int = None) -> dict:
    """Generate a complete game map.

    Args:
        num_players: Number of players (2-8).
        seed: Random seed for reproducibility. None for random.

    Returns:
        Dict with keys: systems, jump_lines, clusters.
    """
    rng = random.Random(seed)

    num_systems = rng.randint(4 * num_players, 7 * num_players) + 1  # +1 for Founder's World
    clusters = _build_clusters(num_players, rng)
    _distribute_systems(num_systems, clusters, rng)

    G = _build_graph(clusters, rng)
    _ensure_safe_paths(G, clusters, rng)
    positions = _compute_layout(G, clusters, rng)
    names = _assign_names(num_systems, rng)

    # Build system-to-cluster lookup
    system_cluster = {0: -1}
    for cluster in clusters:
        for sid in cluster["system_ids"]:
            system_cluster[sid] = cluster["id"]

    # Determine home systems (first system in each player cluster)
    home_system_ids = set()
    for cluster in clusters:
        if cluster["is_home_cluster"] and cluster["system_ids"]:
            home_system_ids.add(cluster["system_ids"][0])

    # Assign mining values
    mining_values = {}
    for node_id in G.nodes:
        if node_id == 0:
            mining_values[node_id] = 5  # Founder's World
        elif node_id in home_system_ids:
            mining_values[node_id] = 5
        else:
            mining_values[node_id] = _roll_mining_value(rng)

    # Assemble systems list
    systems = []
    for node_id in sorted(G.nodes):
        x, y = positions[node_id]
        is_home = node_id in home_system_ids
        is_founders = node_id == 0
        cluster_id = system_cluster[node_id]

        # Determine owner for home systems
        owner = None
        if is_home:
            for cluster in clusters:
                if cluster["is_home_cluster"] and node_id in cluster["system_ids"]:
                    owner = cluster["player_index"]
                    break

        systems.append({
            "id": node_id,
            "name": names[node_id],
            "x": x,
            "y": y,
            "mining_value": mining_values[node_id],
            "materials": 0,
            "cluster_id": cluster_id,
            "is_home_system": is_home,
            "is_founders_world": is_founders,
            "owner_player_index": owner,
        })

    # Assemble jump lines
    jump_lines = []
    for u, v in G.edges:
        jump_lines.append({"from_id": min(u, v), "to_id": max(u, v)})
    jump_lines.sort(key=lambda jl: (jl["from_id"], jl["to_id"]))

    # Assemble cluster info
    cluster_info = []
    for cluster in clusters:
        cluster_info.append({
            "id": cluster["id"],
            "is_home_cluster": cluster["is_home_cluster"],
            "player_index": cluster["player_index"],
            "system_ids": sorted(cluster["system_ids"]),
        })

    return {
        "systems": systems,
        "jump_lines": jump_lines,
        "clusters": cluster_info,
    }
