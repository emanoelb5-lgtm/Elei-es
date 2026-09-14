package br.com.eleicoes.termometro

import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

class ElectionRepository {
    private val base = "https://raw.githubusercontent.com/emanoelb5-lgtm/Elei-es/main/data"

    fun load(): DashboardData {
        val nonce = System.currentTimeMillis()
        val latest = getJson("$base/latest.json?t=$nonce")
        val history = getJson("$base/history.json?t=$nonce")
        return DashboardData(parseSnapshot(JSONObject(latest)), parseHistory(JSONArray(history)))
    }

    private fun getJson(address: String): String {
        val connection = (URL(address).openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 12_000
            readTimeout = 12_000
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
        val candidates = root.getJSONArray("candidates").let { array ->
            List(array.length()) { i ->
                val item = array.getJSONObject(i)
                Candidate(
                    id = item.getString("id"),
                    name = item.getString("name"),
                    pollingSupport = item.optDouble("pollingSupport", 0.0),
                    marketProbability = if (item.isNull("marketProbability")) null else item.optDouble("marketProbability"),
                    winProbability = item.optDouble("winProbability", 0.0),
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
        return Snapshot(
            generatedAt = root.getString("generatedAt"),
            electionDate = root.optString("electionDate", "2026-10-04"),
            daysToElection = root.optInt("daysToElection", 0),
            confidence = root.optString("confidence", "experimental"),
            candidates = candidates.sortedByDescending { it.winProbability },
            sources = sources,
            note = root.optString("note", "Estimativa experimental; não é pesquisa eleitoral nem previsão oficial.")
        )
    }

    private fun parseHistory(array: JSONArray): List<HistoryPoint> =
        List(array.length()) { i ->
            val item = array.getJSONObject(i)
            HistoryPoint(
                generatedAt = item.getString("generatedAt"),
                probabilities = readDoubleMap(item.optJSONObject("probabilities")),
                pollingSupport = readDoubleMap(item.optJSONObject("pollingSupport")),
                marketProbabilities = readDoubleMap(item.optJSONObject("marketProbabilities")),
                origin = item.optString("origin", "live"),
                pollCount = item.optInt("pollCount", 0),
                sourceNote = item.optString("sourceNote").takeIf { it.isNotBlank() }
            )
        }.sortedBy { it.generatedAt }

    private fun readDoubleMap(obj: JSONObject?): Map<String, Double> {
        if (obj == null) return emptyMap()
        val result = mutableMapOf<String, Double>()
        obj.keys().forEach { key -> result[key] = obj.optDouble(key, 0.0) }
        return result
    }
}
