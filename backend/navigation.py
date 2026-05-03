"""
navigation.py
A* pathfinding engine for indoor navigation.

Usage:
    from navigation import Navigator
    nav = Navigator('floor_map.json')
    result = nav.get_path('ELEVATOR', 'B-412')
    # or with raw coordinates:
    result = nav.get_path_from_coords((0, 0), 'B-412')
"""
import json
import math
import heapq
from typing import List, Tuple, Dict, Optional


# ─────────────────────────────────────────────
# Graph Builder
# ─────────────────────────────────────────────

def build_graph(walkable_nodes: List[List[int]]) -> Dict[Tuple, List[Tuple]]:
    """
    Build an adjacency list from a list of walkable (x, y) nodes.
    Two nodes are connected if they are exactly 1 unit apart (4-directional).
    """
    node_set = {tuple(n) for n in walkable_nodes}
    graph = {node: [] for node in node_set}

    for (x, y) in node_set:
        for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
            neighbour = (x + dx, y + dy)
            if neighbour in node_set:
                # Edge weight = 1 (uniform grid step)
                graph[(x, y)].append((neighbour, 1))

    return graph


# ─────────────────────────────────────────────
# A* Algorithm
# ─────────────────────────────────────────────

def heuristic(a: Tuple[int, int], b: Tuple[int, int]) -> float:
    """Manhattan distance heuristic — optimal for 4-directional grids."""
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def astar(graph: Dict, start: Tuple, goal: Tuple) -> Optional[List[Tuple]]:
    """
    A* search from start to goal on the graph.
    Returns a list of (x,y) tuples from start to goal, or None if unreachable.
    """
    if start not in graph:
        # Snap to nearest walkable node
        start = nearest_node(start, list(graph.keys()))
    if goal not in graph:
        goal = nearest_node(goal, list(graph.keys()))

    # Priority queue: (f_score, node)
    open_set = []
    heapq.heappush(open_set, (0, start))

    came_from = {}
    g_score = {node: float('inf') for node in graph}
    g_score[start] = 0
    f_score = {node: float('inf') for node in graph}
    f_score[start] = heuristic(start, goal)

    while open_set:
        _, current = heapq.heappop(open_set)

        if current == goal:
            return reconstruct_path(came_from, current)

        for neighbour, weight in graph[current]:
            tentative_g = g_score[current] + weight
            if tentative_g < g_score[neighbour]:
                came_from[neighbour] = current
                g_score[neighbour] = tentative_g
                f_score[neighbour] = tentative_g + heuristic(neighbour, goal)
                heapq.heappush(open_set, (f_score[neighbour], neighbour))

    return None  # No path found


def reconstruct_path(came_from: Dict, current: Tuple) -> List[Tuple]:
    """Trace back the shortest path from goal to start."""
    path = [current]
    while current in came_from:
        current = came_from[current]
        path.append(current)
    path.reverse()
    return path


def nearest_node(pos: Tuple, nodes: List[Tuple]) -> Tuple:
    """Return the walkable node closest to a given (x, y) position."""
    return min(nodes, key=lambda n: math.hypot(n[0] - pos[0], n[1] - pos[1]))


# ─────────────────────────────────────────────
# Direction Generator
# ─────────────────────────────────────────────

DIRECTION_NAMES = {
    (-1,  0): "west",
    ( 1,  0): "east",
    ( 0, -1): "south",
    ( 0,  1): "north",
}

# ─────────────────────────────────────────────
# Zone-based Arrival Detection
# ─────────────────────────────────────────────

ARRIVAL_RADIUS = 2  # grid units — within this distance = "you're here"

def nearest_room_to_pos(
    pos: Tuple[int, int],
    room_map: Dict[str, Tuple],
    room_display: Dict[str, str],
    corridor_y: int = 8,
    radius: float = ARRIVAL_RADIUS
) -> Optional[Dict]:
    """
    Return the closest room within `radius` grid units of `pos`.
    For rooms NOT on the corridor (y != corridor_y), only the x-distance
    is used — because those rooms are offset vertically for display only,
    so using Euclidean distance would cause a systematic 1-unit shift error.
    """
    best = None
    best_dist = float('inf')
    for room_id, coord in room_map.items():
        # Use x-only distance for rooms offset from corridor (faculty rooms, labs)
        if coord[1] != corridor_y:
            dist = abs(coord[0] - pos[0])
        else:
            dist = math.hypot(coord[0] - pos[0], coord[1] - pos[1])
        if dist < best_dist:
            best_dist = dist
            best = (room_id, coord, dist)

    if best and best[2] <= radius:
        room_id, coord, dist = best
        return {
            "room_id": room_id,
            "display_name": room_display.get(room_id, room_id),
            "distance": round(dist, 2)
        }
    return None


