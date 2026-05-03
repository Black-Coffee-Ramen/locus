"""
Backend API for WiFi Indoor Localization and Navigation System.
Exposes endpoints consumed by the Android app.

Endpoints:
  GET  /rooms         -> list all available rooms
  GET  /map           -> floor map nodes (for drawing on Android)
  POST /localize      -> WiFi scan -> (x, y) prediction
  POST /navigate      -> (x, y) + destination -> path + instructions
"""
from flask import Flask, request, jsonify
from flask_cors import CORS
import json
import numpy as np
import joblib
import os

from navigation import Navigator

app = Flask(__name__)
CORS(app)  # Allow cross-origin requests from the Android app

# ─────────────────────────────────────────────
# Load model and supporting files at startup
# ─────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

print("Loading KNN model...")
model = joblib.load(os.path.join(BASE_DIR, 'knn_localization_model.joblib'))

print("Loading BSSID feature list...")
with open(os.path.join(BASE_DIR, 'bssids.json'), 'r') as f:
    BSSIDS = json.load(f)

print("Loading floor map and navigator...")
nav = Navigator(os.path.join(BASE_DIR, 'floor_map.json'))

with open(os.path.join(BASE_DIR, 'floor_map.json'), 'r') as f:
    floor_map_data = json.load(f)

print("Backend ready.")


# ─────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────

def build_feature_vector(rssi_dict: dict) -> np.ndarray:
    """
    Convert a {bssid: rssi} dict into the ordered feature vector
    expected by the KNN model. Missing BSSIDs get -100 (no signal).
    """
    return np.array([[rssi_dict.get(bssid, -100) for bssid in BSSIDS]])


# ─────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────

@app.route('/health', methods=['GET'])
def health():
    """Health check endpoint."""
    return jsonify({"status": "ok", "model": "KNN", "rooms": len(nav.room_map)})


@app.route('/rooms', methods=['GET'])
def get_rooms():
    """
    Returns all navigable room IDs and their display names.
    Android uses this to populate the destination dropdown.
    """
    rooms = [
        {
            "id": room_id,
            "display_name": nav.room_display.get(room_id, room_id),
            "x": coord[0],
            "y": coord[1]
        }
        for room_id, coord in nav.room_map.items()
    ]
    return jsonify({"rooms": rooms})


@app.route('/map', methods=['GET'])
def get_map():
    """
    Returns the walkable node list and room positions.
    Android uses this to draw the floor map on a Canvas.
    """
    return jsonify({
        "walkable_nodes": floor_map_data['walkable_nodes'],
        "room_map": floor_map_data['room_map'],
        "room_display_names": floor_map_data.get('room_display_names', {})
    })


@app.route('/localize', methods=['POST'])
def localize():
    """
    Predicts the user's (x, y) location from a WiFi scan.

    Request body:
    {
        "bssids": {
            "00:df:1d:6a:9c:2a": -65,
            "72:7f:f0:12:cf:80": -54,
            ...
        }
    }

    Response:
    {
        "x": -7.3,
        "y": -3.8,
        "snapped_x": -7,
        "snapped_y": -4,
        "confidence": "high"
    }
    """
    data = request.get_json()
    if not data or 'bssids' not in data:
        return jsonify({"error": "Request must include 'bssids' dict"}), 400

    rssi_dict = data['bssids']
    if not rssi_dict:
        return jsonify({"error": "Empty BSSID list — please scan WiFi first"}), 400

    # Truncate to Top 12 strongest APs to match the feature density of the training dataset.
    # This mitigates prediction variance (teleportation) caused by weak, fluctuating background noise
    # and prevents asymmetric distance penalties in the KNN algorithm.
    sorted_bssids = sorted(rssi_dict.items(), key=lambda x: x[1], reverse=True)
    top_rssi_dict = dict(sorted_bssids[:12])

    # Build feature vector and predict
    features = [top_rssi_dict.get(bssid, -100) for bssid in BSSIDS]
    features_array = np.array(features).reshape(1, -1)
    
    prediction = model.predict(features_array)[0]  # [x, y]
    x_pred, y_pred = float(prediction[0]), float(prediction[1])

    # Snap to nearest walkable node for navigation use
    from navigation import nearest_node
    walkable = [tuple(n) for n in floor_map_data['walkable_nodes']]
    snapped = nearest_node((round(x_pred), round(y_pred)), walkable)

    # Confidence based on how many known BSSIDs were seen
    known_seen = sum(1 for b in rssi_dict if b in BSSIDS)
    confidence = "high" if known_seen >= 5 else "medium" if known_seen >= 2 else "low"

    # Zone-based arrival: find nearest room within 2 grid units
    snapped_pos = (snapped[0], snapped[1])
    nearby_room = nav.nearest_room(snapped_pos)

    return jsonify({
        "x": round(x_pred, 2),
        "y": round(y_pred, 2),
        "snapped_x": snapped[0],
        "snapped_y": snapped[1],
        "known_bssids_seen": known_seen,
        "confidence": confidence,
        "nearest_room": nearby_room   # e.g. {"room_id": "A-416", "display_name": "Lab 3 (Block A)", "distance": 1.4} or null
    })


@app.route('/navigate', methods=['POST'])
def navigate():
    """
    Returns the A* path and step-by-step instructions.

    Request body:
    {
        "x": -7.3,
        "y": -3.8,
        "destination": "B-412"
    }

    Response:
    {
        "start": [-7, -4],
        "goal": [-23, -3],
        "destination_display": "Room B-412",
        "path": [[-7,-4], [-8,-4], ...],
        "instructions": ["Go west for 16 step(s)", ...],
        "total_steps": 17
    }
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "Empty request body"}), 400

    x = data.get('x')
    y = data.get('y')
    destination = data.get('destination')

    if x is None or y is None:
        return jsonify({"error": "Missing 'x' or 'y' fields"}), 400
    if not destination:
        return jsonify({"error": "Missing 'destination' field"}), 400

    result = nav.get_path_from_coords((float(x), float(y)), destination)

    if "error" in result:
        return jsonify(result), 404

    return jsonify(result)


# ─────────────────────────────────────────────
# Run
# ─────────────────────────────────────────────

if __name__ == '__main__':
    # host='0.0.0.0' makes it accessible from Android on same WiFi network
    # Change port if 5000 is taken
    app.run(host='0.0.0.0', port=5000, debug=True)
