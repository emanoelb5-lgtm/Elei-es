package br.com.eleicoes.termometro

import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

class ElectionRepository {
    private val base = "https://raw.githubusercontent.com/emanoelb5-lgtm/Elei-es/main/data"

    fun load(): DashboardData {
        val nonce = System.currentTimeMillis()
        val latest = getJson("$base/analytics.json?t=$nonce")
        val history = getJson("$base/analytics-history.json?t=$nonce")
        val polls = getJson("$base/polls.json?t=$nonce")
        val calibration = getJson("$base/calibration.json?t=$nonce")
        val historicalBacktest = getJson("$base/historical-backtest.json?t=$nonce")
        val modelLab = runCatching { getJson("$base/model-lab.json?t=$nonce") }.getOrNull()
        return DashboardData(
            snapshot = parseSnapshot(JSONObject(latest)),
            history = parseHistory(JSONArray(history)),
            polls = parsePolls(JSONObject(polls)),
            calibration = parseCalibration(JSONObject(calibration)),
            historicalBacktests = parseHistoricalBacktests(JSONObject(historicalBacktest)),
            modelLab = modelLab?.let { parseModelLab(JSONObject(it)) }
        )
    }

    private fun getJson(address: String): String {
        val connection = (URL(address).openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 15_000
            readTimeout = 15_000
            setRequestProperty("Accept", "application/json")
            setRequestProperty("Cache-Control", "no-cache, no-store, max-age=0")
            setRequestProperty("Pragma", "no-cache")
        }
        try {
            if (connection.responseCode !in 200..299) error("HTTP ${connection.responseCode}")
            return connection.inputStream.bufferedReader().use { it.readText() }
        } finally {
            connection.disconnect()
        }
    }

    private fun parseResponseComposition(obj: JSONObject?): ResponseComposition {
        val root = obj ?: JSONObject()
        return ResponseComposition(
            available = root.optBoolean("available", false),
            candidateShare = if (root.isNull("candidateShare")) null else root.optDouble("candidateShare"),
            categories = readDoubleMap(root.optJSONObject("categories")),
            residualUnclassified = if (root.isNull("residualUnclassified")) null else root.optDouble("residualUnclassified"),
            pollCount = root.optInt("pollCount", 0),
            note = root.optString("note")
        )
    }

    private fun parseSensitivity(obj: JSONObject?): SensitivityData {
        val root = obj ?: JSONObject()
        val candidatesObj = root.optJSONObject("candidates") ?: JSONObject()
        val candidates = mutableMapOf<String, CandidateSensitivity>()
        candidatesObj.keys().forEach { id ->
            val item = candidatesObj.optJSONObject(id) ?: return@forEach
            candidates[id] = CandidateSensitivity(
                baseline = item.optDouble("baseline", 0.0),
                leaveOneOutLow = item.optDouble("leaveOneOutLow", 0.0),
                leaveOneOutHigh = item.optDouble("leaveOneOutHigh", 0.0),
                maxLeaveOneOutShift = item.optDouble("maxLeaveOneOutShift", 0.0),
                support14Days = if (item.isNull("support14Days")) null else item.optDouble("support14Days"),
                difference14Vs30 = if (item.isNull("difference14Vs30")) null else item.optDouble("difference14Vs30")
            )
        }
        return SensitivityData(
            status = root.optString("status", "insufficient-data"),
            pollCount = root.optInt("pollCount", 0),
            maxLeaveOneOutShift = if (root.isNull("maxLeaveOneOutShift")) null else root.optDouble("maxLeaveOneOutShift"),
            stability = root.optString("stability").takeIf { it.isNotBlank() },
            candidates = candidates,
            note = root.optString("note")
        )
    }

