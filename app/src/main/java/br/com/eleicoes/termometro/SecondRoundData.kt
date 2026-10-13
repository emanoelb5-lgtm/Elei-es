package br.com.eleicoes.termometro

import android.content.Context
import android.util.AtomicFile
import android.util.Base64
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId

internal val RoundIds = setOf("flavio-bolsonaro", "lula")
internal val RoundZone: ZoneId = ZoneId.of("America/Sao_Paulo")
internal data class RoundCandidate(val id: String, val name: String, val party: String)
internal data class RoundPoll(
    val id: String, val institute: String, val fieldworkStart: String,
    val fieldworkEnd: String, val publishedAt: String?, val sample: Int,
    val method: String, val registration: String?, val basis: String,
    val result: Map<String, Double>, val validResult: Map<String, Double>,
    val nonCandidate: Map<String, Double>, val sourceUrl: String,
    val sourceLabel: String, val origin: String, val marginError: Double?
)
internal data class RoundWeight(val pollId: String, val institute: String, val weightShare: Double, val basisOrigin: String)
internal data class RoundModel(
    val asOf: String, val support: Map<String, Double>, val probability: Map<String, Double>,
    val intervals: Map<String, Pair<Double, Double>>, val weights: List<RoundWeight>,
    val change: Map<String, Double>, val changeSince: String?, val quality: String, val message: String
)
internal data class RoundPoint(
    val date: String, val support: Map<String, Double>,
    val probability: Map<String, Double>, val instituteCount: Int
)
internal data class RoundMarket(val status: String, val values: Map<String, Double>, val updatedAt: String?, val url: String)
internal data class RoundSource(val id: String, val status: String)
internal data class RoundReading(
    val generatedAt: String, val checkedAt: String, val revision: String, val electionDate: String,
    val candidates: List<RoundCandidate>, val polls: List<RoundPoll>, val model: RoundModel?,
    val history: List<RoundPoint>, val market: RoundMarket, val sources: List<RoundSource>,
    val methodology: String
)
internal data class RoundLoad(val reading: RoundReading, val origin: String, val persisted: Boolean = true)

private fun JSONObject.values(key: String): Map<String, Double> =
    optJSONObject(key)?.let { obj -> obj.keys().asSequence().associateWith { obj.getDouble(it) } } ?: emptyMap()

private fun checkValues(values: Map<String, Double>, sum100: Boolean = false) {
    require(values.keys == RoundIds && values.values.all { it.isFinite() && it in 0.0..100.0 })
    require(values.values.sum() in 0.001..101.1)
    if (sum100) require(kotlin.math.abs(values.values.sum() - 100.0) <= 1.1)
}

