package com.wn.indoornavigation

import android.content.Context
import android.graphics.*
import android.util.AttributeSet
import android.view.GestureDetector
import android.view.MotionEvent
import android.view.ScaleGestureDetector
import android.view.View

/**
 * FloorMapView
 *
 * A custom Canvas-based view that draws:
 *  - The walkable corridor nodes as a connected grid
 *  - Room labels at their coordinates
 *  - The user's current predicted location (blue dot)
 *  - The A* navigation path (animated dashed line)
 *  - The destination room (highlighted)
 *
 * Supports pinch-to-zoom and drag-to-pan.
 */
class FloorMapView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null
) : View(context, attrs) {

    // ── Map Data ─────────────────────────────────────────────
    private var walkableNodes: List<List<Int>> = emptyList()
    private var roomMap: Map<String, List<Int>> = emptyMap()
    private var roomDisplayNames: Map<String, String> = emptyMap()
    private var navigationPath: List<List<Int>> = emptyList()
    private var userPosition: Pair<Float, Float>? = null    // (x, y) in grid coords
    private var destinationRoom: String? = null

    // ── Rendering Scale ──────────────────────────────────────
    // Each grid unit maps to this many pixels before user zoom
    private val CELL_PX = 60f

    // Transform: translate grid origin to screen center, flip y (grid y negative = down)
    private var offsetX = 0f
    private var offsetY = 0f
    private var scaleFactor = 1f

    // ── Paints ───────────────────────────────────────────────
    private val corridorPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#2D2D3A")
        strokeWidth = 8f
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
        strokeJoin = Paint.Join.ROUND
    }

    private val nodePaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#3D5AFE")
        style = Paint.Style.FILL
    }

    private val pathPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#00E5FF")
        strokeWidth = 12f
        style = Paint.Style.STROKE
        strokeCap = Paint.Cap.ROUND
        pathEffect = DashPathEffect(floatArrayOf(20f, 10f), 0f)
    }

    private val userPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#FF6D00")
        style = Paint.Style.FILL
    }

    private val userRingPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#FFAB40")
        style = Paint.Style.STROKE
        strokeWidth = 4f
    }

    private val roomPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#546E7A")
        style = Paint.Style.FILL
    }

    private val destPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.parseColor("#00E676")
        style = Paint.Style.FILL
    }

    private val labelPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
        color = Color.WHITE
        textSize = 28f
        textAlign = Paint.Align.CENTER
        typeface = Typeface.create(Typeface.DEFAULT, Typeface.BOLD)
    }

    private val bgPaint = Paint().apply {
        color = Color.parseColor("#1A1A2E")
    }

    // ── Gesture Detectors ────────────────────────────────────
    private val scaleGestureDetector = ScaleGestureDetector(context,
        object : ScaleGestureDetector.SimpleOnScaleGestureListener() {
            override fun onScale(detector: ScaleGestureDetector): Boolean {
                scaleFactor *= detector.scaleFactor
                scaleFactor = scaleFactor.coerceIn(0.3f, 4f)
                invalidate()
                return true
            }
        })

    private var lastTouchX = 0f
    private var lastTouchY = 0f

    private val gestureDetector = GestureDetector(context,
        object : GestureDetector.SimpleOnGestureListener() {
            override fun onScroll(
                e1: MotionEvent?, e2: MotionEvent,
                distanceX: Float, distanceY: Float
            ): Boolean {
                offsetX -= distanceX
                offsetY -= distanceY
                invalidate()
                return true
            }
        })

    override fun onTouchEvent(event: MotionEvent): Boolean {
        scaleGestureDetector.onTouchEvent(event)
        gestureDetector.onTouchEvent(event)
        return true
    }

    // ── Public API ───────────────────────────────────────────

    /** Load the map from backend /map response */
    fun setMapData(
        nodes: List<List<Int>>,
        rooms: Map<String, List<Int>>,
        displayNames: Map<String, String>
    ) {
        walkableNodes = nodes
        roomMap = rooms
        roomDisplayNames = displayNames
        centerMap()
        invalidate()
    }

    /** Update the user's position (grid coordinates from KNN) */
    fun setUserPosition(x: Float, y: Float) {
        userPosition = Pair(x, y)
        invalidate()
    }

    /** Draw the A* navigation path */
    fun setNavigationPath(path: List<List<Int>>, destination: String) {
        navigationPath = path
        destinationRoom = destination
        invalidate()
    }

    /** Clear navigation path */
    fun clearPath() {
        navigationPath = emptyList()
        destinationRoom = null
        invalidate()
    }

    /** Check if navigation is currently active */
    fun hasActiveNavigation(): Boolean {
        return destinationRoom != null
    }

    /** Pan the camera to center on the current user position */
    fun centerOnUser() {
        userPosition?.let { (ux, uy) ->
            offsetX = width / 2f - ux * CELL_PX * scaleFactor
            offsetY = height / 2f + uy * CELL_PX * scaleFactor
            invalidate()
        }
    }

    // ── Drawing ──────────────────────────────────────────────

    private var isMapCentered = false

    override fun onSizeChanged(w: Int, h: Int, oldw: Int, oldh: Int) {
        super.onSizeChanged(w, h, oldw, oldh)
        if (!isMapCentered) {
            centerMap()
            isMapCentered = true
        }
    }

    private fun centerMap() {
        if (walkableNodes.isEmpty()) return
        val xs = walkableNodes.map { it[0] }
        val ys = walkableNodes.map { it[1] }
        val midX = (xs.min() + xs.max()) / 2f
        val midY = (ys.min() + ys.max()) / 2f
        offsetX = width / 2f - midX * CELL_PX
        offsetY = height / 2f + midY * CELL_PX  // y is flipped
    }

    /** Convert grid (x, y) to screen pixels */
    private fun toScreen(gx: Float, gy: Float): PointF {
        return PointF(
            offsetX + gx * CELL_PX * scaleFactor,
            offsetY - gy * CELL_PX * scaleFactor  // flip y-axis
        )
    }

    override fun onDraw(canvas: Canvas) {
        super.onDraw(canvas)

        // Background
        canvas.drawRect(0f, 0f, width.toFloat(), height.toFloat(), bgPaint)

        if (walkableNodes.isEmpty()) return

        val nodeSet = walkableNodes.map { Pair(it[0], it[1]) }.toSet()

        // ── Draw corridor edges ──
        for ((x, y) in nodeSet) {
            // Draw edge to the node at (x-1, y) [west] and (x, y-1) [south]
            for ((dx, dy) in listOf(Pair(-1, 0), Pair(0, -1))) {
                val nx = x + dx; val ny = y + dy
                if (Pair(nx, ny) in nodeSet) {
                    val s1 = toScreen(x.toFloat(), y.toFloat())
                    val s2 = toScreen(nx.toFloat(), ny.toFloat())
                    canvas.drawLine(s1.x, s1.y, s2.x, s2.y, corridorPaint)
                }
            }
        }

        // ── Draw walkable nodes ──
        val nodeRadius = 8f * scaleFactor
        for ((x, y) in nodeSet) {
            val s = toScreen(x.toFloat(), y.toFloat())
            canvas.drawCircle(s.x, s.y, nodeRadius, nodePaint)
        }

        // ── Draw room markers ──
        val roomRadius = 18f * scaleFactor
        for ((roomId, coord) in roomMap) {
            val paint = if (roomId == destinationRoom) destPaint else roomPaint
            val s = toScreen(coord[0].toFloat(), coord[1].toFloat())
            canvas.drawCircle(s.x, s.y, roomRadius, paint)
            val label = roomDisplayNames[roomId]?.replace("Room ", "") ?: roomId
            labelPaint.textSize = 22f * scaleFactor.coerceIn(0.5f, 1.5f)
            canvas.drawText(label, s.x, s.y - roomRadius - 6f, labelPaint)
        }

        // ── Draw A* path ──
        if (navigationPath.size >= 2) {
            pathPaint.strokeWidth = 10f * scaleFactor
            val path = Path()
            val first = toScreen(navigationPath[0][0].toFloat(), navigationPath[0][1].toFloat())
            path.moveTo(first.x, first.y)
            for (i in 1 until navigationPath.size) {
                val s = toScreen(navigationPath[i][0].toFloat(), navigationPath[i][1].toFloat())
                path.lineTo(s.x, s.y)
            }
            canvas.drawPath(path, pathPaint)
        }

        // ── Draw user position ──
        userPosition?.let { (ux, uy) ->
            val s = toScreen(ux, uy)
            val dotRadius = 16f * scaleFactor
            canvas.drawCircle(s.x, s.y, dotRadius, userPaint)
            canvas.drawCircle(s.x, s.y, dotRadius + 8f * scaleFactor, userRingPaint)
        }
    }
}