    private fun parseInfluence(obj: JSONObject?): InfluenceData {
        val root = obj ?: JSONObject()
        val pollsArray = root.optJSONArray("polls") ?: JSONArray()
        val institutesArray = root.optJSONArray("institutes") ?: JSONArray()

        val polls = List(pollsArray.length()) { i ->
            val item = pollsArray.getJSONObject(i)
            PollInfluence(
                date = item.optString("date"),
                institute = item.optString("institute", "Instituto não identificado"),
                sample = item.optInt("sample", 0),
                method = item.optString("method", "não identificado"),
                registration = item.optString("registration").takeIf { it.isNotBlank() && it != "null" },
                verifiedTse = item.optBoolean("verifiedTse", false),
                maxAbsoluteShift = item.optDouble("maxAbsoluteShift", 0.0),
                meanAbsoluteShift = item.optDouble("meanAbsoluteShift", 0.0),
                candidateShifts = readDoubleMap(item.optJSONObject("candidateShifts")),
                peerComparisonCount = item.optInt("peerComparisonCount", 0),
                meanPeerDeviation = if (item.isNull("meanPeerDeviation")) null else item.optDouble("meanPeerDeviation"),
                atypicalSignal = item.optBoolean("atypicalSignal", false)
            )
        }

        val institutes = List(institutesArray.length()) { i ->
            val item = institutesArray.getJSONObject(i)
            InstituteInfluence(
                institute = item.optString("institute", "Instituto não identificado"),
                pollCount = item.optInt("pollCount", 0),
                maxAbsoluteShift = item.optDouble("maxAbsoluteShift", 0.0),
                meanAbsoluteShift = item.optDouble("meanAbsoluteShift", 0.0),
                candidateShifts = readDoubleMap(item.optJSONObject("candidateShifts"))
            )
        }

        return InfluenceData(
            status = root.optString("status", "insufficient-data"),
            pollCount = root.optInt("pollCount", 0),
            instituteCount = root.optInt("instituteCount", 0),
            peerWindowDays = root.optInt("peerWindowDays", 10),
            atypicalThreshold = if (root.isNull("atypicalThreshold")) null else root.optDouble("atypicalThreshold"),
            polls = polls,
            institutes = institutes,
            correctionApplied = root.optBoolean("correctionApplied", false),
            note = root.optString("note")
        )
    }

    private fun parseUncertainty(obj: JSONObject?): UncertaintyData {
        val root = obj ?: JSONObject()
        val candidatesObj = root.optJSONObject("candidates") ?: JSONObject()
        val candidates = mutableMapOf<String, CandidateUncertainty>()

        candidatesObj.keys().forEach { id ->
            val item = candidatesObj.optJSONObject(id) ?: return@forEach
            candidates[id] = CandidateUncertainty(
                support = item.optDouble("support", 0.0),
                modelLow = item.optDouble("modelLow", 0.0),
                modelHigh = item.optDouble("modelHigh", 0.0),
                bootstrapP10 = if (item.isNull("bootstrapP10")) null else item.optDouble("bootstrapP10"),
                bootstrapP50 = if (item.isNull("bootstrapP50")) null else item.optDouble("bootstrapP50"),
                bootstrapP90 = if (item.isNull("bootstrapP90")) null else item.optDouble("bootstrapP90"),
                empiricalErrorQ80 = if (item.isNull("empiricalErrorQ80")) null else item.optDouble("empiricalErrorQ80"),
                advancedLow = item.optDouble("advancedLow", 0.0),
                advancedHigh = item.optDouble("advancedHigh", 0.0),
                advancedHalfWidth = item.optDouble("advancedHalfWidth", 0.0)
            )
        }

        return UncertaintyData(
            status = root.optString("status", "insufficient-data"),
            bootstrapDraws = root.optInt("bootstrapDraws", 0),
            empiricalErrorQuantileUsed = root.optString("empiricalErrorQuantileUsed"),
            empiricalErrorQ80 = if (root.isNull("empiricalErrorQ80")) null else root.optDouble("empiricalErrorQ80"),
            empiricalErrorQ90 = if (root.isNull("empiricalErrorQ90")) null else root.optDouble("empiricalErrorQ90"),
            candidates = candidates,
            note = root.optString("note")
        )
    }

