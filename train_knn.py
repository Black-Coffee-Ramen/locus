import json
import numpy as np
import pandas as pd
from sklearn.neighbors import KNeighborsRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, mean_absolute_error
import joblib

def load_data(filepath):
    with open(filepath, 'r') as f:
        data = json.load(f)
    return data

def preprocess_data(data):
    # Find all unique BSSIDs
    all_bssids = set()
    for point in data:
        all_bssids.update(point.get('rssi', {}).keys())
    
    all_bssids = list(all_bssids)
    print(f"Total unique BSSIDs found: {len(all_bssids)}")
    
    # Build X (features) and y (targets)
    X = []
    y = []
    
    for point in data:
        # Default RSSI for missing APs is usually a low value like -100
        # since weaker signals mean further away.
        features = []
        for bssid in all_bssids:
            features.append(point.get('rssi', {}).get(bssid, -100))
        
        X.append(features)
        y.append([point['x'], point['y']])
        
    return np.array(X), np.array(y), all_bssids

def main():
    filepath = 'survey.json'
    print("Loading survey data...")
    data = load_data(filepath)
    
    print("Preprocessing data...")
    X, y, bssids = preprocess_data(data)
    
    print(f"Dataset shape: X={X.shape}, y={y.shape}")
    
    # Save the feature columns (BSSIDs) so the backend knows the exact order
    with open('bssids.json', 'w') as f:
        json.dump(bssids, f)
    print("Saved feature columns to bssids.json")
    
    # Split the dataset
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    # Initialize and train KNN
    # n_neighbors can be tuned, 3 is a good starting point for fingerprinting
    k = 3
    print(f"Training KNN Regressor with k={k}...")
    model = KNeighborsRegressor(n_neighbors=k, weights='distance') 
    # 'distance' weight is good for RSSI so closer points in feature space have more impact
    
    model.fit(X_train, y_train)
    
    # Evaluate
    predictions = model.predict(X_test)
    mse = mean_squared_error(y_test, predictions)
    mae = mean_absolute_error(y_test, predictions)
    
    print(f"Evaluation Results:")
    print(f"Mean Squared Error: {mse:.4f}")
    print(f"Mean Absolute Error (Grid Units): {mae:.4f}")
    
    # Print a few predictions vs actual to see visually
    print("\nSample Predictions (Test Set):")
    for i in range(min(5, len(predictions))):
        print(f"Actual: {y_test[i]} -> Predicted: {np.round(predictions[i], 1)}")
    
    # Save the model
    model_filename = 'knn_localization_model.joblib'
    joblib.dump(model, model_filename)
    print(f"\nModel saved to {model_filename}")

if __name__ == '__main__':
    main()
