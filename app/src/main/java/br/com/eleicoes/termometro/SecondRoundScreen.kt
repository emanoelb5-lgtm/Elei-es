package br.com.eleicoes.termometro

import androidx.activity.compose.BackHandler
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
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.saveable.rememberSaveableStateHolder
import androidx.compose.foundation.Canvas
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
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
import androidx.lifecycle.compose.LocalLifecycleOwner
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.repeatOnLifecycle
import kotlinx.coroutines.delay
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

@Composable
internal fun SegundoTurnoApp(injectedRepository: SecondRoundRepository? = null) {
    val context = LocalContext.current
    val repository = remember(context, injectedRepository) { injectedRepository ?: SecondRoundRepository(context.applicationContext) }
    val lifecycle = LocalLifecycleOwner.current.lifecycle
    val scope = rememberCoroutineScope()
    var reading by remember { mutableStateOf<RoundReading?>(null) }
    var loading by remember { mutableStateOf(true) }
    var origin by remember { mutableStateOf("bundled") }
    var lastSync by remember { mutableStateOf<String?>(null) }
    var attemptedAt by remember { mutableLongStateOf(0L) }
    var error by remember { mutableStateOf<String?>(null) }
    var notice by remember { mutableStateOf<String?>(null) }
    var tab by rememberSaveable { mutableIntStateOf(0) }
    val screenState = rememberSaveableStateHolder()
    BackHandler(tab != 0) { tab = 0 }

    fun refresh(manual: Boolean = false) {
        if (loading) return
        loading = true
        error = null
        if (manual) notice = null
        attemptedAt = System.currentTimeMillis()
        val previous = reading
        scope.launch {
            runCatching { withContext(Dispatchers.IO) { repository.fetch(previous) } }
                .onSuccess { fresh ->
                    reading = fresh.reading
                    origin = fresh.origin
                    lastSync = repository.lastSync()
                    if (manual) notice = roundRefreshFeedback(previous, fresh.reading)
                    if (!fresh.persisted) error = "Dados recebidos, mas não foi possível salvar no aparelho."
                }
                .onFailure { failure ->
                    if (failure is CancellationException) throw failure
                    error = if (reading == null)
                        "Não foi possível carregar os dados. Confira a conexão e tente novamente."
                    else "Sem sincronização. Os dados disponíveis continuam visíveis; tente novamente."
                }
            loading = false
        }
    }

    LaunchedEffect(repository) {
        runCatching { withContext(Dispatchers.IO) { repository.initial() } }
            .onSuccess { reading = it.reading; origin = it.origin; lastSync = repository.lastSync() }
            .onFailure { error = "Não foi possível abrir a leitura local. Tente atualizar." }
        loading = false
        lifecycle.repeatOnLifecycle(Lifecycle.State.STARTED) {
            if (System.currentTimeMillis() - attemptedAt > 300_000L) refresh()
            while (true) { delay(300_000L); refresh() }
        }
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
                    screenState.SaveableStateProvider(tab) {
                        when (tab) {
                            0 -> RoundHome(reading, loading, origin, lastSync, error, notice,
                                onPolls = { tab = 1 }, onEvolution = { tab = 2 }) { refresh(true) }
                            1 -> RoundPolls(reading)
                            2 -> RoundEvolution(reading)
                            else -> RoundAbout(reading)
                        }
                    }
                }
                NavigationBar(containerColor = Color.White, tonalElevation = 5.dp) {
                    listOf(
                        Triple("Início", R.drawable.ic_nav_home, 0),
                        Triple("Pesquisas", R.drawable.ic_nav_polls, 1),
                        Triple("Evolução", R.drawable.ic_nav_trend, 2),
                        Triple("Fontes", R.drawable.ic_nav_insights, 3)
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
    reading: RoundReading?, loading: Boolean, origin: String, lastSync: String?,
    error: String?, notice: String?, onPolls: () -> Unit, onEvolution: () -> Unit, onRefresh: () -> Unit
) {
    LazyColumn(
        Modifier.fillMaxSize(),
        contentPadding = PaddingValues(18.dp, 20.dp, 18.dp, 30.dp),
        verticalArrangement = Arrangement.spacedBy(15.dp)
    ) {
        item { RoundHero(reading?.electionDate ?: "2026-10-25") }
        item { RoundStatus(reading, loading, origin, lastSync, error, notice, onRefresh) }
        if (reading == null) {
            item { RoundMessage("Abrindo a leitura", "Carregando os dados disponíveis no aparelho.") }
        } else if (reading.polls.isEmpty()) {
            item { RoundMessage("Ainda não há levantamento", "Serão exibidas apenas pesquisas com os dois finalistas realizadas após 4 de outubro.") }
        } else {
            item { RoundOverview(reading) }
            item { RoundForecast(reading) }
            item {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = onPolls, modifier = Modifier.weight(1f)) { Text("Ver pesquisas") }
                    OutlinedButton(onClick = onEvolution, modifier = Modifier.weight(1f)) { Text("Ver evolução") }
                }
            }
            item { RoundSection("Pesquisa mais recente", "Percentuais publicados pelo instituto; não são uma previsão") }
            item { RoundPollCard(reading.polls.first(), reading.candidates) }
            item { RoundMarketCard(reading.market) }
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
    reading: RoundReading?, loading: Boolean, origin: String, lastSync: String?,
    error: String?, notice: String?, onRefresh: () -> Unit
) {
    RoundCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(8.dp).background(if (origin != "network" || error != null) Color(0xFFB87C30) else Teal, CircleShape))
            Spacer(Modifier.width(8.dp))
            Text(
                when {
                    loading -> "VERIFICANDO NOVOS DADOS"
                    error != null -> "USANDO DADOS DISPONÍVEIS"
                    origin == "saved" -> "LEITURA SALVA NO APARELHO"
                    origin == "bundled" -> "BASE INCLUÍDA NO APLICATIVO"
                    else -> "SINCRONIZAÇÃO CONCLUÍDA"
                },
                color = SecondaryText, fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = .8.sp
            )
        }
        Text(
            reading?.polls?.maxOfOrNull { it.fieldworkEnd }?.let { "Pesquisa mais recente: coleta até ${roundDate(it)}" }
                ?: if (error != null) "Sem leitura disponível neste aparelho" else "Buscando pesquisas do segundo turno…",
            fontSize = 15.sp, fontWeight = FontWeight.Bold
        )
        lastSync?.let { Text("Última consulta pelo app: ${roundDateTime(it)}", fontSize = 12.sp, color = SecondaryText) }
        reading?.let {
            Text("Coletor consultou as fontes: ${roundDateTime(it.checkedAt)}", fontSize = 12.sp, color = SecondaryText)
            val age = it.polls.maxOfOrNull { p -> p.fieldworkEnd }?.let { date ->
                ChronoUnit.DAYS.between(LocalDate.parse(date), LocalDate.now(BrazilZone))
            }
            if (age != null && age >= 3) Text("A coleta mais recente tem $age dias. Nova consulta não significa pesquisa nova.",
                fontSize = 12.sp, color = Color(0xFF8A5A20), lineHeight = 17.sp)
        }
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
private fun RoundPolls(reading: RoundReading?) {
    var query by rememberSaveable { mutableStateOf("") }
    var basis by rememberSaveable { mutableStateOf("all") }
    val visible = remember(reading, query, basis) {
        reading?.polls?.filter {
            (basis == "all" || it.basis == basis || (basis == "valid" && it.validResult.isNotEmpty())) &&
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
        Text("Coleta: ${roundDate(poll.fieldworkStart)} a ${roundDate(poll.fieldworkEnd)} · ${basisLabel(poll.basis)}",
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
        poll.publishedAt?.let { Text("Divulgação: ${roundDate(it.take(10))}", color = SecondaryText, fontSize = 12.sp) }
        poll.marginError?.let { Text("Margem de erro publicada: ±${roundPercent(it)} pontos", color = SecondaryText, fontSize = 12.sp) }
        Text("Amostra: ${poll.sample} · ${poll.method}", color = SecondaryText, fontSize = 12.sp)
        poll.registration?.let { Text("Registro informado: $it", color = SecondaryText, fontSize = 12.sp) }
        TextButton(onClick = { runCatching { uriHandler.openUri(poll.sourceUrl) } }) {
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
        item { RoundPageHeader("FONTES E MÉTODO", "De onde vem\na leitura", "Confira o que entra no diagnóstico do segundo turno.") }
        if (reading != null) {
            item { RoundMessage("Como o modelo funciona", reading.methodology) }
            item { RoundWeightAudit(reading) }
            item { RoundSourceStatus(reading) }
        }
        item { RoundMessage("Votos totais", "Percentuais sobre todos os entrevistados, incluindo respostas em branco, nulo e indecisão quando a fonte as divulga.") }
        item { RoundMessage("Votos válidos", "A lista preserva os números publicados. O agregado usa válidos publicados; se a fonte divulga somente totais, a conversão entre os dois nomes é identificada na auditoria. Base desconhecida fica fora do modelo.") }
        item { RoundMessage("Chance no modelo", "A probabilidade de vitória depende de hipóteses explícitas. O modelo é exploratório e ainda não tem calibração histórica. O intervalo de cenário incorpora um piso estrutural de incerteza, além da dispersão entre institutos; não é a margem de erro de uma pesquisa.") }
        item { RoundMessage("Origem dos dados", "As pesquisas recentes incluem links para a publicação original. Números de registro informados pela fonte não são apresentados como validação direta do TSE.") }
        item {
            RoundCard {
                Text("Votação em 25 de outubro", fontSize = 18.sp, fontWeight = FontWeight.ExtraBold)
                Text("O Tribunal Superior Eleitoral confirmou os dois participantes do segundo turno presidencial.",
                    color = SecondaryText, lineHeight = 20.sp)
                TextButton(onClick = {
                    runCatching { uriHandler.openUri("https://www.tse.jus.br/comunicacao/noticias/2026/Outubro/flavio-bolsonaro-e-lula-vao-disputar-o-2o-turno-para-a-presidencia-da-republica") }
                }) { Text("Ler confirmação do TSE") }
            }
        }
        if (reading != null) {
            item { Text("${reading.polls.size} pesquisas na leitura atual", color = SecondaryText, fontSize = 12.sp) }
        }
    }
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

@Composable
private fun RoundForecast(reading: RoundReading) {
    val model = reading.model
    if (model == null) {
        RoundMessage("Diagnóstico aguardando dados", "São necessários dois institutos com base identificada e coleta recente. As pesquisas continuam disponíveis.")
        return
    }
    val stale = ChronoUnit.DAYS.between(LocalDate.parse(model.asOf), LocalDate.now(BrazilZone)) > 1
    RoundCard {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text("Chance no modelo", Modifier.weight(1f), fontSize = 22.sp, fontWeight = FontWeight.ExtraBold)
            Surface(color = Color(0xFFFFF0D8), shape = RoundedCornerShape(50)) {
                Text("EXPLORATÓRIO", Modifier.padding(8.dp), color = Color(0xFF805512), fontSize = 10.sp, fontWeight = FontWeight.Bold)
            }
        }
        Text("Estimativa de vitória · leitura de ${roundDate(model.asOf)}", color = SecondaryText, fontSize = 12.sp)
        if (stale) Text("Estimativa salva. Atualize para consultar uma leitura mais recente.", color = Color(0xFF8A5A20), fontSize = 12.sp)
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            reading.candidates.forEachIndexed { index, candidate ->
                val color = if (index == 0) FirstColor else SecondColor
                Column(Modifier.weight(1f).background(color.copy(alpha = .09f), RoundedCornerShape(18.dp)).padding(13.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(candidate.name, fontWeight = FontWeight.Bold, fontSize = 14.sp, minLines = 2)
                    Text("${roundPercent(model.probability[candidate.id])}%", color = color, fontSize = 31.sp, fontWeight = FontWeight.ExtraBold)
                    LinearProgressIndicator(progress = { ((model.probability[candidate.id] ?: 0.0) / 100).toFloat() },
                        modifier = Modifier.fillMaxWidth().height(6.dp), color = color, trackColor = color.copy(alpha = .12f))
                }
            }
        }
        Text(model.message, fontSize = 12.sp, lineHeight = 18.sp, color = SecondaryText)
        HorizontalDivider(color = Hairline)
        Text("Apoio agregado em votos válidos", fontSize = 16.sp, fontWeight = FontWeight.Bold)
        reading.candidates.forEachIndexed { index, candidate ->
            Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
                Row(Modifier.fillMaxWidth()) {
                    Text(candidate.name, Modifier.weight(1f), fontSize = 14.sp)
                    Text("${roundPercent(model.support[candidate.id])}%", color = if (index == 0) FirstColor else SecondColor,
                        fontWeight = FontWeight.ExtraBold, fontSize = 19.sp)
                }
                val interval = model.intervals[candidate.id]
                val change = model.change[candidate.id]
                val delta = change?.let { (if (it > 0) "+" else "") + String.format(Locale("pt", "BR"), "%.2f", it) + " p.p." }
                Text("Intervalo de cenário: ${roundPercent(interval?.first)}–${roundPercent(interval?.second)}%" +
                    (if (delta != null) " · $delta desde ${roundDate(model.changeSince ?: "")}" else ""),
                    color = SecondaryText, fontSize = 11.sp, lineHeight = 16.sp)
            }
        }
        Text("${model.weights.size} institutos no modelo · ${model.quality}", color = Teal, fontWeight = FontWeight.Bold, fontSize = 12.sp)
    }
}

@Composable
private fun RoundEvolution(reading: RoundReading?) {
    var metric by rememberSaveable { mutableStateOf("support") }
    val points = reading?.history ?: emptyList()
    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(18.dp, 22.dp, 18.dp, 30.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp)) {
        item { RoundPageHeader("HISTÓRICO DO SEGUNDO TURNO", "A evolução\nda leitura", "Histórico reconstruído a partir das divulgações, inclusive anteriores à instalação.") }
        item {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip(metric == "support", onClick = { metric = "support" }, label = { Text("Apoio em válidos") })
                FilterChip(metric == "probability", onClick = { metric = "probability" }, label = { Text("Chance no modelo") })
            }
        }
        if (points.isEmpty() || reading == null) {
            item { RoundMessage("Histórico ainda insuficiente", "Os pontos aparecerão quando houver publicações de ao menos dois institutos com base identificada.") }
        } else {
            item {
                RoundCard {
                    Text(if (metric == "support") "Apoio agregado (%)" else "Estimativa exploratória (%)", fontSize = 17.sp, fontWeight = FontWeight.Bold)
                    RoundChart(points, reading.candidates, metric)
                    Text("Cada ponto usa apenas as pesquisas divulgadas até aquele dia. Alterações na composição da base também mudam o agregado.",
                        fontSize = 12.sp, color = SecondaryText, lineHeight = 18.sp)
                }
            }
            if (points.size < 3) item {
                RoundMessage("Base histórica inicial", "Há somente ${points.size} datas comparáveis. A linha liga os pontos disponíveis; isso ainda não demonstra uma tendência.")
            }
            item { RoundSection("Leitura por data", if (metric == "support") "Percentual de votos válidos no agregado" else "Probabilidade exploratória, sob as hipóteses do modelo") }
            items(points.asReversed(), key = { it.date }) { point ->
                RoundCard {
                    Text("${roundDate(point.date)} · ${point.instituteCount} institutos", fontWeight = FontWeight.Bold)
                    reading.candidates.forEachIndexed { index, candidate ->
                        Row(Modifier.fillMaxWidth()) {
                            Text(candidate.name, Modifier.weight(1f), fontSize = 14.sp)
                            val value = if (metric == "support") point.support[candidate.id] else point.probability[candidate.id]
                            Text("${roundPercent(value)}%", fontWeight = FontWeight.Bold, color = if (index == 0) FirstColor else SecondColor)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun RoundChart(points: List<RoundPoint>, candidates: List<RoundCandidate>, metric: String) {
    val values = points.flatMap { (if (metric == "support") it.support else it.probability).values }
    val min = if (metric == "support") kotlin.math.min(40.0, (values.minOrNull() ?: 40.0) - 3).coerceAtLeast(0.0) else 0.0
    val max = if (metric == "support") kotlin.math.max(60.0, (values.maxOrNull() ?: 60.0) + 3).coerceAtMost(100.0) else 100.0
    val begin = LocalDate.parse(points.first().date).toEpochDay()
    val end = LocalDate.parse(points.last().date).toEpochDay()
    Row(Modifier.fillMaxWidth().height(200.dp)) {
        Column(Modifier.width(35.dp).fillMaxHeight(), verticalArrangement = Arrangement.SpaceBetween) {
            listOf(max, (min + max) / 2, min).forEach { Text("${it.toInt()}%", fontSize = 10.sp, color = SecondaryText) }
        }
        Canvas(Modifier.weight(1f).fillMaxHeight().semantics { contentDescription = "Gráfico de $metric; valores detalhados por data abaixo." }) {
            val padding = 8.dp.toPx()
            val width = size.width - padding * 2
            val height = size.height - padding * 2
            listOf(0f, .5f, 1f).forEach { ratio ->
                drawLine(Hairline, Offset(padding, padding + ratio * height), Offset(padding + width, padding + ratio * height), 1.dp.toPx())
            }
            if (min <= 50 && max >= 50) {
                val y = padding + ((max - 50) / (max - min)).toFloat() * height
                drawLine(SecondaryText.copy(alpha = .35f), Offset(padding, y), Offset(padding + width, y), 1.dp.toPx())
            }
            candidates.forEachIndexed { index, candidate ->
                val color = if (index == 0) FirstColor else SecondColor
                val offsets = points.map { point ->
                    val day = LocalDate.parse(point.date).toEpochDay()
                    val x = if (end == begin) width / 2 else (day - begin).toFloat() / (end - begin) * width
                    val value = (if (metric == "support") point.support else point.probability).getValue(candidate.id)
                    Offset(padding + x, padding + ((max - value) / (max - min)).toFloat() * height)
                }
                val path = Path()
                offsets.forEachIndexed { i, offset -> if (i == 0) path.moveTo(offset.x, offset.y) else path.lineTo(offset.x, offset.y) }
                if (offsets.size > 1) drawPath(path, color, style = Stroke(3.dp.toPx(), cap = StrokeCap.Round))
                offsets.forEach { drawCircle(Color.White, 5.dp.toPx(), it); drawCircle(color, 3.dp.toPx(), it) }
            }
        }
    }
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(roundDate(points.first().date), fontSize = 11.sp, color = SecondaryText)
        if (points.size > 1) Text(roundDate(points.last().date), fontSize = 11.sp, color = SecondaryText)
    }
    candidates.forEachIndexed { index, candidate ->
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(8.dp).background(if (index == 0) FirstColor else SecondColor, CircleShape))
            Spacer(Modifier.width(7.dp))
            Text(candidate.name, fontSize = 12.sp, color = SecondaryText)
        }
    }
}

@Composable
private fun RoundMarketCard(market: RoundMarket) {
    val uriHandler = LocalUriHandler.current
    val fresh = runCatching {
        val age = java.time.Duration.between(Instant.parse(market.updatedAt), Instant.now()).seconds
        market.status == "ok" && age in 0..86_400
    }.getOrDefault(false)
    RoundCard {
        Text("Mercado de previsão", fontWeight = FontWeight.ExtraBold, fontSize = 18.sp)
        if (fresh) {
            Text("Polymarket · cotações de ${roundDateTime(market.updatedAt ?: "")}", fontSize = 12.sp, color = SecondaryText)
            Text("Flávio Bolsonaro ${roundPercent(market.values["flavio-bolsonaro"])}% · Lula ${roundPercent(market.values["lula"])}%", fontWeight = FontWeight.Bold)
        } else Text("Sem cotação recente validada nesta leitura.", color = SecondaryText, fontSize = 14.sp)
        Text("Sinal externo, apresentado separadamente das pesquisas e do modelo do aplicativo.", color = SecondaryText, fontSize = 12.sp, lineHeight = 18.sp)
        TextButton(onClick = { runCatching { uriHandler.openUri(market.url) } }) { Text("Abrir mercado") }
    }
}

@Composable
private fun RoundWeightAudit(reading: RoundReading) {
    val model = reading.model ?: return
    RoundCard {
        Text("Pesquisas usadas no modelo", fontWeight = FontWeight.ExtraBold, fontSize = 18.sp)
        model.weights.forEach { row ->
            Text("${row.institute} · ${roundPercent(row.weightShare * 100)}% do peso", fontWeight = FontWeight.Bold, fontSize = 14.sp)
            Text("${row.pollId} · ${row.basisOrigin}", color = SecondaryText, fontSize = 12.sp)
        }
        Text("Um levantamento por instituto evita contar rodadas repetidas como evidências independentes.", fontSize = 12.sp, lineHeight = 18.sp, color = SecondaryText)
    }
}

@Composable
private fun RoundSourceStatus(reading: RoundReading) {
    RoundCard {
        Text("Estado das fontes", fontSize = 18.sp, fontWeight = FontWeight.ExtraBold)
        Text("Última verificação do coletor: ${roundDateTime(reading.checkedAt)}", fontSize = 12.sp, color = SecondaryText)
        if (reading.sources.isEmpty()) Text("Dados incluídos no APK.", fontSize = 13.sp, color = SecondaryText)
        reading.sources.forEach { source ->
            val label = when (source.id) { "pollingdata" -> "BBC / PollingData"; "polymarket" -> "Polymarket"; else -> "Base conferida" }
            val status = when (source.status) { "ok" -> "consulta concluída"; "saved" -> "dados salvos"; else -> "indisponível nesta consulta" }
            Text("$label · $status", fontSize = 13.sp, color = SecondaryText)
        }
        Text("Falhas de fontes complementares não apagam as pesquisas confirmadas.", fontSize = 12.sp, color = SecondaryText, lineHeight = 18.sp)
    }
}