    private fun parseSnapshot(root: JSONObject): Snapshot {
        val q = root.optJSONObject("quality") ?: JSONObject()
        val quality = QualityInfo(
            pollCount = q.optInt("pollCount", 0),
            instituteCount = q.optInt("instituteCount", 0),
            methodCount = q.optInt("methodCount", 0),
            registrationCount = q.optInt("registrationCount", 0),
            verifiedTseCount = q.optInt("verifiedTseCount", 0),
            averageAgeDays = q.optDouble("averageAgeDays", 0.0),
            effectivePolls = q.optDouble("effectivePolls", 0.0),
            confidence = q.optString("confidence", "limitada")
        )

        val candidates = root.getJSONArray("candidates").let { array ->
            List(array.length()) { i ->
                val item = array.getJSONObject(i)
                Candidate(
                    id = item.getString("id"),
                    name = item.getString("name"),
                    pollingSupport = item.optDouble("pollingSupport", 0.0),
                    intervalLow = item.optDouble("intervalLow", 0.0),
                    intervalHigh = item.optDouble("intervalHigh", 0.0),
                    modelIntervalLow = item.optDouble("modelIntervalLow", item.optDouble("intervalLow", 0.0)),
                    modelIntervalHigh = item.optDouble("modelIntervalHigh", item.optDouble("intervalHigh", 0.0)),
                    marketSignal = if (item.isNull("marketSignal")) null else item.optDouble("marketSignal"),
                    change = item.optDouble("change", 0.0),
                    trend = item.optString("trend", "estável")
                )
            }
        }

        val sources = root.optJSONArray("sources")?.let { array ->
            List(array.length()) { i ->
                val item = array.getJSONObject(i)
                SourceInfo(
                    id = item.optString("id"),
                    label = item.optString("label"),
                    type = item.optString("type"),
                    status = item.optString("status", "indisponível"),
                    updatedAt = item.optString("updatedAt").takeIf { it.isNotBlank() },
                    url = item.optString("url")
                )
            }
        } ?: emptyList()

        val runoff = root.optJSONArray("runoffScenarios")?.let { array ->
            List(array.length()) { i ->
                val scenario = array.getJSONObject(i)
                val rc = scenario.optJSONArray("candidates") ?: JSONArray()
                RunoffScenario(
                    id = scenario.optString("id"),
                    label = scenario.optString("label"),
                    candidates = List(rc.length()) { j ->
                        val c = rc.getJSONObject(j)
                        RunoffCandidate(
                            id = c.optString("id"),
                            name = c.optString("name"),
                            support = c.optDouble("support", 0.0),
                            intervalLow = c.optDouble("intervalLow", 0.0),
                            intervalHigh = c.optDouble("intervalHigh", 0.0)
                        )
                    },
                    pollCount = scenario.optInt("pollCount", 0),
                    instituteCount = scenario.optInt("instituteCount", 0),
                    responseComposition = parseResponseComposition(scenario.optJSONObject("responseComposition")),
                    pairNormalized = readDoubleMap(scenario.optJSONObject("pairNormalized")),
                    pairNormalizationNote = scenario.optString("pairNormalizationNote")
                )
            }
        } ?: emptyList()

        return Snapshot(
            generatedAt = root.getString("generatedAt"),
            electionDate = root.optString("electionDate", "2026-10-04"),
            daysToElection = root.optInt("daysToElection", 0),
            quality = quality,
            candidates = candidates,
            sources = sources,
            runoffScenarios = runoff,
            responseComposition = parseResponseComposition(root.optJSONObject("responseComposition")),
            sensitivity = parseSensitivity(root.optJSONObject("sensitivity")),
            influence = parseInfluence(root.optJSONObject("influence")),
            uncertainty = parseUncertainty(root.optJSONObject("uncertainty")),
            note = root.optString("note", "Leitura estatística de pesquisas públicas.")
        )
    }

    private fun parseHistory(array: JSONArray): List<HistoryPoint> =
        List(array.length()) { i ->
            val item = array.getJSONObject(i)
            HistoryPoint(
                generatedAt = item.getString("generatedAt"),
                pollingSupport = readDoubleMap(item.optJSONObject("pollingSupport")),
                intervals = readIntervalMap(item.optJSONObject("intervals")),
                pollCount = item.optInt("pollCount", 0),
                instituteCount = item.optInt("instituteCount", 0),
                verifiedTseCount = item.optInt("verifiedTseCount", 0),
                origin = item.optString("origin", "live")
            )
        }.sortedBy { it.generatedAt }

    private fun parsePolls(root: JSONObject): List<PollRecord> {
        val array = root.optJSONArray("firstRound") ?: JSONArray()
        return List(array.length()) { i ->
            val item = array.getJSONObject(i)
            PollRecord(
                date = item.optString("date"),
                institute = item.optString("institute", "Instituto não identificado"),
                sample = item.optInt("sample", 0),
                method = item.optString("method", "não identificado"),
                registration = item.optString("registration").takeIf { it.isNotBlank() && it != "null" },
                verifiedTse = item.optBoolean("verifiedTse", false),
                candidates = readDoubleMap(item.optJSONObject("candidates")),
                nonCandidate = readDoubleMap(item.optJSONObject("nonCandidate"))
            )
        }.sortedByDescending { it.date }
    }

