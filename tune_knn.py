"""
KNN Hyperparameter Tuning for WiFi Indoor Localization
Searches over key parameters and reports the best configuration.
"""
import json
import numpy as np
from sklearn.neighbors import KNeighborsRegressor
from sklearn.model_selection import GridSearchCV, LeaveOneOut, cross_val_score
from sklearn.metrics import mean_absolute_error
import joblib
import warnings
warnings.filterwarnings('ignore')

def load_data(filepath):
    with open(filepath, 'r') as f:
        return json.load(f)

def preprocess_data(data):
    all_bssids = set()
    for point in data:
        all_bssids.update(point.get('rssi', {}).keys())
    all_bssids = list(all_bssids)

    X, y = [], []
    for point in data:
        features = [point.get('rssi', {}).get(bssid, -100) for bssid in all_bssids]
        X.append(features)
        y.append([point['x'], point['y']])

    return np.array(X), np.array(y), all_bssids

def euclidean_error(y_true, y_pred):
    """Compute mean Euclidean distance between predicted and actual (x,y)."""
    return np.mean(np.sqrt(np.sum((y_true - y_pred) ** 2, axis=1)))

def main():
    print("Loading and preprocessing data...")
    data = load_data('coordinates.json')
    X, y, bssids = preprocess_data(data)
    print(f"  Dataset: {X.shape[0]} points, {X.shape[1]} BSSIDs\n")

    # -------------------------------------------------------------------
    # Parameter grid to search
    # k       : how many neighbors to consider
    # weights : 'uniform' (all equal) vs 'distance' (closer = more weight)
    # metric  : distance function used in feature space
    # -------------------------------------------------------------------
    param_grid = {
        'n_neighbors': [1, 2, 3, 4, 5, 7],
        'weights':     ['uniform', 'distance'],
        'metric':      ['euclidean', 'manhattan', 'chebyshev'],
    }

    # Use LeaveOneOut CV — best strategy for small datasets like ours (56 points)
    loo = LeaveOneOut()

    print("Running GridSearchCV with Leave-One-Out cross-validation...")
    print("(This tests every parameter combination fairly — takes ~30 seconds)\n")

    # We train a separate model for x and y, but for the grid search
    # we use the joint KNeighborsRegressor which handles multi-output natively.
    knn = KNeighborsRegressor()
    grid = GridSearchCV(
        knn,
        param_grid,
        cv=loo,
        scoring='neg_mean_squared_error',
        n_jobs=-1,
        refit=True
    )
    grid.fit(X, y)

    best = grid.best_estimator_
    best_params = grid.best_params_

    # Evaluate best model with LOO — compute true Euclidean distance error
    from sklearn.model_selection import cross_val_predict
    y_pred_loo = cross_val_predict(best, X, y, cv=loo)
    euclid_errors = np.sqrt(np.sum((y - y_pred_loo) ** 2, axis=1))
    mae = mean_absolute_error(y, y_pred_loo)

    print("=" * 55)
    print("  BEST PARAMETERS FOUND")
    print("=" * 55)
    print(f"  k (n_neighbors)  : {best_params['n_neighbors']}")
    print(f"  weights          : {best_params['weights']}")
    print(f"  metric           : {best_params['metric']}")
    print("=" * 55)
    print(f"\n  LOO MAE (grid units)         : {mae:.4f}")
    print(f"  LOO Mean Euclidean Error     : {euclid_errors.mean():.4f} grid units")
    print(f"  LOO Median Euclidean Error   : {np.median(euclid_errors):.4f} grid units")
    print(f"  LOO Max Euclidean Error      : {euclid_errors.max():.4f} grid units")

    # -------------------------------------------------------------------
    # Show full ranking of top 10 configurations
    # -------------------------------------------------------------------
    print("\n  TOP 10 CONFIGURATIONS (sorted by LOO MSE):")
    print(f"  {'k':>4}  {'weights':>10}  {'metric':>12}  {'MSE':>10}")
    print(f"  {'-'*4}  {'-'*10}  {'-'*12}  {'-'*10}")
    results = grid.cv_results_
    sorted_idx = np.argsort(results['mean_test_score'])[::-1]  # higher neg_mse = better
    for rank, i in enumerate(sorted_idx[:10]):
        p = results['params'][i]
        mse_val = -results['mean_test_score'][i]
        print(f"  {p['n_neighbors']:>4}  {p['weights']:>10}  {p['metric']:>12}  {mse_val:>10.4f}")

    # -------------------------------------------------------------------
    # Retrain final model on ALL data with the best params and save
    # -------------------------------------------------------------------
    print(f"\nRetraining on all {len(data)} points with best params...")
    final_model = KNeighborsRegressor(**best_params)
    final_model.fit(X, y)

    joblib.dump(final_model, 'knn_localization_model.joblib')
    with open('bssids.json', 'w') as f:
        json.dump(bssids, f)

    print("Saved: knn_localization_model.joblib  &  bssids.json")
    print("\nDone.")

if __name__ == '__main__':
    main()
