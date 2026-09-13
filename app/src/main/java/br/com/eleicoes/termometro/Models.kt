package br.com.eleicoes.termometro

data class Candidate(
    val id: String,
    val name: String,
    val pollingSupport: Double,
    val marketProbability: Double?,
    val winProbability: Double,
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

data class Snapshot(
    val generatedAt: String,
    val electionDate: String,
    val daysToElection: Int,
    val confidence: String,
    val candidates: List<Candidate>,
    val sources: List<SourceInfo>,
    val note: String
)

data class HistoryPoint(
    val generatedAt: String,
    val probabilities: Map<String, Double>,
    val pollingSupport: Map<String, Double> = emptyMap(),
    val marketProbabilities: Map<String, Double> = emptyMap()
)

data class DashboardData(
    val snapshot: Snapshot,
    val history: List<HistoryPoint>
)