    private fun parseCalibration(root: JSONObject): CalibrationData {
        fun parseDiagnosticArray(array: JSONArray?): List<SourceDiagnostic> {
            if (array == null) return emptyList()
            return List(array.length()) { i ->
                val item = array.getJSONObject(i)
                val offsetsObj = item.optJSONObject("candidateOffsets") ?: JSONObject()
                val offsets = mutableListOf<CandidateOffsetDiagnostic>()
                offsetsObj.keys().forEach { id ->
                    val value = offsetsObj.optJSONObject(id) ?: return@forEach
                    offsets += CandidateOffsetDiagnostic(
                        id = id,
                        name = value.optString("name", id),
                        comparisons = value.optInt("comparisons", 0),
                        meanOffset = value.optDouble("meanOffset", 0.0),
                        meanAbsoluteDeviation = value.optDouble("meanAbsoluteDeviation", 0.0)
                    )
                }
                SourceDiagnostic(
                    label = item.optString("label"),
                    pollCount = item.optInt("pollCount", 0),
                    comparisonCount = item.optInt("comparisonCount", 0),
                    meanOffset = item.optDouble("meanOffset", 0.0),
                    meanAbsoluteDeviation = item.optDouble("meanAbsoluteDeviation", 0.0),
                    residualSd = item.optDouble("residualSd", 0.0),
                    candidateOffsets = offsets.sortedBy { it.name }
                )
            }
        }

        val source = root.optJSONObject("sourceDiagnostics") ?: JSONObject()
        val rolling = root.optJSONObject("rollingValidation") ?: JSONObject()
        val historical = root.optJSONObject("historicalElectionBacktest") ?: JSONObject()

        return CalibrationData(
            generatedAt = root.optString("generatedAt"),
            correctionApplied = root.optBoolean("correctionApplied", false),
            correctionPolicy = root.optString("correctionPolicy"),
            peerWindowDays = source.optInt("peerWindowDays", 10),
            instituteDiagnostics = parseDiagnosticArray(source.optJSONArray("institutes")),
            methodDiagnostics = parseDiagnosticArray(source.optJSONArray("methods")),
            rollingValidation = RollingValidation(
                status = rolling.optString("status", "insufficient-data"),
                caseCount = rolling.optInt("caseCount", 0),
                comparisonCount = rolling.optInt("comparisonCount", 0),
                meanAbsoluteError = if (rolling.isNull("meanAbsoluteError")) null else rolling.optDouble("meanAbsoluteError"),
                medianAbsoluteError = if (rolling.isNull("medianAbsoluteError")) null else rolling.optDouble("medianAbsoluteError"),
                simpleMeanAbsoluteError = if (rolling.isNull("simpleMeanAbsoluteError")) null else rolling.optDouble("simpleMeanAbsoluteError"),
                errorDifferenceVsSimple = if (rolling.isNull("errorDifferenceVsSimple")) null else rolling.optDouble("errorDifferenceVsSimple"),
                intervalCoverage = if (rolling.isNull("intervalCoverage")) null else rolling.optDouble("intervalCoverage"),
                absoluteErrorQuantiles = readDoubleMap(rolling.optJSONObject("absoluteErrorQuantiles")),
                target = rolling.optString("target").takeIf { it.isNotBlank() },
                note = rolling.optString("note").takeIf { it.isNotBlank() }
            ),
            historicalBacktestStatus = historical.optString("status", "not-applied"),
            historicalBacktestNote = historical.optString("note")
        )
    }

