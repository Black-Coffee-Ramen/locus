# Indoor Localization and Navigation System

**Team Members:** Dhruv Bargoti, Dhruv Dewan, Athiyo Chakma, Nitin Yadav

## Overview
The **Indoor Localization and Navigation System** is a full-stack, infrastructure-free localization solution designed to track a user's position inside a building and provide turn-by-turn navigation to specific rooms. Designed specifically for the R&D Building (Floor 4, Wings A & B), this system completely bypasses the limitations of GPS in indoor environments by leveraging existing ambient Wi-Fi signals (Wi-Fi Fingerprinting) combined with Machine Learning and graph-based pathfinding algorithms.

Unlike systems that require expensive Bluetooth beacons or Ultra-Wideband (UWB) hardware installations, this system utilizes the existing building infrastructure—specifically the Received Signal Strength Indicator (RSSI) from standard Wi-Fi Access Points—to calculate precise coordinates.

---


## Technology Stack

### Backend / Server
* **Language:** Python 3.11
* **Framework:** Flask
* **Machine Learning:** Scikit-Learn (`scikit-learn`)
* **Data Processing:** NumPy, Joblib
* **Role:** Acts as the computational brain of the system. It hosts the Machine Learning model, maintains the graph data structures for pathfinding, and processes incoming Wi-Fi vectors via a REST API to return exact coordinates and navigation arrays.

### Frontend / Mobile Application
* **Language:** Kotlin
* **Framework:** Android SDK (Minimum API 24)
* **Networking:** Retrofit2 & OkHttp3 (for asynchronous REST API calls)
* **Concurrency:** Kotlin Coroutines (`lifecycleScope`)
* **UI/Graphics:** Custom Android `Canvas` rendering (`FloorMapView.kt`), Material Components
* **Role:** Provides the user-facing interface. It handles active Wi-Fi scanning (requesting location permissions), renders the 2D floor map, plots the user's marker, and draws the calculated navigation path.

---

## Core System Architecture & Functioning

### Scale and Metrics (2026 Deployment)
* **Walkable Nodes:** 122
* **Mapped Rooms:** 40 across 3 spatial layers (Labs, Main Corridor, Faculty Offices)
* **Unique BSSIDs (Features):** 135
* **Training Fingerprints:** 125

### 1. Data Collection & Training Phase (`coordinates.json`)
The foundation of the system is a highly detailed site survey. During this phase, a technician physically walked the corridors of the R&D building, stopping at mapped grid nodes to capture Wi-Fi scans. Each scan recorded:
* The physical `x, y` coordinate (e.g., `x: -26, y: 8` for A-408).
* A dictionary of every visible router's MAC address (BSSID) and its signal strength (RSSI in dBm).

This data is fed into `train_knn.py`, which compiles a comprehensive list of all unique BSSIDs. Any missing routers at a given point are mathematically penalized by assigning them a baseline signal of `-100 dBm`. The data is then packaged and saved as a pre-trained `knn_localization_model.joblib` binary file for lightning-fast inference.

### 2. Localization Phase (KNN Regression)
When the user clicks "Scan WiFi" in the Android app, the device captures the current ambient Wi-Fi environment and POSTs it to the `/localize` endpoint.
1. **Truncation Filter:** The backend intercepts the payload, sorts the routers by signal strength, and discards everything except the Top 12 strongest signals. This prevents dense, noisy scans from corrupting the distance calculations against sparser training data.
2. **Prediction:** The truncated vector is passed into the `KNeighborsRegressor`. The model calculates the Manhattan distance between the live scan and all historical scans, taking the weighted average of the 5 closest matches (K=5).
3. **Graph Snapping:** The raw prediction is then snapped to the nearest logical `walkable_node` on the floor map to ensure the user's marker isn't placed inside a physical wall.

### 3. Pathfinding Phase (A* Algorithm)
Once the user's location is established, they select a destination room (e.g., "A-415"). The `/navigate` endpoint triggers the A* (A-Star) search algorithm.
* **Nodes & Edges:** The system builds an adjacency list from `walkable_nodes`. Nodes are connected if they are horizontally or vertically adjacent.
* **Heuristic:** The algorithm uses Manhattan distance as the heuristic to guarantee the shortest path to the room's doorway.
* **Instruction Generation:** Once the path array is generated, the backend translates the vector geometry into human-readable instructions (e.g., "Go West for 20 m", "Pass Discussion Area 1").

---

## File Structure & Configuration

* **`coordinates.json`:** The raw training dataset containing physical coordinates, textual descriptions, and RSSI fingerprints.
* **`room_mapping.json`:** The matrix mapping logical room names (e.g., `A-419`) to their physical corridor coordinates and categorical types (Lab, Office, Meeting Room).
* **`floor_map.json`:** An auto-generated JSON file that builds the logical A* graph. It handles gap-bridging heuristics to ensure corridors are perfectly connected across structural gaps (like the elevator lobby).
* **`backend/app.py`:** The main Flask application routing the API requests.
* **`backend/navigation.py`:** The mathematical engine handling A* pathfinding, graph generation, grid snapping, and proximity detection.
* **`android/app/src/main/.../MainActivity.kt`:** The main Android view controller managing permissions, networking, and UI state.
* **`android/app/src/main/.../FloorMapView.kt`:** The custom rendering engine that draws the map, rooms, user marker, and path lines using Android Canvas APIs.

> **CRITICAL WARNING:** The file `bssids.json` defines the Feature Vector Layout of the production KNN model. **Never manually edit this file.** It is auto-generated during training. After every run of `tune_knn.py` or `train_knn.py`, you must copy both `knn_localization_model.joblib` and `bssids.json` from the project root into the `backend/` folder atomically before restarting the Flask server.

---

## REST API Specification

### 1. `GET /map`
* **Purpose:** Returns the static floor geometry to the Android app on launch.
* **Response:** JSON containing `walkable_nodes` arrays, `room_map` coordinates, and `room_display_names`.

### 2. `GET /rooms`
* **Purpose:** Populates the Android dropdown spinner with available destinations.
* **Response:** JSON list of room ID and Display Name pairs.

### 3. `POST /localize`
* **Purpose:** Translates a raw Wi-Fi scan into physical coordinates.
* **Body:** `{"bssids": {"mac_address": -rssi, ...}}`
* **Response:** `{"x": float, "y": float, "snapped_x": int, "snapped_y": int, "nearest_room": object, "confidence": string}`

### 4. `POST /navigate`
* **Purpose:** Calculates the shortest route from the user to a room.
* **Body:** `{"x": float, "y": float, "destination_room": "string"}`
* **Response:** `{"path": [[x1,y1], [x2,y2]...], "instructions": [string, string], "total_steps": int}`

---

## Deployment & Setup Instructions

### Backend Setup
1. Ensure Python 3.10+ is installed.
2. Install dependencies:
   ```bash
   pip install flask flask-cors numpy scikit-learn joblib
   ```
3. Run the map builder to generate the graph:
   ```bash
   python build_floor_map.py
   ```
4. Start the Flask server (ensure it runs on your local network's IP):
   ```bash
   cd backend
   python app.py --host=0.0.0.0
   ```

### Android Setup
1. Open the `/android` folder in Android Studio.
2. Navigate to `ApiClient.kt` and update the `BASE_URL` variable to match the IPv4 address of the computer running the Flask backend (e.g., `http://192.168.1.50:5000/`).
3. Build and run the application on a physical Android device (Emulators do not support active Wi-Fi scanning).
4. Grant Location permissions when prompted.