internal fun parseRoundReading(raw: String, today: LocalDate = LocalDate.now(RoundZone)): RoundReading {
    val root = JSONObject(raw)
    require(root.getInt("schemaVersion") == 2 && root.getString("electionDate") == "2026-10-25")
    val generated = root.getString("generatedAt")
    val checked = root.getString("checkedAt")
    Instant.parse(generated); Instant.parse(checked)
    val array = root.getJSONArray("candidates")
    val candidates = List(array.length()) { i -> array.getJSONObject(i).let {
        RoundCandidate(it.getString("id"), it.getString("name"), it.getString("party"))
    } }
    require(candidates.size == 2 && candidates.map { it.id }.toSet() == RoundIds)
    val rows = root.getJSONArray("polls")
    val polls = List(rows.length()) { i ->
        val row = rows.getJSONObject(i)
        val start = LocalDate.parse(row.getString("fieldworkStart"))
        val end = LocalDate.parse(row.getString("fieldworkEnd"))
        require(start >= LocalDate.of(2026, 10, 5) && start <= end && end <= today && end <= LocalDate.of(2026, 10, 25))
        val published = row.optString("publishedAt").takeIf { it.isNotBlank() && it != "null" }
        published?.let { require(LocalDate.parse(it.take(10)) in end..today) }
        val basis = row.getString("basis")
        require(basis in setOf("total", "valid", "unspecified"))
        val result = row.values("result")
        checkValues(result, basis == "valid")
        val valid = row.values("validResult")
        if (valid.isNotEmpty()) checkValues(valid, true)
        val other = row.values("nonCandidate")
        require(other.values.all { it.isFinite() && it in 0.0..100.0 })
        require(row.getInt("sample") in 1..1_000_000 && row.getString("sourceUrl").startsWith("https://"))
        val margin = row.optDouble("marginError").takeIf { it.isFinite() }
        require(margin == null || margin in 0.01..20.0)
        RoundPoll(row.getString("id"), row.getString("institute"), start.toString(), end.toString(),
            published, row.getInt("sample"), row.optString("method", "Não informado"),
            row.optString("registration").takeIf { it.isNotBlank() && it != "null" },
            basis, result, valid, other, row.getString("sourceUrl"),
            row.optString("sourceLabel", row.getString("institute")), row.optString("origin"), margin)
    }.sortedWith(compareByDescending<RoundPoll> { it.fieldworkEnd }.thenByDescending { it.publishedAt ?: "" })
    require(polls.map { it.id }.distinct().size == polls.size && polls.all { it.id.isNotBlank() && it.institute.isNotBlank() })
    require(root.getInt("pollCount") == polls.size)
    val modelObj = root.optJSONObject("model")
    val model = if (modelObj?.optString("status") == "ok") {
        require(!modelObj.getBoolean("calibrated"))
        val asOf = modelObj.getString("asOf")
        require(LocalDate.parse(asOf) <= today)
        val support = modelObj.values("support")
        val probability = modelObj.values("winProbability")
        checkValues(support, true); checkValues(probability, true)
        val intervals = modelObj.getJSONObject("intervals")
        val ranges = RoundIds.associateWith { id ->
            val range = intervals.getJSONArray(id)
            val low = range.getDouble(0)
            val high = range.getDouble(1)
            require(low.isFinite() && high.isFinite() && low in 0.0..100.0 && high in low..100.0)
            require(support.getValue(id) in low..high)
            low to high
        }
        val weightsObj = modelObj.getJSONArray("rows")
        val weights = List(weightsObj.length()) { i ->
            val row = weightsObj.getJSONObject(i)
            val weight = row.getDouble("weightShare")
            require(weight.isFinite() && weight in 0.0..1.0 && polls.any { it.id == row.getString("pollId") && it.basis != "unspecified" })
            RoundWeight(row.getString("pollId"), row.getString("institute"), weight, row.getString("basisOrigin"))
        }
        require(weights.size >= 2 && weights.map { it.pollId }.distinct().size == weights.size)
        require(kotlin.math.abs(weights.sumOf { it.weightShare } - 1.0) < .001)
        val change = modelObj.values("change")
        require(change.isEmpty() || (change.keys == RoundIds && change.values.all { it.isFinite() }))
        RoundModel(asOf, support, probability, ranges, weights, change,
            modelObj.optString("changeSince").takeIf { it.isNotBlank() && it != "null" },
            modelObj.getString("quality"), modelObj.getString("message"))
    } else null
    val historyObj = root.optJSONArray("history")
    val history = List(historyObj?.length() ?: 0) { i ->
        val row = historyObj!!.getJSONObject(i)
        val day = row.getString("date")
        require(LocalDate.parse(day) in LocalDate.of(2026, 10, 5)..today)
        val support = row.values("support")
        val probability = row.values("winProbability")
        checkValues(support, true); checkValues(probability, true)
        RoundPoint(day, support, probability, row.getInt("instituteCount"))
    }.sortedBy { it.date }
    require(history.map { it.date }.distinct().size == history.size)
    val marketObj = root.optJSONObject("market")
    val marketValues = marketObj?.values("values") ?: emptyMap()
    if (marketObj?.optString("status") == "ok") checkValues(marketValues)
    val market = RoundMarket(marketObj?.optString("status") ?: "unavailable", marketValues,
        marketObj?.optString("updatedAt")?.takeIf { it.isNotBlank() && it != "null" },
        marketObj?.optString("url")?.takeIf { it.startsWith("https://") } ?: "https://polymarket.com/event/brazil-presidential-election")
    val sourcesObj = root.optJSONArray("sources")
    val sources = List(sourcesObj?.length() ?: 0) { i ->
        val row = sourcesObj!!.getJSONObject(i)
        RoundSource(row.getString("id"), row.getString("status"))
    }
    return RoundReading(generated, checked, root.getString("pollRevision"), root.getString("electionDate"),
        candidates, polls, model, history, market, sources, root.optString("methodology"))
}