    private fun parseHistoricalBacktests(root: JSONObject): List<HistoricalBacktestStudy> {
        val array = root.optJSONArray("studies") ?: JSONArray()
        return List(array.length()) { i ->
            val item = array.getJSONObject(i)
            val hs = item.optJSONArray("horizons") ?: JSONArray()
            HistoricalBacktestStudy(
                year = item.optInt("year", 0),
                round = item.optString("round"),
                status = item.optString("status"),
                pollCountTotal = item.optInt("pollCountTotal", 0),
                averageWeightedMae = if (item.isNull("averageWeightedMae")) null else item.optDouble("averageWeightedMae"),
                averageSimpleMae = if (item.isNull("averageSimpleMae")) null else item.optDouble("averageSimpleMae"),
                correctionApplied = item.optBoolean("correctionApplied", false),
                note = item.optString("note"),
                horizons = List(hs.length()) { j ->
                    val h = hs.getJSONObject(j)
                    HistoricalHorizon(
                        daysBeforeElection = h.optInt("daysBeforeElection", 0),
                        pollCount = h.optInt("pollCount", 0),
                        instituteCount = h.optInt("instituteCount", 0),
                        weightedMae = if (h.isNull("weightedMae")) null else h.optDouble("weightedMae"),
                        simpleMae = if (h.isNull("simpleMae")) null else h.optDouble("simpleMae")
                    )
                }
            )
        }
    }

    private fun parseModelLab(root: JSONObject): ModelLabData {
        val variantsArray = root.optJSONArray("variants") ?: JSONArray()
        val variants = List(variantsArray.length()) { i ->
            val item = variantsArray.getJSONObject(i)
            val params = item.optJSONObject("parameters") ?: JSONObject()
            val historical = item.optJSONObject("historical") ?: JSONObject()
            val studiesArray = historical.optJSONArray("studies") ?: JSONArray()
            val current = item.optJSONObject("currentRolling") ?: JSONObject()
            val delta = item.optJSONObject("deltaVsProduction") ?: JSONObject()

            ModelVariantDiagnostic(
                id = item.optString("id"),
                label = item.optString("label"),
                decayDays = if (params.isNull("decayDays")) null else params.optDouble("decayDays"),
                sampleWeight = params.optBoolean("sampleWeight", false),
                repeatPenalty = params.optBoolean("repeatPenalty", false),
                historicalComparisonCount = historical.optInt("comparisonCount", 0),
                historicalMae = if (historical.isNull("pooledMeanAbsoluteError")) null else historical.optDouble("pooledMeanAbsoluteError"),
                historicalStudies = List(studiesArray.length()) { j ->
                    val study = studiesArray.getJSONObject(j)
                    ModelStudyMetric(
                        year = study.optInt("year", 0),
                        comparisonCount = study.optInt("comparisonCount", 0),
                        meanAbsoluteError = if (study.isNull("meanAbsoluteError")) null else study.optDouble("meanAbsoluteError")
                    )
                },
                currentCaseCount = current.optInt("caseCount", 0),
                currentComparisonCount = current.optInt("comparisonCount", 0),
                currentMae = if (current.isNull("meanAbsoluteError")) null else current.optDouble("meanAbsoluteError"),
                historicalDeltaVsProduction = if (delta.isNull("historicalMae")) null else delta.optDouble("historicalMae"),
                currentDeltaVsProduction = if (delta.isNull("currentRollingMae")) null else delta.optDouble("currentRollingMae"),
                promotionCandidate = item.optBoolean("promotionCandidate", false)
            )
        }

        val candidatesArray = root.optJSONArray("promotionCandidates") ?: JSONArray()
        val promotionCandidates = List(candidatesArray.length()) { i -> candidatesArray.optString(i) }

        return ModelLabData(
            productionModelId = root.optString("productionModelId", "current-v04"),
            automaticPromotion = root.optBoolean("automaticPromotion", false),
            promotionPolicy = root.optString("promotionPolicy"),
            promotionCandidates = promotionCandidates,
            variants = variants,
            note = root.optString("note")
        )
    }

    private fun readDoubleMap(obj: JSONObject?): Map<String, Double> {
        if (obj == null) return emptyMap()
        val result = mutableMapOf<String, Double>()
        obj.keys().forEach { key -> result[key] = obj.optDouble(key, 0.0) }
        return result
    }

    private fun readIntervalMap(obj: JSONObject?): Map<String, IntervalBand> {
        if (obj == null) return emptyMap()
        val result = mutableMapOf<String, IntervalBand>()
        obj.keys().forEach { key ->
            val band = obj.optJSONObject(key) ?: return@forEach
            result[key] = IntervalBand(
                low = band.optDouble("low", 0.0),
                high = band.optDouble("high", 0.0)
            )
        }
        return result
    }
}