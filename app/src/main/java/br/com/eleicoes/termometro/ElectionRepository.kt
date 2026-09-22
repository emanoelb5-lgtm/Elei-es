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
        return DashboardData(
            snapshot = parseSnapshot(JSONObject(latest)),
            history = parseHistory(JSONArray(history)),
            polls = parsePolls(JSONObject(polls)),
            calibration = parseCalibration(JSONObject(calibration))
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
                    instituteCount = scenario.optInt("instituteCount", 0)
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
                candidates = readDoubleMap(item.optJSONObject("candidates"))
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
                intervalCoverage = if (rolling.isNull("intervalCoverage")) null else rolling.optDouble("intervalCoverage"),
                target = rolling.optString("target").takeIf { it.isNotBlank() },
                note = rolling.optString("note").takeIf { it.isNotBlank() }
            ),
            historicalBacktestStatus = historical.optString("status", "not-applied"),
            historicalBacktestNote = historical.optString("note")
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