internal class SecondRoundRepository(
    context: Context, private val download: (String) -> String = ::downloadRound,
    cacheName: String = "second-round-reading.json"
) {
    private val appContext = context.applicationContext
    private val file = AtomicFile(File(appContext.filesDir, cacheName))
    private val preferences = appContext.getSharedPreferences("round-sync", Context.MODE_PRIVATE)
    fun lastSync(): String? = preferences.getString("lastSync", null)
    fun initial(): RoundLoad {
        val bundled = parseRoundReading(appContext.assets.open("runoff-2026.json").bufferedReader().use { it.readText() })
        val cached = runCatching { parseRoundReading(file.openRead().bufferedReader().use { it.readText() }) }.getOrNull()
        return if (cached != null && Instant.parse(cached.checkedAt) >= Instant.parse(bundled.checkedAt))
            RoundLoad(cached, "saved") else RoundLoad(bundled, "bundled")
    }
    fun fetch(previous: RoundReading?): RoundLoad {
        var lastFailure: Exception? = null
        val urls = listOf(
            "https://raw.githubusercontent.com/emanoelb5-lgtm/Elei-es/main/data/runoff-dashboard.json",
            "https://api.github.com/repos/emanoelb5-lgtm/Elei-es/contents/data/runoff-dashboard.json?ref=main"
        )
        for (url in urls) {
            try {
                val response = download(url)
                val obj = JSONObject(response)
                val raw = if (obj.optString("encoding") == "base64")
                    String(Base64.decode(obj.getString("content"), Base64.DEFAULT), Charsets.UTF_8) else response
                val reading = parseRoundReading(raw)
                require(previous == null || Instant.parse(reading.checkedAt) >= Instant.parse(previous.checkedAt)) { "Resposta anterior à leitura salva" }
                val persisted = runCatching {
                    val stream = file.startWrite()
                    try {
                        stream.write(raw.toByteArray(Charsets.UTF_8))
                        file.finishWrite(stream)
                    } catch (failure: Exception) {
                        file.failWrite(stream)
                        throw failure
                    }
                }.isSuccess
                preferences.edit().putString("lastSync", Instant.now().toString()).apply()
                return RoundLoad(reading, "network", persisted)
            } catch (failure: Exception) { lastFailure = failure }
        }
        throw lastFailure ?: IllegalStateException("Fontes indisponíveis")
    }
}

private fun downloadRound(url: String): String {
    val separator = if (url.contains("?")) "&" else "?"
    val connection = (URL(url + separator + "t=" + System.currentTimeMillis()).openConnection() as HttpURLConnection).apply {
        connectTimeout = 6_000; readTimeout = 6_000
        setRequestProperty("Accept", "application/vnd.github.raw+json")
        setRequestProperty("User-Agent", "TermometroSegundoTurno/0.11")
        setRequestProperty("Cache-Control", "no-cache")
    }
    return try {
        require(connection.responseCode == 200)
        connection.inputStream.use { stream ->
            val buffer = ByteArray(8192)
            val output = java.io.ByteArrayOutputStream()
            while (true) {
                val count = stream.read(buffer)
                if (count < 0) break
                require(output.size() + count <= 2_000_000)
                output.write(buffer, 0, count)
            }
            output.toString("UTF-8")
        }
    } finally { connection.disconnect() }
}

internal fun roundRefreshFeedback(before: RoundReading?, fresh: RoundReading): String {
    if (before == null) return "Dados do segundo turno carregados."
    if (before.revision == fresh.revision) return "Nenhuma pesquisa nova. Consulta concluída."
    val newIds = fresh.polls.map { it.id }.toSet() - before.polls.map { it.id }.toSet()
    return if (newIds.isNotEmpty()) newIds.size.toString() + " nova(s) pesquisa(s). Diagnóstico atualizado."
        else "Dados das pesquisas revisados. Diagnóstico atualizado."
}
