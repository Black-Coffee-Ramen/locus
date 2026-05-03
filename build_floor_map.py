import json

with open('coordinates.json') as f:
    coords = json.load(f)
with open('room_mapping.json') as f:
    room_data = json.load(f)

# ── 1. Build walkable nodes from coordinates.json + fill gaps ──
seen = set()
walkable = []
for p in sorted(coords, key=lambda c: (c['y'], c['x'])):
    key = (p['x'], p['y'])
    if key not in seen:
        seen.add(key)
        walkable.append([p['x'], p['y']])

# Fill corridor gaps: x=27 and x=31 at y=8
# Also fill vertical gap: y=2 at x=0
gap_fills = [[27, 8], [31, 8], [0, 2]]
for gf in gap_fills:
    key = tuple(gf)
    if key not in seen:
        seen.add(key)
        walkable.append(gf)
        print(f'  Added gap-fill node: {gf}')

# ── 2. Room coordinates: faculty rooms above corridor, labs below ──
# Faculty rooms: y=10 (north/above corridor at y=8)
# Labs + discussion areas: y=5 (south/below corridor at y=8)
# Meeting room: y=10

FACULTY_TYPES = {'Office'}
LAB_TYPES = {'Lab', 'Discussion Area'}
MEETING_TYPES = {'Meeting Room'}

room_map = {}
room_display = {}

for room_id, info in room_data['rooms'].items():
    rx = info['representative_x']
    room_type = info['type']

    if room_type in FACULTY_TYPES or room_type in MEETING_TYPES:
        ry = 10   # above the corridor
    else:
        ry = 5    # below the corridor (labs)

    room_map[room_id] = [rx, ry]
    room_display[room_id] = room_id   # ← clean short names: "A-401", "B-418" etc.

# ── 3. Add Lift as a navigable landmark (clean name) ──
room_map['LIFT'] = [0, 0]
room_display['LIFT'] = 'Lift'

# ── 4. Write new floor_map.json ──
floor_map = {
    "_comment": "R&D Building Floor 4 — A and B Wings. Faculty rooms at y=10, Labs at y=5, Corridor at y=8.",
    "_coordinate_info": {
        "corridor_y": 8,
        "faculty_rooms_y": 10,
        "labs_y": 5,
        "lift": "(0, 0)",
        "a_wing": "negative x",
        "b_wing": "positive x"
    },
    "walkable_nodes": walkable,
    "room_map": room_map,
    "room_display_names": room_display
}

with open('floor_map_new.json', 'w') as f:
    json.dump(floor_map, f, indent=2)

print(f'\nDone!')
print(f'  Walkable nodes: {len(walkable)}')
print(f'  Rooms: {len(room_map)}')
print(f'\nFaculty rooms (y=10):')
for k,v in room_map.items():
    if v[1] == 10:
        print(f'  {k}: {v}')
print(f'\nLabs (y=5):')
for k,v in room_map.items():
    if v[1] == 5:
        print(f'  {k}: {v}')
