package br.com.eleicoes.termometro

data class Candidate(
    val id: String,
    val name: String,
    val pollingSupport: Double,
    val intervalLow: Double,
    val intervalHigh: Double,
    val marketSignal: Double?,
    val change: Double,
    val trend: String
)

data class SourceInfo(
    val id: String,
    val label: String,
    val type: String,
    val status: String,
    val updatedAt: String?,
    val url: String
)

data class QualityInfo(
    val pollCount: Int,
    val instituteCount: Int,
    val methodCount: Int,
    val registrationCount: Int,
    val verifiedTseCount: Int,
    val averageAgeDays: Double,
    val effectivePolls: Double,
    val confidence: String
)

data class RunoffCandidate(
    val id: String,
    val name: String,
    val support: Double,
    val intervalLow: Double,
    val intervalHigh: Double
)

data class RunoffScenario(
    val id: String,
    val label: String,
    val candidates: List<RunoffCandidate>,
    val pollCount: Int,
    val instituteCount: Int
)

data class Snapshot(
    val generatedAt: String,
    val electionDate: String,
    val daysToElection: Int,
    val quality: QualityInfo,
    val candidates: List<Candidate>,
    val sources: List<SourceInfo>,
    val runoffScenarios: List<RunoffScenario>,
    val note: String
)

data class IntervalBand(
    val low: Double,
    val high: Double
)

data class HistoryPoint(
    val generatedAt: String,
    val pollingSupport: Map<String, Double>,
    val intervals: Map<String, IntervalBand>,
    val pollCount: Int,
    val instituteCount: Int,
    val verifiedTseCount: Int,
    val origin: String = "live"
)

data class DashboardData(
    val snapshot: Snapshot,
    val history: List<HistoryPoint>
)
