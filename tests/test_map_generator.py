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
    for num_players in [2, 3, 4, 5, 6, 7, 8]:
        for seed in [1, 7, 42, 99, 777]:
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


def test_neutral_clusters_have_at_least_one_system():
    """Every neutral cluster must contain at least one star system."""
    for num_players in [2, 3, 4, 5, 6]:
        for seed in [1, 42, 99]:
            result = generate_map(num_players, seed=seed)
            neutral_clusters = [c for c in result["clusters"] if not c["is_home_cluster"]]
            for nc in neutral_clusters:
                assert len(nc["system_ids"]) >= 1, (
                    f"Neutral cluster {nc['id']} has no systems "
                    f"(players={num_players}, seed={seed})"
                )


def test_player_clusters_form_ring():
    """For 3+ players, each player cluster must have direct jump lines to
    at least 2 other player clusters (ring topology)."""
    for num_players in [3, 4, 5, 6]:
        for seed in [1, 42, 99]:
            result = generate_map(num_players, seed=seed)
            G = nx.Graph()
            for jl in result["jump_lines"]:
                G.add_edge(jl["from_id"], jl["to_id"])

            sys_to_cluster = {0: None}
            for c in result["clusters"]:
                for sid in c["system_ids"]:
                    sys_to_cluster[sid] = c["id"]

            player_cluster_ids = {c["id"] for c in result["clusters"] if c["is_home_cluster"]}
            player_clusters = [c for c in result["clusters"] if c["is_home_cluster"]]

            for cluster in player_clusters:
                cluster_sys = set(cluster["system_ids"])
                connected_player_clusters = set()
                for sid in cluster_sys:
                    for neighbor in G.neighbors(sid):
                        nc = sys_to_cluster.get(neighbor)
                        if nc in player_cluster_ids and nc != cluster["id"]:
                            connected_player_clusters.add(nc)
                assert len(connected_player_clusters) >= 2, (
                    f"Player cluster {cluster['id']} (player {cluster['player_index']}) "
                    f"connects to only {len(connected_player_clusters)} other player cluster(s) "
                    f"(players={num_players}, seed={seed})"
                )


def test_neutral_clusters_bridge_player_clusters():
    """Every neutral cluster must connect directly to at least 2 different
    player clusters (acting as a contested bridge between them)."""
    for num_players in [2, 3, 4, 5, 6]:
        for seed in [1, 42, 99]:
            result = generate_map(num_players, seed=seed)
            G = nx.Graph()
            for jl in result["jump_lines"]:
                G.add_edge(jl["from_id"], jl["to_id"])

            sys_to_cluster = {0: None}
            for c in result["clusters"]:
                for sid in c["system_ids"]:
                    sys_to_cluster[sid] = c["id"]

            player_cluster_ids = {c["id"] for c in result["clusters"] if c["is_home_cluster"]}
            neutral_clusters = [c for c in result["clusters"] if not c["is_home_cluster"]]

            for neutral in neutral_clusters:
                neutral_sys = set(neutral["system_ids"])
                connected_player_clusters = set()
                for sid in neutral_sys:
                    for neighbor in G.neighbors(sid):
                        nc = sys_to_cluster.get(neighbor)
                        if nc in player_cluster_ids:
                            connected_player_clusters.add(nc)
                assert len(connected_player_clusters) >= 2, (
                    f"Neutral cluster {neutral['id']} connects to only "
                    f"{len(connected_player_clusters)} player cluster(s) "
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
