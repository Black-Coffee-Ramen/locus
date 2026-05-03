package com.wn.indoornavigation

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import android.view.View
import android.widget.*
import androidx.activity.result.contract.ActivityResultContracts
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import androidx.lifecycle.lifecycleScope
import com.google.android.material.button.MaterialButton
import com.google.android.material.card.MaterialCardView
import com.google.android.material.snackbar.Snackbar
import com.wn.indoornavigation.network.*
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MainActivity : AppCompatActivity() {

    // ── Views ─────────────────────────────────────────────────
    private lateinit var mapView: FloorMapView
    private lateinit var spinnerRooms: Spinner
    private lateinit var btnScan: MaterialButton
    private lateinit var btnNavigate: MaterialButton
    private lateinit var btnClear: MaterialButton
    private lateinit var progressBar: ProgressBar
    private lateinit var cardStatus: MaterialCardView
    private lateinit var tvStatus: TextView
    private lateinit var tvConfidence: TextView
    private lateinit var cardInstructions: MaterialCardView
    private lateinit var tvInstructions: TextView
    private lateinit var tvSteps: TextView

    // ── State ─────────────────────────────────────────────────
    private var rooms: List<Room> = emptyList()
    private var currentX: Double = 0.0
    private var currentY: Double = 0.0
    private var hasLocation = false
    private val wifiScanner by lazy { WifiScanner(this) }

    // ── Permission Launcher ───────────────────────────────────
    private val permissionLauncher = registerForActivityResult(
        ActivityResultContracts.RequestMultiplePermissions()
    ) { grants ->
        if (grants.values.all { it }) {
            startWifiScan()
        } else {
            showSnack("Location permission is required for WiFi scanning.")
        }
    }

    // ─────────────────────────────────────────────────────────
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)
        bindViews()
        loadMapAndRooms()

        btnScan.setOnClickListener { checkPermissionsAndScan() }
        btnNavigate.setOnClickListener { navigate() }
        btnClear.setOnClickListener {
            mapView.clearPath()
            cardInstructions.visibility = View.GONE
            btnNavigate.isEnabled = hasLocation
        }
    }

    // ─────────────────────────────────────────────────────────
    private fun bindViews() {
        mapView          = findViewById(R.id.mapView)
        spinnerRooms     = findViewById(R.id.spinnerRooms)
        btnScan          = findViewById(R.id.btnScan)
        btnNavigate      = findViewById(R.id.btnNavigate)
        btnClear         = findViewById(R.id.btnClear)
        progressBar      = findViewById(R.id.progressBar)
        cardStatus       = findViewById(R.id.cardStatus)
        tvStatus         = findViewById(R.id.tvStatus)
        tvConfidence     = findViewById(R.id.tvConfidence)
        cardInstructions = findViewById(R.id.cardInstructions)
        tvInstructions   = findViewById(R.id.tvInstructions)
        tvSteps          = findViewById(R.id.tvSteps)

        btnNavigate.isEnabled = false
    }

    // ─────────────────────────────────────────────────────────
    /** Fetch map geometry and room list from the backend */
    private fun loadMapAndRooms() {
        showLoading(true)
        lifecycleScope.launch {
            try {
                val mapData = withContext(Dispatchers.IO) { ApiClient.service.getMap() }
                val roomsData = withContext(Dispatchers.IO) { ApiClient.service.getRooms() }

                mapView.setMapData(
                    mapData.walkable_nodes,
                    mapData.room_map,
                    mapData.room_display_names
                )

                rooms = roomsData.rooms
                val roomNames = rooms.map { it.display_name }
                spinnerRooms.adapter = ArrayAdapter(
                    this@MainActivity,
                    android.R.layout.simple_spinner_dropdown_item,
                    roomNames
                )

            } catch (e: Exception) {
                showSnack("Could not reach backend: ${e.message}\nCheck BASE_URL in ApiClient.kt")
            } finally {
                showLoading(false)
            }
        }
    }

    // ─────────────────────────────────────────────────────────
    /** Check permissions, then scan WiFi */
    private fun checkPermissionsAndScan() {
        val needed = mutableListOf(
            Manifest.permission.ACCESS_FINE_LOCATION,
            Manifest.permission.ACCESS_COARSE_LOCATION
        )
        val missing = needed.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }
        if (missing.isEmpty()) {
            startWifiScan()
        } else {
            permissionLauncher.launch(missing.toTypedArray())
        }
    }

    private fun startWifiScan() {
        showLoading(true)
        tvStatus.text = "Scanning WiFi..."
        cardStatus.visibility = View.VISIBLE

        wifiScanner.scan(
            onResult = { bssidMap ->
                sendToLocalize(bssidMap)
            },
            onError = { msg ->
                runOnUiThread {
                    showLoading(false)
                    showSnack(msg)
                }
            }
        )
    }

    /** POST scan results to /localize and update map */
    private fun sendToLocalize(bssidMap: Map<String, Int>) {
        lifecycleScope.launch {
            try {
                val response = withContext(Dispatchers.IO) {
                    ApiClient.service.localize(LocalizeRequest(bssidMap))
                }

                val acceptedX = response.x
                val acceptedY = response.y
                currentX = acceptedX
                currentY = acceptedY
                hasLocation = true

                mapView.setUserPosition(acceptedX.toFloat(), acceptedY.toFloat())
                mapView.centerOnUser()

                val nr = response.nearest_room
                if (nr != null) {
                    tvStatus.text = "Location: (${response.snapped_x}, ${response.snapped_y}) | Near: ${nr.display_name}"
                } else {
                    tvStatus.text = "Location: (${response.snapped_x}, ${response.snapped_y})"
                }

                tvConfidence.text = "Confidence: ${response.confidence} " +
                        "(${response.known_bssids_seen} known APs seen)"
                tvConfidence.visibility = View.VISIBLE
                cardStatus.visibility = View.VISIBLE
                btnNavigate.isEnabled = true

                // Auto-update navigation path if one is already active
                if (mapView.hasActiveNavigation()) {
                    navigate()
                }

            } catch (e: Exception) {
                showSnack("Localization failed: ${e.message}")
            } finally {
                showLoading(false)
            }
        }
    }

    // ─────────────────────────────────────────────────────────
    /** POST current location + destination to /navigate */
    private fun navigate() {
        if (!hasLocation) {
            showSnack("Scan WiFi first to determine your location.")
            return
        }
        val selectedRoom = rooms.getOrNull(spinnerRooms.selectedItemPosition) ?: return
        showLoading(true)

        lifecycleScope.launch {
            try {
                val response = withContext(Dispatchers.IO) {
                    ApiClient.service.navigate(
                        NavigateRequest(currentX, currentY, selectedRoom.id)
                    )
                }

                mapView.setNavigationPath(response.path, selectedRoom.id)

                val instructionText = response.instructions
                    .mapIndexed { i, s -> "${i + 1}. $s" }
                    .joinToString("\n")

                tvInstructions.text = instructionText
                tvSteps.text = "Total: ${response.total_steps} m to ${response.destination_display}"
                cardInstructions.visibility = View.VISIBLE

            } catch (e: Exception) {
                showSnack("Navigation failed: ${e.message}")
            } finally {
                showLoading(false)
            }
        }
    }

    // ─────────────────────────────────────────────────────────
    private fun showLoading(show: Boolean) {
        progressBar.visibility = if (show) View.VISIBLE else View.GONE
        btnScan.isEnabled = !show
    }

    private fun showSnack(msg: String) {
        Snackbar.make(mapView, msg, Snackbar.LENGTH_LONG).show()
    }
}
