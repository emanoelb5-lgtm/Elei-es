package br.com.eleicoes.termometro

import android.content.Context
import android.util.AtomicFile
import androidx.compose.animation.AnimatedContent
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.time.temporal.ChronoUnit
import java.util.Locale

private val Ink = Color(0xFF102A3A)
private val Teal = Color(0xFF006D62)
private val CanvasBg = Color(0xFFF3F6F5)
private val SecondaryText = Color(0xFF526872)
private val Hairline = Color(0xFFE1E9E7)
private val FirstColor = Color(0xFF0C6B75)
private val SecondColor = Color(0xFF9B6427)
private val BrazilZone = ZoneId.of("America/Sao_Paulo")

private data class RoundCandidate(val id: String, val name: String, val party: String)
private data class RoundPoll(
    val id: String,
    val institute: String,
    val fieldworkEnd: String,
    val publishedAt: String,
    val sample: Int,
    val method: String,
    val registration: String?,
    val basis: String,
    val result: Map<String, Double>,
    val validResult: Map<String, Double>,
    val nonCandidate: Map<String, Double>,
    val sourceUrl: String,
    val sourceLabel: String,
    val origin: String
)

private data class RoundReading(
    val generatedAt: String,
    val electionDate: String,
    val candidates: List<RoundCandidate>,
    val polls: List<RoundPoll>
)

private class SecondRoundRepository(context: Context) {
    private val file = AtomicFile(File(context.applicationContext.filesDir, "second-round-reading.json"))
    private val url = "https://raw.githubusercontent.com/emanoelb5-lgtm/Elei-es/main/data/runoff-2026.json"

    fun cached(): RoundReading? = runCatching {
        parse(file.openRead().bufferedReader().use { it.readText() })
    }.getOrNull()

    fun fetch(): RoundReading {
        val connection = (URL("$url?t=${System.currentTimeMillis()}").openConnection() as HttpURLConnection).apply {
            connectTimeout = 8_000
            readTimeout = 8_000
            setRequestProperty("Accept", "application/json")
            setRequestProperty("Cache-Control", "no-cache")
        }
        val raw = try {
            if (connection.responseCode !in 200..299) error("HTTP ${connection.responseCode}")
            connection.inputStream.bufferedReader().use { it.readText() }
        } finally {
            connection.disconnect()
        }
        val reading = parse(raw)
        // Uma falha de armazenamento não deve descartar uma leitura válida recebida da rede.
        runCatching {
            val stream = file.startWrite()
            try {
                stream.write(raw.toByteArray(Charsets.UTF_8))
                file.finishWrite(stream)
            } catch (e: Exception) {
                file.failWrite(stream)
                throw e
            }
        }
        return reading
    }

    private fun parse(raw: String): RoundReading {
        val root = JSONObject(raw)
        require(root.getInt("schemaVersion") == 1)
        val electionDate = root.getString("electionDate")
        require(electionDate == "2026-10-25")
        val list = root.getJSONArray("candidates")
        val candidates = List(list.length()) { index ->
            val row = list.getJSONObject(index)
            RoundCandidate(row.getString("id"), row.getString("name"), row.getString("party"))
        }
        require(candidates.map { it.id }.toSet() == setOf("flavio-bolsonaro", "lula") && candidates.size == 2)
        fun values(obj: JSONObject?): Map<String, Double> = obj?.let { source ->
            source.keys().asSequence().associateWith { key -> source.getDouble(key) }
        } ?: emptyMap()
        val rows = root.getJSONArray("polls")
        val polls = List(rows.length()) { index ->
            val row = rows.getJSONObject(index)
            val result = values(row.getJSONObject("result"))
            require(result.keys == candidates.map { it.id }.toSet())
            require(LocalDate.parse(row.getString("fieldworkEnd")) >= LocalDate.of(2026, 10, 5))
            RoundPoll(
                id = row.getString("id"),
                institute = row.getString("institute"),
                fieldworkEnd = row.getString("fieldworkEnd"),
                publishedAt = row.getString("publishedAt"),
                sample = row.getInt("sample"),
                method = row.optString("method", "Não informado"),
                registration = row.optString("registration").takeIf { it.isNotBlank() && it != "null" },
                basis = row.getString("basis"),
                result = result,
                validResult = values(row.optJSONObject("validResult")),
                nonCandidate = values(row.optJSONObject("nonCandidate")),
                sourceUrl = row.getString("sourceUrl"),
                sourceLabel = row.optString("sourceLabel", row.getString("institute")),
                origin = row.optString("origin")
            )
        }
        return RoundReading(root.getString("generatedAt"), electionDate, candidates, polls)
    }
}

