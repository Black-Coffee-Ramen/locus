package com.wn.indoornavigation.network

import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST

// ─────────────────────────────────────────────────────────────
// CHANGE THIS to your laptop's local IP when running the backend
// Find it with: ipconfig (Windows) or ifconfig (Linux/Mac)
// Example: "http://192.168.1.105:5000/"
// ─────────────────────────────────────────────────────────────
const val BASE_URL = "http://192.168.46.57:5000/"

// ─── Data Models ──────────────────────────────────────────────

data class LocalizeRequest(
    val bssids: Map<String, Int>   // { "mac_address": rssi_value }
)

data class LocalizeResponse(
    val x: Double,
    val y: Double,
    val snapped_x: Int,
    val snapped_y: Int,
    val known_bssids_seen: Int,
    val confidence: String,           // "high", "medium", "low"
    val nearest_room: NearestRoom?    // zone-based: null if not near any room
)

data class NearestRoom(
    val room_id: String,
    val display_name: String,
    val distance: Double
)

data class NavigateRequest(
    val x: Double,
    val y: Double,
    val destination: String
)

data class NavigateResponse(
    val start: List<Int>,
    val goal: List<Int>,
    val destination_display: String,
    val path: List<List<Int>>,
    val instructions: List<String>,
    val total_steps: Int
)

data class Room(
    val id: String,
    val display_name: String,
    val x: Int,
    val y: Int
)

data class RoomsResponse(val rooms: List<Room>)

data class MapResponse(
    val walkable_nodes: List<List<Int>>,
    val room_map: Map<String, List<Int>>,
    val room_display_names: Map<String, String>
)

// ─── Retrofit API Interface ────────────────────────────────────

interface ApiService {

    @GET("rooms")
    suspend fun getRooms(): RoomsResponse

    @GET("map")
    suspend fun getMap(): MapResponse

    @POST("localize")
    suspend fun localize(@Body request: LocalizeRequest): LocalizeResponse

    @POST("navigate")
    suspend fun navigate(@Body request: NavigateRequest): NavigateResponse
}

// ─── Singleton ────────────────────────────────────────────────

object ApiClient {
    val service: ApiService by lazy {
        Retrofit.Builder()
            .baseUrl(BASE_URL)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(ApiService::class.java)
    }
}
