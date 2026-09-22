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

data class PollRecord(
    val date: String,
    val institute: String,
    val sample: Int,
    val method: String,
    val registration: String?,
    val verifiedTse: Boolean,
    val candidates: Map<String, Double>
)

data class CandidateOffsetDiagnostic(
    val id: String,
    val name: String,
    val comparisons: Int,
    val meanOffset: Double,
    val meanAbsoluteDeviation: Double
)

data class SourceDiagnostic(
    val label: String,
    val pollCount: Int,
    val comparisonCount: Int,
    val meanOffset: Double,
    val meanAbsoluteDeviation: Double,
    val residualSd: Double,
    val candidateOffsets: List<CandidateOffsetDiagnostic>
)

data class RollingValidation(
    val status: String,
    val caseCount: Int,
    val comparisonCount: Int,
    val meanAbsoluteError: Double?,
    val medianAbsoluteError: Double?,
    val simpleMeanAbsoluteError: Double?,
    val errorDifferenceVsSimple: Double?,
    val intervalCoverage: Double?,
    val target: String?,
    val note: String?
)

data class CalibrationData(
    val generatedAt: String,
    val correctionApplied: Boolean,
    val correctionPolicy: String,
    val peerWindowDays: Int,
    val instituteDiagnostics: List<SourceDiagnostic>,
    val methodDiagnostics: List<SourceDiagnostic>,
    val rollingValidation: RollingValidation,
    val historicalBacktestStatus: String,
    val historicalBacktestNote: String
)

data class HistoricalHorizon(
    val daysBeforeElection: Int,
    val pollCount: Int,
    val instituteCount: Int,
    val weightedMae: Double?,
    val simpleMae: Double?
)

data class HistoricalBacktestStudy(
    val year: Int,
    val round: String,
    val status: String,
    val pollCountTotal: Int,
    val averageWeightedMae: Double?,
    val averageSimpleMae: Double?,
    val correctionApplied: Boolean,
    val note: String,
    val horizons: List<HistoricalHorizon>
)

data class ModelStudyMetric(
    val year: Int,
    val comparisonCount: Int,
    val meanAbsoluteError: Double?
)

data class ModelVariantDiagnostic(
    val id: String,
    val label: String,
    val decayDays: Double?,
    val sampleWeight: Boolean,
    val repeatPenalty: Boolean,
    val historicalComparisonCount: Int,
    val historicalMae: Double?,
    val historicalStudies: List<ModelStudyMetric>,
    val currentCaseCount: Int,
    val currentComparisonCount: Int,
    val currentMae: Double?,
    val historicalDeltaVsProduction: Double?,
    val currentDeltaVsProduction: Double?,
    val promotionCandidate: Boolean
)

data class ModelLabData(
    val productionModelId: String,
    val automaticPromotion: Boolean,
    val promotionPolicy: String,
    val promotionCandidates: List<String>,
    val variants: List<ModelVariantDiagnostic>,
    val note: String
)

data class DashboardData(
    val snapshot: Snapshot,
    val history: List<HistoryPoint>,
    val polls: List<PollRecord>,
    val calibration: CalibrationData,
    val historicalBacktests: List<HistoricalBacktestStudy>,
    val modelLab: ModelLabData?
)