@Composable
fun SegundoTurnoApp() {
    val context = LocalContext.current
    val repository = remember(context) { SecondRoundRepository(context.applicationContext) }
    val scope = rememberCoroutineScope()
    var reading by remember { mutableStateOf<RoundReading?>(null) }
    var loading by remember { mutableStateOf(true) }
    var saved by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var notice by remember { mutableStateOf<String?>(null) }
    var tab by remember { mutableIntStateOf(0) }

    fun refresh(manual: Boolean = false) {
        if (loading) return
        loading = true
        error = null
        if (manual) notice = null
        val previous = reading?.generatedAt
        scope.launch {
            runCatching { withContext(Dispatchers.IO) { repository.fetch() } }
                .onSuccess { fresh ->
                    reading = fresh
                    saved = false
                    if (manual) notice = if (previous == fresh.generatedAt)
                        "Nenhuma nova leitura foi publicada." else "Leitura do segundo turno atualizada."
                }
                .onFailure { failure ->
                    if (failure is CancellationException) throw failure
                    error = if (reading == null)
                        "Não foi possível carregar os dados. Confira a conexão e tente novamente."
                    else "Fonte indisponível. A última leitura salva continua visível."
                }
            loading = false
        }
    }

    LaunchedEffect(Unit) {
        reading = withContext(Dispatchers.IO) { repository.cached() }
        saved = reading != null
        loading = false
        refresh()
    }

    MaterialTheme(
        colorScheme = lightColorScheme(
            primary = Teal, onPrimary = Color.White, secondary = Ink,
            background = CanvasBg, surface = Color.White, onSurface = Ink,
            primaryContainer = Color(0xFFD8F2E9), onPrimaryContainer = Ink
        )
    ) {
        Surface(Modifier.fillMaxSize(), color = CanvasBg) {
            Column(Modifier.fillMaxSize().windowInsetsPadding(WindowInsets.safeDrawing)) {
                Box(Modifier.weight(1f)) {
                    when (tab) {
                        0 -> RoundHome(reading, loading, saved, error, notice) { refresh(true) }
                        1 -> RoundPolls(reading)
                        else -> RoundAbout(reading)
                    }
                }
                NavigationBar(containerColor = Color.White, tonalElevation = 5.dp) {
                    listOf(
                        Triple("Início", R.drawable.ic_nav_home, 0),
                        Triple("Pesquisas", R.drawable.ic_nav_polls, 1),
                        Triple("Entenda", R.drawable.ic_nav_insights, 2)
                    ).forEach { (label, icon, index) ->
                        NavigationBarItem(
                            selected = tab == index,
                            onClick = { tab = index },
                            icon = { Icon(painterResource(icon), contentDescription = null) },
                            label = { Text(label) },
                            colors = NavigationBarItemDefaults.colors(
                                selectedIconColor = Teal, selectedTextColor = Teal,
                                indicatorColor = Color(0xFFD8F2E9),
                                unselectedIconColor = SecondaryText, unselectedTextColor = SecondaryText
                            )
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun RoundHome(
    reading: RoundReading?, loading: Boolean, saved: Boolean,
    error: String?, notice: String?, onRefresh: () -> Unit
) {
    LazyColumn(
        Modifier.fillMaxSize(),
        contentPadding = PaddingValues(18.dp, 20.dp, 18.dp, 30.dp),
        verticalArrangement = Arrangement.spacedBy(15.dp)
    ) {
        item { RoundHero(reading?.electionDate ?: "2026-10-25") }
        item { RoundStatus(reading, loading, saved, error, notice, onRefresh) }
        if (reading == null) {
            item { RoundMessage("Aguardando a leitura", "É preciso conectar à internet para carregar as pesquisas pela primeira vez.") }
        } else if (reading.polls.isEmpty()) {
            item { RoundMessage("Ainda não há levantamento", "Serão exibidas apenas pesquisas com os dois finalistas realizadas após 4 de outubro.") }
        } else {
            item { RoundOverview(reading) }
            item { RoundSection("Pesquisa mais recente", "Percentuais publicados pelo instituto; não são uma previsão") }
            item { LatestPoll(reading.polls.first(), reading.candidates) }
            item { RoundSection("Outros levantamentos", "Consulte data, amostra, base percentual e fonte") }
            items(reading.polls.drop(1).take(3), key = { it.id }) { poll ->
                RoundPollCard(poll, reading.candidates)
            }
            item { RoundTrendNotice(reading.polls) }
            item { RoundMessage("Como ler esta tela", "Votos totais incluem brancos, nulos e indecisos. Votos válidos excluem essas respostas. O aplicativo mantém as duas bases separadas.") }
        }
    }
}

@Composable
private fun RoundHero(electionDate: String) {
    val days = runCatching {
        ChronoUnit.DAYS.between(LocalDate.now(BrazilZone), LocalDate.parse(electionDate))
    }.getOrNull()
    Column(
        Modifier.fillMaxWidth()
            .background(Brush.linearGradient(listOf(Ink, Color(0xFF174C57), Teal)), RoundedCornerShape(28.dp))
            .padding(22.dp),
        verticalArrangement = Arrangement.spacedBy(13.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(9.dp).background(Color(0xFF98E8C5), CircleShape))
            Spacer(Modifier.width(8.dp))
            Text("ELEIÇÕES 2026  ·  2º TURNO", color = Color(0xFFD9F5EA),
                fontWeight = FontWeight.Bold, fontSize = 12.sp, letterSpacing = 1.sp)
        }
        Text("A disputa\npresidencial", color = Color.White, fontSize = 33.sp,
            lineHeight = 36.sp, fontWeight = FontWeight.ExtraBold)
        Text("Flávio Bolsonaro  ×  Lula", color = Color(0xFFE6F5F2),
            fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
        Surface(color = Color.White.copy(alpha = .16f), shape = RoundedCornerShape(50)) {
            Text(
                when {
                    days == null -> "Votação em 25 de outubro"
                    days < 0 -> "Segundo turno · 25 de outubro"
                    days == 0L -> "Dia da votação"
                    else -> "$days dias até 25 de outubro"
                },
                Modifier.padding(horizontal = 13.dp, vertical = 8.dp),
                color = Color.White, fontSize = 12.sp, fontWeight = FontWeight.Bold
            )
        }
    }
}

@Composable
private fun RoundStatus(
    reading: RoundReading?, loading: Boolean, saved: Boolean,
    error: String?, notice: String?, onRefresh: () -> Unit
) {
    RoundCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(8.dp).background(if (saved || error != null) Color(0xFFB87C30) else Teal, CircleShape))
            Spacer(Modifier.width(8.dp))
            Text(
                when {
                    saved -> "LEITURA SALVA NO APARELHO"
                    loading -> "VERIFICANDO NOVOS DADOS"
                    error != null -> "FONTE INDISPONÍVEL"
                    else -> "LEITURA ATUALIZADA"
                },
                color = SecondaryText, fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = .8.sp
            )
        }
        Text(
            reading?.generatedAt?.let { "Dados consultados em ${roundDateTime(it)}" }
                ?: if (error != null) "Sem leitura disponível neste aparelho" else "Buscando pesquisas do segundo turno…",
            fontSize = 15.sp, fontWeight = FontWeight.Bold
        )
        if (loading) LinearProgressIndicator(Modifier.fillMaxWidth(), color = Teal)
        Button(
            onClick = onRefresh, enabled = !loading, modifier = Modifier.fillMaxWidth(),
            shape = RoundedCornerShape(14.dp)
        ) {
            AnimatedContent(loading, label = "reading-refresh") { active ->
                Text(if (active) "Consultando fontes…" else "Atualizar pesquisas", fontWeight = FontWeight.Bold)
            }
        }
        notice?.let { Text(it, color = Teal, fontSize = 13.sp) }
        error?.let { Text(it, color = Color(0xFFAE352D), fontSize = 13.sp) }
    }
}

@Composable
private fun RoundOverview(reading: RoundReading) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(9.dp)) {
        listOf(
            reading.polls.size.toString() to "pesquisas",
            reading.polls.map { it.institute }.distinct().size.toString() to "institutos",
            "25/10" to "votação"
        ).forEach { (value, label) ->
            Column(
                Modifier.weight(1f).background(Color.White, RoundedCornerShape(18.dp))
                    .padding(horizontal = 8.dp, vertical = 14.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Text(value, fontSize = 21.sp, fontWeight = FontWeight.ExtraBold, color = Ink)
                Text(label, fontSize = 11.sp, color = SecondaryText, maxLines = 1)
            }
        }
    }
}

@Composable
private fun LatestPoll(poll: RoundPoll, candidates: List<RoundCandidate>) {
    RoundCard {
        Text(poll.institute.uppercase(Locale("pt", "BR")), color = Teal,
            fontSize = 12.sp, fontWeight = FontWeight.ExtraBold, letterSpacing = .7.sp)
        Text("${if (poll.origin.startsWith("tabela pública")) "Coleta até ${roundDate(poll.fieldworkEnd)}" else "Divulgada em ${roundDate(poll.publishedAt.take(10))}"} · ${basisLabel(poll.basis)}",
            color = SecondaryText, fontSize = 13.sp)
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(9.dp)) {
            candidates.forEachIndexed { index, candidate ->
                Column(
                    Modifier.weight(1f)
                        .background(if (index == 0) Color(0xFFE4F3F2) else Color(0xFFF7EEE3), RoundedCornerShape(18.dp))
                        .padding(14.dp),
                    verticalArrangement = Arrangement.spacedBy(7.dp)
                ) {
                    Text(candidate.name, fontWeight = FontWeight.Bold, fontSize = 14.sp,
                        maxLines = 2, minLines = 2, overflow = TextOverflow.Ellipsis)
                    Text("${roundPercent(poll.result[candidate.id])}%", fontWeight = FontWeight.ExtraBold,
                        fontSize = 29.sp, color = if (index == 0) FirstColor else SecondColor)
                    Text(candidate.party, color = SecondaryText, fontSize = 12.sp)
                }
            }
        }
        if (poll.validResult.isNotEmpty()) {
            Text(
                "Em votos válidos: ${candidates.joinToString(" · ") { "${it.name} ${roundPercent(poll.validResult[it.id])}%" }}",
                color = SecondaryText, fontSize = 12.sp, lineHeight = 18.sp
            )
        }
        Text("Pesquisa, não projeção de resultado.", color = SecondaryText, fontSize = 12.sp)
    }
}

@Composable
private fun RoundPolls(reading: RoundReading?) {
    var query by remember { mutableStateOf("") }
    var basis by remember { mutableStateOf("all") }
    val visible = remember(reading, query, basis) {
        reading?.polls?.filter {
            (basis == "all" || it.basis == basis) &&
                (query.isBlank() || it.institute.contains(query.trim(), ignoreCase = true) ||
                    it.registration?.contains(query.trim(), ignoreCase = true) == true)
        } ?: emptyList()
    }
    LazyColumn(
        Modifier.fillMaxSize(), contentPadding = PaddingValues(18.dp, 22.dp, 18.dp, 30.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        item { RoundPageHeader("PESQUISAS DO 2º TURNO", "Cada levantamento,\nno seu contexto", "Somente pesquisas realizadas após o primeiro turno entre os dois finalistas.") }
        item {
            OutlinedTextField(
                value = query, onValueChange = { query = it }, modifier = Modifier.fillMaxWidth(),
                label = { Text("Buscar instituto ou registro") }, singleLine = true,
                shape = RoundedCornerShape(16.dp)
            )
        }
        item {
            LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                items(listOf("all" to "Todas", "total" to "Votos totais", "valid" to "Votos válidos", "unspecified" to "Base a conferir")) { (key, label) ->
                    FilterChip(selected = basis == key, onClick = { basis = key }, label = { Text(label) })
                }
            }
        }
        if (reading == null) {
            item { RoundMessage("Buscando dados", "A lista aparecerá após a primeira atualização.") }
        } else if (visible.isEmpty()) {
            item { RoundMessage("Nenhuma pesquisa neste filtro", "Experimente outro instituto ou outra base percentual.") }
        } else {
            items(visible, key = { it.id }) { poll -> RoundPollCard(poll, reading.candidates) }
        }
    }
}

@Composable
private fun RoundPollCard(poll: RoundPoll, candidates: List<RoundCandidate>) {
    val uriHandler = LocalUriHandler.current
    RoundCard {
        Text(poll.institute, fontSize = 18.sp, fontWeight = FontWeight.ExtraBold)
        Text("${roundDate(poll.fieldworkEnd)} · ${basisLabel(poll.basis)}",
            color = SecondaryText, fontSize = 13.sp)
        HorizontalDivider(color = Hairline)
        candidates.forEachIndexed { index, candidate ->
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(8.dp).background(if (index == 0) FirstColor else SecondColor, CircleShape))
                Spacer(Modifier.width(8.dp))
                Text(candidate.name, Modifier.weight(1f), fontSize = 14.sp, fontWeight = FontWeight.SemiBold)
                Text("${roundPercent(poll.result[candidate.id])}%", fontSize = 17.sp, fontWeight = FontWeight.ExtraBold)
            }
        }
        if (poll.validResult.isNotEmpty()) {
            Text("Votos válidos publicados: ${candidates.joinToString(" · ") { "${it.name} ${roundPercent(poll.validResult[it.id])}%" }}",
                color = SecondaryText, fontSize = 12.sp, lineHeight = 18.sp)
        }
        if (poll.nonCandidate.isNotEmpty()) {
            Text("Outras respostas: ${poll.nonCandidate.entries.joinToString(" · ") { "${nonCandidateLabel(it.key)} ${roundPercent(it.value)}%" }}",
                color = SecondaryText, fontSize = 12.sp, lineHeight = 18.sp)
        }
        Text("Amostra: ${poll.sample} · ${poll.method}", color = SecondaryText, fontSize = 12.sp)
        poll.registration?.let { Text("Registro informado: $it", color = SecondaryText, fontSize = 12.sp) }
        TextButton(onClick = { uriHandler.openUri(poll.sourceUrl) }) {
            Text("Abrir fonte: ${poll.sourceLabel}", maxLines = 1, overflow = TextOverflow.Ellipsis)
        }
    }
}