def path_to_instructions(
    path: List[Tuple],
    room_map: Dict[str, Tuple] = None,
    room_display: Dict[str, str] = None
) -> List[str]:
    """
    Convert a sequence of (x,y) nodes into human-readable navigation steps.
    Consecutive steps in the same direction are collapsed into one instruction.
    If room_map is provided, landmark rooms near waypoints are called out.
    """
    if len(path) < 2:
        return ["You are already at the destination."]

    # Build a quick lookup: coord -> room name for landmark callouts
    waypoint_labels = {}
    if room_map and room_display:
        for room_id, coord in room_map.items():
            # Only label rooms that sit exactly on corridor nodes
            if coord in path[1:-1]:  # skip start and goal
                waypoint_labels[coord] = room_display.get(room_id, room_id)

    instructions = []
    current_dir = None
    step_count = 0

    for i in range(1, len(path)):
        dx = path[i][0] - path[i-1][0]
        dy = path[i][1] - path[i-1][1]
        direction = (dx, dy)

        # Callout when passing a landmark mid-route
        if path[i] in waypoint_labels and current_dir is not None:
            instructions.append(
                f"Go {DIRECTION_NAMES.get(current_dir, str(current_dir))} for {step_count} m"
            )
            instructions.append(f"Pass {waypoint_labels[path[i]]}")
            step_count = 0
            current_dir = None

        if direction == current_dir:
            step_count += 1
        else:
            if current_dir is not None:
                instructions.append(
                    f"Go {DIRECTION_NAMES.get(current_dir, str(current_dir))} for {step_count} m"
                )
            current_dir = direction
            step_count = 1

    if current_dir is not None:
        instructions.append(
            f"Go {DIRECTION_NAMES.get(current_dir, str(current_dir))} for {step_count} m"
        )

    instructions.append("You have arrived at your destination.")
    return instructions


# ─────────────────────────────────────────────
# Navigator Class (main interface)
# ─────────────────────────────────────────────

class Navigator:
    """
    High-level navigation interface.

    Example:
        nav = Navigator('floor_map.json')
        result = nav.get_path_from_coords((-3, -4), 'B-412')
        print(result['instructions'])
    """

    def __init__(self, floor_map_path: str = 'floor_map.json'):
        with open(floor_map_path, 'r') as f:
            floor_map = json.load(f)

        self.room_map: Dict[str, Tuple] = {
            k: tuple(v) for k, v in floor_map['room_map'].items()
        }
        self.room_display = floor_map.get('room_display_names', {})
        self.graph = build_graph(floor_map['walkable_nodes'])
        self.walkable_nodes = [tuple(n) for n in floor_map['walkable_nodes']]
        print(f"[Navigator] Loaded graph: {len(self.graph)} nodes, "
              f"{sum(len(v) for v in self.graph.values())} edges, "
              f"{len(self.room_map)} mapped rooms.")

    def list_rooms(self) -> List[str]:
        """Return all available room IDs."""
        return sorted(self.room_map.keys())

    def get_path(self, start_room: str, end_room: str) -> Dict:
        """Navigate between two named rooms."""
        if start_room not in self.room_map:
            return {"error": f"Unknown room: {start_room}"}
        if end_room not in self.room_map:
            return {"error": f"Unknown room: {end_room}"}

        start_coord = self.room_map[start_room]
        return self._navigate(start_coord, end_room)

    def get_path_from_coords(self, current_pos: Tuple[float, float], end_room: str) -> Dict:
        """
        Navigate from a raw (x, y) coordinate (e.g. from KNN output) to a named room.
        Snaps current_pos to the nearest walkable node automatically.
        """
        if end_room not in self.room_map:
            return {"error": f"Unknown room: {end_room}"}

        # Round float coordinates from KNN to the nearest integer grid node
        snapped = nearest_node(
            (round(current_pos[0]), round(current_pos[1])),
            self.walkable_nodes
        )
        return self._navigate(snapped, end_room)

    def _navigate(self, start_coord: Tuple, end_room: str) -> Dict:
        goal_coord = self.room_map[end_room]
        path = astar(self.graph, start_coord, goal_coord)

        if path is None:
            return {
                "error": "No navigable path found. Check that start and end are on the walkable map.",
                "start": start_coord,
                "end_room": end_room,
                "goal": goal_coord
            }

        instructions = path_to_instructions(path, self.room_map, self.room_display)
        total_distance = len(path) - 1  # grid units

        return {
            "start": list(start_coord),
            "end_room": end_room,
            "destination_display": self.room_display.get(end_room, end_room),
            "goal": list(goal_coord),
            "path": [list(p) for p in path],
            "instructions": instructions,
            "total_steps": total_distance
        }

    def nearest_room(self, pos: Tuple[int, int], radius: float = ARRIVAL_RADIUS) -> Optional[Dict]:
        """Public wrapper for zone-based arrival detection."""
        return nearest_room_to_pos(pos, self.room_map, self.room_display, radius)


# ─────────────────────────────────────────────
# Quick test when run directly
# ─────────────────────────────────────────────

if __name__ == '__main__':
    nav = Navigator('floor_map.json')

    print("\nAvailable rooms:", nav.list_rooms())

    test_cases = [
        ("ELEVATOR", "B-412"),
        ("ELEVATOR", "B-416"),
        ((-3.7, -3.5), "B-412"),   # simulated KNN output -> named room
        ((-20.1, -4.2), "B-403"),  # crossing back toward elevator
    ]

    for start, end in test_cases:
        print(f"\n{'='*55}")
        if isinstance(start, str):
            result = nav.get_path(start, end)
        else:
            result = nav.get_path_from_coords(start, end)

        if "error" in result:
            print(f"[ERROR] {result['error']}")
        else:
            print(f"From: {result['start']}  -->  To: {result['destination_display']}")
            print(f"Total steps: {result['total_steps']}")
            print("Path:", result['path'])
            print("Instructions:")
            for i, step in enumerate(result['instructions'], 1):
                print(f"   {i}. {step}")
