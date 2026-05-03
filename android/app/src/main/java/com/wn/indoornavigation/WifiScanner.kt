package com.wn.indoornavigation

import android.Manifest
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.net.wifi.WifiManager
import android.os.Build
import androidx.core.content.ContextCompat

/**
 * WifiScanner
 *
 * Wraps Android's WifiManager to perform a single WiFi scan and
 * return a {BSSID -> RSSI} map required by the /localize endpoint.
 *
 * Usage:
 *   val scanner = WifiScanner(context)
 *   scanner.scan { bssidMap -> /* send to backend */ }
 */
class WifiScanner(private val context: Context) {

    private val wifiManager: WifiManager =
        context.applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager

    /**
     * Check if all required permissions are granted.
     * Must be called before scan().
     */
    fun hasPermissions(): Boolean {
        val fineLocation = ContextCompat.checkSelfPermission(
            context, Manifest.permission.ACCESS_FINE_LOCATION
        ) == PackageManager.PERMISSION_GRANTED

        return fineLocation
    }

    /**
     * Trigger a WiFi scan. Results are delivered via [onResult] callback.
     *
     * @param onResult  Called with a {bssid: rssi} map when the scan completes.
     * @param onError   Called if the scan could not be initiated.
     */
    fun scan(
        onResult: (Map<String, Int>) -> Unit,
        onError: (String) -> Unit = {}
    ) {
        if (!hasPermissions()) {
            onError("Location permission not granted. Please enable it in Settings.")
            return
        }

        // Register a one-shot receiver that fires when the scan is done
        val receiver = object : BroadcastReceiver() {
            override fun onReceive(ctx: Context, intent: Intent) {
                context.unregisterReceiver(this)

                // getScanResults() requires ACCESS_FINE_LOCATION
                val results = wifiManager.scanResults

                if (results.isNullOrEmpty()) {
                    onError("No WiFi networks found. Make sure WiFi is enabled.")
                    return
                }

                // Build BSSID → RSSI map; keep strongest reading if BSSID appears twice
                val bssidMap = mutableMapOf<String, Int>()
                for (result in results) {
                    val mac = result.BSSID.lowercase()
                    val rssi = result.level  // already in dBm (negative)
                    // Keep the strongest (highest) reading for duplicates
                    if (!bssidMap.containsKey(mac) || rssi > bssidMap[mac]!!) {
                        bssidMap[mac] = rssi
                    }
                }

                onResult(bssidMap)
            }
        }

        val filter = IntentFilter(WifiManager.SCAN_RESULTS_AVAILABLE_ACTION)
        context.registerReceiver(receiver, filter)

        // Start the scan (deprecated on Android 9+ but still works for background apps)
        val started = wifiManager.startScan()
        if (!started) {
            context.unregisterReceiver(receiver)
            // On throttled devices, fall back to cached results
            val cached = wifiManager.scanResults
            if (!cached.isNullOrEmpty()) {
                val bssidMap = cached.associate { it.BSSID.lowercase() to it.level }
                onResult(bssidMap)
            } else {
                onError("WiFi scan could not be started. Try enabling WiFi scanning in system settings.")
            }
        }
    }
}
