import networkx as nx
from map_generator import generate_map


def test_system_count_in_range():
    """Number of systems should be 4-7x number of players."""
    for num_players in [2, 4, 6]:
        result = generate_map(num_players, seed=42)
        systems = result["systems"]
        # +1 for Founder's World
        min_count = 4 * num_players + 1
        max_count = 7 * num_players + 1
        assert min_count <= len(systems) <= max_count, (
            f"Expected {min_count}-{max_count} systems for {num_players} players, "
            f"got {len(systems)}"
        )


def test_graph_is_connected():
    """All systems must be reachable from any other system."""
    result = generate_map(4, seed=42)
    G = nx.Graph()
    for s in result["systems"]:
        G.add_node(s["id"])
    for jl in result["jump_lines"]:
        G.add_edge(jl["from_id"], jl["to_id"])
    assert nx.is_connected(G), "Map graph is not connected"


def test_degree_constraint():
    """Each system must have 1-4 jump lines."""
    result = generate_map(4, seed=42)
    G = nx.Graph()
    for s in result["systems"]:
        G.add_node(s["id"])
    for jl in result["jump_lines"]:
        G.add_edge(jl["from_id"], jl["to_id"])
    for node in G.nodes:
        degree = G.degree(node)
        assert 1 <= degree <= 4, (
            f"System {node} has degree {degree}, expected 1-4"
        )


def test_founders_world_exists():
    """Exactly one Founder's World at center."""
    result = generate_map(4, seed=42)
    founders = [s for s in result["systems"] if s["is_founders_world"]]
    assert len(founders) == 1


def test_home_systems_count():
    """One home system per player."""
    for num_players in [2, 4, 6]:
        result = generate_map(num_players, seed=42)
        homes = [s for s in result["systems"] if s["is_home_system"]]
        assert len(homes) == num_players


def test_home_systems_mining_value():
    """Home systems always have mining value 5."""
    result = generate_map(4, seed=42)
    for s in result["systems"]:
        if s["is_home_system"]:
            assert s["mining_value"] == 5


def test_mining_values_in_range():
    """Mining values should be 0-10 (2d6-2)."""
    result = generate_map(4, seed=42)
    for s in result["systems"]:
        assert 0 <= s["mining_value"] <= 10


def test_clusters_exist():
    """Should have player clusters + neutral clusters."""
    result = generate_map(4, seed=42)
    clusters = result["clusters"]
    player_clusters = [c for c in clusters if c["is_home_cluster"]]
    neutral_clusters = [c for c in clusters if not c["is_home_cluster"]]
    assert len(player_clusters) == 4
    assert len(neutral_clusters) >= 1


def test_all_systems_have_positions():
    """Every system must have x and y coordinates."""
    result = generate_map(4, seed=42)
    for s in result["systems"]:
        assert "x" in s and "y" in s
        assert isinstance(s["x"], float)
        assert isinstance(s["y"], float)


def test_safe_path_to_founders_world():
    """Every player must be able to reach Founder's World without passing
    through another player's home cluster."""
    for num_players in [2, 4, 6, 8]:
        for seed in [1, 42, 99, 777]:
            result = generate_map(num_players, seed=seed)
            G = nx.Graph()
            for s in result["systems"]:
                G.add_node(s["id"])
            for jl in result["jump_lines"]:
                G.add_edge(jl["from_id"], jl["to_id"])

            # Build cluster ownership lookup: system_id -> player_index or None
            system_owner = {}
            for cluster in result["clusters"]:
                for sid in cluster["system_ids"]:
                    if cluster["is_home_cluster"]:
                        system_owner[sid] = cluster["player_index"]
                    else:
                        system_owner[sid] = None
            system_owner[0] = None  # Founder's World is neutral

            homes = [s for s in result["systems"] if s["is_home_system"]]
            for home in homes:
                player = home["owner_player_index"]
                # Safe nodes: own cluster + neutral + Founder's World
                safe_nodes = {
                    sid for sid, owner in system_owner.items()
                    if owner is None or owner == player
                }
                safe_subgraph = G.subgraph(safe_nodes)
                assert nx.has_path(safe_subgraph, home["id"], 0), (
                    f"Player {player} (home={home['id']}) cannot reach Founder's World "
                    f"without passing through another player's cluster "
                    f"(players={num_players}, seed={seed})"
                )


def test_deterministic_with_seed():
    """Same seed should produce identical maps."""
    result1 = generate_map(4, seed=123)
    result2 = generate_map(4, seed=123)
    assert len(result1["systems"]) == len(result2["systems"])
    assert len(result1["jump_lines"]) == len(result2["jump_lines"])
    for s1, s2 in zip(result1["systems"], result2["systems"]):
        assert s1["name"] == s2["name"]
        assert s1["x"] == s2["x"]
        assert s1["y"] == s2["y"]
