package br.com.eleicoes.termometro

import java.time.Duration
import java.time.Instant
import kotlin.math.exp
import kotlin.math.sqrt

data class ForecastCurvePoint(
    val instant: Instant,
    val probabilities: Map<String, Double>,
    val projected: Boolean,
    val historicalReconstruction: Boolean = false
)

data class CandidateProjection(
    val id: String,
    val name: String,
    val current: Double,
    val projectedElection: Double,
    val delta: Double,
    val slopePerDay: Double
)

data class ForecastAnalysis(
    val periodDays: Int,
    val availableSpanDays: Double,
    val actual: List<ForecastCurvePoint>,
    val projected: List<ForecastCurvePoint>,
    val candidates: List<CandidateProjection>,
    val confidence: String,
    val historicalPoints: Int,
    val livePoints: Int
)

object ForecastEngine {
    fun analyze(data: DashboardData, periodDays: Int): ForecastAnalysis {
        val snapshotInstant = runCatching { Instant.parse(data.snapshot.generatedAt) }.getOrElse { Instant.now() }
        val parsed = data.history.mapNotNull { point ->
            runCatching { Instant.parse(point.generatedAt) }.getOrNull()?.let { it to point }
        }.sortedBy { it.first }

        val latest = maxOf(parsed.lastOrNull()?.first ?: snapshotInstant, snapshotInstant)
        val cutoff = latest.minus(Duration.ofDays(periodDays.toLong()))
        val filtered = parsed.filter { !it.first.isBefore(cutoff) && !it.first.isAfter(snapshotInstant.plus(Duration.ofMinutes(5))) }

        // Um ponto a cada 6 horas evita que dezenas de leituras idênticas de 15 min
        // deem peso exagerado à regressão. O histórico retroativo usa no máximo um
        // ponto por dia, então permanece integralmente representado.
        val buckets = linkedMapOf<Long, Pair<Instant, HistoryPoint>>()
        filtered.forEach { pair -> buckets[pair.first.epochSecond / 21_600L] = pair }
        var actual = buckets.values.map { (instant, point) ->
            ForecastCurvePoint(
                instant = instant,
                probabilities = point.probabilities,
                projected = false,
                historicalReconstruction = point.origin == "historical-reconstruction"
            )
        }

        val currentMap = data.snapshot.candidates.associate { it.id to it.winProbability }
        if (actual.isEmpty() || Duration.between(actual.last().instant, snapshotInstant).abs().toMinutes() >= 5) {
            actual = actual + ForecastCurvePoint(snapshotInstant, currentMap, projected = false)
        } else {
            actual = actual.dropLast(1) + ForecastCurvePoint(snapshotInstant, currentMap, projected = false)
        }

        val span = if (actual.size >= 2) {
            Duration.between(actual.first().instant, actual.last().instant).toMinutes().coerceAtLeast(0) / 1440.0
        } else 0.0

        val slopes = data.snapshot.candidates.associate { candidate ->
            candidate.id to regressionSlope(actual, candidate.id)
        }

        val horizon = data.snapshot.daysToElection.coerceAtLeast(0)
        val projected = (1..horizon).map { day ->
            // Amortecimento exponencial: a tendência recente influencia o futuro,
            // mas não cresce indefinidamente como numa extrapolação linear pura.
            val dampedDays = 10.0 * (1.0 - exp(-day / 10.0))
            val raw = data.snapshot.candidates.associate { candidate ->
                val value = candidate.winProbability + (slopes[candidate.id] ?: 0.0) * dampedDays
                candidate.id to value.coerceIn(0.01, 99.99)
            }
            val total = raw.values.sum().takeIf { it > 0.0 } ?: 1.0
            val normalized = raw.mapValues { (_, value) -> value * 100.0 / total }
            ForecastCurvePoint(snapshotInstant.plus(Duration.ofDays(day.toLong())), normalized, projected = true)
        }

        val electionMap = projected.lastOrNull()?.probabilities ?: currentMap
        val summaries = data.snapshot.candidates.take(5).map { candidate ->
            val future = electionMap[candidate.id] ?: candidate.winProbability
            CandidateProjection(
                id = candidate.id,
                name = candidate.name,
                current = candidate.winProbability,
                projectedElection = future,
                delta = future - candidate.winProbability,
                slopePerDay = slopes[candidate.id] ?: 0.0
            )
        }

        val historicalPoints = actual.count { it.historicalReconstruction }
        val livePoints = actual.size - historicalPoints
        val confidence = when {
            span >= 20.0 && actual.size >= 20 -> "média"
            span >= 5.0 && actual.size >= 8 -> "baixa a média"
            else -> "baixa"
        }

        return ForecastAnalysis(
            periodDays = periodDays,
            availableSpanDays = span,
            actual = actual,
            projected = projected,
            candidates = summaries,
            confidence = confidence,
            historicalPoints = historicalPoints,
            livePoints = livePoints
        )
    }

    private fun regressionSlope(points: List<ForecastCurvePoint>, candidateId: String): Double {
        val usable = points.mapNotNull { point ->
            point.probabilities[candidateId]?.let { point.instant to it }
        }
        if (usable.size < 2) return 0.0

        val start = usable.first().first
        val xs = usable.map { Duration.between(start, it.first).toMinutes() / 1440.0 }
        val ys = usable.map { it.second }
        val maxX = xs.maxOrNull() ?: 0.0
        if (maxX < 0.25) return 0.0

        val weights = xs.map { x -> 0.45 + 0.55 * (x / maxX).coerceIn(0.0, 1.0) }
        val weightSum = weights.sum().takeIf { it > 0.0 } ?: return 0.0
        val meanX = xs.indices.sumOf { xs[it] * weights[it] } / weightSum
        val meanY = ys.indices.sumOf { ys[it] * weights[it] } / weightSum
        val numerator = xs.indices.sumOf { (xs[it] - meanX) * (ys[it] - meanY) * weights[it] }
        val denominator = xs.indices.sumOf { (xs[it] - meanX) * (xs[it] - meanX) * weights[it] }
        if (denominator <= 1e-9) return 0.0

        val rawSlope = numerator / denominator
        val variance = ys.sumOf { (it - meanY) * (it - meanY) } / ys.size.coerceAtLeast(1)
        val sd = sqrt(variance)
        val cap = (0.15 + sd * 0.90).coerceIn(0.15, 1.50)
        return rawSlope.coerceIn(-cap, cap)
    }
}