@Composable
private fun RoundAbout(reading: RoundReading?) {
    val uriHandler = LocalUriHandler.current
    LazyColumn(
        Modifier.fillMaxSize(), contentPadding = PaddingValues(18.dp, 22.dp, 18.dp, 30.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        item { RoundPageHeader("ENTENDA A LEITURA", "Dados com\ncontexto", "Como interpretar as pesquisas presidenciais do segundo turno.") }
        item { RoundMessage("Votos totais", "Percentuais sobre todos os entrevistados, incluindo respostas em branco, nulo e indecisão quando a fonte as divulga.") }
        item { RoundMessage("Votos válidos", "Percentuais calculados apenas entre os dois nomes. São exibidos quando publicados pela fonte. Essa base não é misturada com votos totais.") }
        item { RoundMessage("Evolução e incerteza", "Levantamentos de institutos e métodos diferentes podem variar. Dois resultados isolados não demonstram tendência nem permitem prever o vencedor.") }
        item { RoundMessage("Origem dos dados", "As pesquisas recentes incluem links para a publicação original. Números de registro informados pela fonte não são apresentados como validação direta do TSE.") }
        item {
            RoundCard {
                Text("Votação em 25 de outubro", fontSize = 18.sp, fontWeight = FontWeight.ExtraBold)
                Text("O Tribunal Superior Eleitoral confirmou os dois participantes do segundo turno presidencial.",
                    color = SecondaryText, lineHeight = 20.sp)
                TextButton(onClick = {
                    uriHandler.openUri("https://www.tse.jus.br/comunicacao/noticias/2026/Outubro/flavio-bolsonaro-e-lula-vao-disputar-o-2o-turno-para-a-presidencia-da-republica")
                }) { Text("Ler confirmação do TSE") }
            }
        }
        if (reading != null) {
            item { Text("${reading.polls.size} pesquisas na leitura atual", color = SecondaryText, fontSize = 12.sp) }
        }
    }
}

@Composable
private fun RoundTrendNotice(polls: List<RoundPoll>) {
    val comparable = polls.filter { it.basis == "total" }.map { it.fieldworkEnd }.distinct().size
    RoundMessage(
        "Leitura ao longo do tempo",
        if (comparable < 3)
            "Ainda há poucas datas com pesquisas de votos totais para avaliar mudanças ao longo do tempo. Consulte os levantamentos e suas fontes na aba Pesquisas."
        else
            "Há pesquisas de votos totais em $comparable datas. Compare os levantamentos na aba Pesquisas considerando método e instituto; diferenças entre eles não são uma previsão."
    )
}

@Composable
private fun RoundPageHeader(eyebrow: String, title: String, description: String) {
    Column(verticalArrangement = Arrangement.spacedBy(7.dp)) {
        Text(eyebrow, color = Teal, fontSize = 12.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp)
        Text(title, color = Ink, fontSize = 32.sp, lineHeight = 35.sp, fontWeight = FontWeight.ExtraBold)
        Text(description, color = SecondaryText, lineHeight = 21.sp)
    }
}

@Composable
private fun RoundSection(title: String, subtitle: String) {
    Column(Modifier.padding(top = 5.dp), verticalArrangement = Arrangement.spacedBy(3.dp)) {
        Text(title, fontSize = 21.sp, fontWeight = FontWeight.ExtraBold, color = Ink)
        Text(subtitle, color = SecondaryText, fontSize = 13.sp, lineHeight = 18.sp)
    }
}

@Composable
private fun RoundCard(content: @Composable ColumnScope.() -> Unit) {
    Card(
        shape = RoundedCornerShape(22.dp),
        colors = CardDefaults.cardColors(containerColor = Color.White),
        border = BorderStroke(1.dp, Hairline)
    ) {
        Column(Modifier.fillMaxWidth().padding(18.dp), verticalArrangement = Arrangement.spacedBy(12.dp), content = content)
    }
}

@Composable
private fun RoundMessage(title: String, body: String) {
    RoundCard {
        Text(title, fontSize = 18.sp, fontWeight = FontWeight.ExtraBold)
        Text(body, color = SecondaryText, fontSize = 14.sp, lineHeight = 20.sp)
    }
}

private fun basisLabel(basis: String) = when (basis) {
    "total" -> "votos totais"
    "valid" -> "votos válidos"
    else -> "base percentual a conferir"
}

private fun nonCandidateLabel(key: String) = when (key) {
    "blankNull" -> "brancos/nulos"
    "undecided" -> "indecisos"
    "blankNullUndecided" -> "brancos/nulos/indecisos"
    else -> key
}

private fun roundPercent(value: Double?): String =
    value?.let { if (it == it.toLong().toDouble()) it.toLong().toString() else String.format(Locale("pt", "BR"), "%.1f", it) } ?: "—"

private fun roundDate(raw: String): String = runCatching {
    LocalDate.parse(raw).format(DateTimeFormatter.ofPattern("dd/MM/yyyy"))
}.getOrElse { raw }

private fun roundDateTime(raw: String): String = runCatching {
    DateTimeFormatter.ofPattern("dd/MM · HH:mm").withZone(BrazilZone).format(Instant.parse(raw))
}.getOrElse { raw }
