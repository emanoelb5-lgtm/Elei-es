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
        return DashboardData(parseSnapshot(JSONObject(latest)), parseHistory(JSONArray(history)))
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