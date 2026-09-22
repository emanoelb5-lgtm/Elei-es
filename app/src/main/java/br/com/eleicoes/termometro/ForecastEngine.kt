package br.com.eleicoes.termometro

import java.time.Duration
import java.time.Instant
import kotlin.math.sqrt

data class TrendCurvePoint(
    val instant: Instant,
    val support: Map<String, Double>,
    val historicalReconstruction: Boolean
)

data class CandidateTrend(
    val id: String,
    val name: String,
    val current: Double,
    val changeInWindow: Double,
    val slopePerDay: Double
)

data class TrendAnalysis(
    val periodDays: Int,
    val availableSpanDays: Double,
    val points: List<TrendCurvePoint>,
    val candidates: List<CandidateTrend>,
    val confidence: String,
    val historicalPoints: Int,
    val livePoints: Int
)

object TrendEngine {
    fun analyze(data: DashboardData, periodDays: Int): TrendAnalysis {
        val snapshotInstant = runCatching { Instant.parse(data.snapshot.generatedAt) }.getOrElse { Instant.now() }
        val parsed = data.history.mapNotNull { point ->
            runCatching { Instant.parse(point.generatedAt) }.getOrNull()?.let { it to point }
        }.sortedBy { it.first }

        val cutoff = snapshotInstant.minus(Duration.ofDays(periodDays.toLong()))
        val filtered = parsed.filter { !it.first.isBefore(cutoff) && !it.first.isAfter(snapshotInstant.plus(Duration.ofMinutes(5))) }

        // Um ponto por dia para o histórico reconstruído e, no máximo, um ponto
        // a cada 6h para leituras ao vivo.
        val buckets = linkedMapOf<Long, Pair<Instant, HistoryPoint>>()
        filtered.forEach { pair ->
            val divisor = if (pair.second.origin == "historical-reconstruction") 86_400L else 21_600L
            buckets[pair.first.epochSecond / divisor] = pair
        }

        var points = buckets.values.map { (instant, point) ->
            TrendCurvePoint(
                instant = instant,
                support = point.pollingSupport,
                historicalReconstruction = point.origin == "historical-reconstruction"
            )
        }.sortedBy { it.instant }

        val currentMap = data.snapshot.candidates.associate { it.id to it.pollingSupport }
        if (points.isEmpty() || Duration.between(points.last().instant, snapshotInstant).abs().toMinutes() >= 5) {
            points = points + TrendCurvePoint(snapshotInstant, currentMap, false)
        } else {
            points = points.dropLast(1) + TrendCurvePoint(snapshotInstant, currentMap, false)
        }

        val span = if (points.size >= 2) {
            Duration.between(points.first().instant, points.last().instant).toMinutes().coerceAtLeast(0) / 1440.0
        } else 0.0

        val trends = data.snapshot.candidates.map { candidate ->
            val usable = points.mapNotNull { p -> p.support[candidate.id]?.let { p.instant to it } }
            val first = usable.firstOrNull()?.second ?: candidate.pollingSupport
            CandidateTrend(
                id = candidate.id,
                name = candidate.name,
                current = candidate.pollingSupport,
                changeInWindow = candidate.pollingSupport - first,
                slopePerDay = regressionSlope(points, candidate.id)
            )
        }

        val historicalPoints = points.count { it.historicalReconstruction }
        val livePoints = points.size - historicalPoints
        val confidence = when {
            data.snapshot.quality.instituteCount >= 4 && data.snapshot.quality.pollCount >= 8 && span >= 20 -> "boa"
            data.snapshot.quality.instituteCount >= 3 && data.snapshot.quality.pollCount >= 4 && span >= 5 -> "moderada"
            else -> "limitada"
        }

        return TrendAnalysis(
            periodDays = periodDays,
            availableSpanDays = span,
            points = points,
            candidates = trends,
            confidence = confidence,
            historicalPoints = historicalPoints,
            livePoints = livePoints
        )
    }

    private fun regressionSlope(points: List<TrendCurvePoint>, candidateId: String): Double {
        val usable = points.mapNotNull { point ->
            point.support[candidateId]?.let { point.instant to it }
        }
        if (usable.size < 2) return 0.0

        val start = usable.first().first
        val xs = usable.map { Duration.between(start, it.first).toMinutes() / 1440.0 }
        val ys = usable.map { it.second }
        val maxX = xs.maxOrNull() ?: 0.0
        if (maxX < 0.25) return 0.0

        val weights = xs.map { x -> 0.5 + 0.5 * (x / maxX).coerceIn(0.0, 1.0) }
        val sumW = weights.sum().takeIf { it > 0 } ?: return 0.0
        val meanX = xs.indices.sumOf { xs[it] * weights[it] } / sumW
        val meanY = ys.indices.sumOf { ys[it] * weights[it] } / sumW
        val num = xs.indices.sumOf { (xs[it] - meanX) * (ys[it] - meanY) * weights[it] }
        val den = xs.indices.sumOf { (xs[it] - meanX) * (xs[it] - meanX) * weights[it] }
        if (den <= 1e-9) return 0.0

        val raw = num / den
        val variance = ys.sumOf { (it - meanY) * (it - meanY) } / ys.size.coerceAtLeast(1)
        val sd = sqrt(variance)
        val cap = (0.10 + sd * 0.65).coerceIn(0.10, 1.0)
        return raw.coerceIn(-cap, cap)
    }
}
