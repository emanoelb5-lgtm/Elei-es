package br.com.eleicoes.termometro

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.animation.AnimatedContent
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.time.Instant
import java.time.LocalDate
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import kotlin.math.abs

private val BrazilGreen = Color(0xFF0B6B45)
private val BrazilBlue = Color(0xFF183B6B)
private val SoftBg = Color(0xFFF5F7F2)
private val TextDark = Color(0xFF17221D)
private val Muted = Color(0xFF65736B)
private val Positive = Color(0xFF157347)
private val Negative = Color(0xFFB42318)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { TermometroApp() }
    }
}

@Composable
fun TermometroApp() {
    MaterialTheme(
        colorScheme = lightColorScheme(
            primary = BrazilGreen,
            secondary = BrazilBlue,
            background = SoftBg,
            surface = Color.White,
            onBackground = TextDark,
            onSurface = TextDark
        )
    ) {
        Surface(Modifier.fillMaxSize(), color = SoftBg) {
            Box(
                Modifier
                    .fillMaxSize()
                    .windowInsetsPadding(WindowInsets.safeDrawing)
            ) {
                DashboardHost()
            }
        }
    }
}

@Composable
private fun DashboardHost() {
    val repository = remember { ElectionRepository() }
    val scope = rememberCoroutineScope()
    var data by remember { mutableStateOf<DashboardData?>(null) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var notice by remember { mutableStateOf<String?>(null) }
    var tab by remember { mutableIntStateOf(0) }

    fun refresh(userInitiated: Boolean = false) {
        loading = true
        error = null
        if (userInitiated) notice = null
        val before = data
        scope.launch {
            runCatching { withContext(Dispatchers.IO) { repository.load() } }
                .onSuccess { fresh ->
                    if (userInitiated) notice = refreshFeedback(before, fresh)
                    data = fresh
                }
                .onFailure {
                    error = "Não foi possível atualizar agora. A leitura anterior foi mantida."
                    if (userInitiated) notice = "Falha ao consultar as fontes. Tente novamente mais tarde."
                }
            loading = false
        }
    }

    LaunchedEffect(Unit) { refresh(false) }

    Column(Modifier.fillMaxSize()) {
        Box(Modifier.weight(1f).fillMaxWidth()) {
            when (tab) {
                0 -> HomeScreen(data, loading, error, notice) { refresh(true) }
                1 -> TrendScreen(data, loading)
                2 -> PollsScreen(data, loading)
                else -> DiagnosticsScreen(data, loading)
            }
        }
        NavigationBar(containerColor = Color.White) {
            NavigationBarItem(
                selected = tab == 0,
                onClick = { tab = 0 },
                icon = { Text("⌂", fontSize = 22.sp, fontWeight = FontWeight.Bold) },
                label = { Text("Início") }
            )
            NavigationBarItem(
                selected = tab == 1,
                onClick = { tab = 1 },
                icon = { Text("↗", fontSize = 21.sp, fontWeight = FontWeight.Bold) },
                label = { Text("Tendência") }
            )
            NavigationBarItem(
                selected = tab == 2,
                onClick = { tab = 2 },
                icon = { Text("≡", fontSize = 21.sp, fontWeight = FontWeight.Bold) },
                label = { Text("Pesquisas") }
            )
            NavigationBarItem(
                selected = tab == 3,
                onClick = { tab = 3 },
                icon = { Text("◎", fontSize = 20.sp, fontWeight = FontWeight.Bold) },
                label = { Text("Diagnóstico") }
            )
        }
    }
}

@Composable
private fun HomeScreen(
    data: DashboardData?,
    loading: Boolean,
    error: String?,
    notice: String?,
    onRefresh: () -> Unit
) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(18.dp, 22.dp, 18.dp, 34.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        item { Header() }
        item { StatusCard(data?.snapshot, loading, error, notice, onRefresh) }

        if (data != null) {
            item { QualityCard(data.snapshot.quality) }
            item { SectionTitle("Apoio agregado nas pesquisas", "Pesquisas individuais deduplicadas e ponderadas") }
            items(data.snapshot.candidates, key = { it.id }) { CandidateCard(it) }

            item { SectionTitle("Evolução observada", "Histórico reconstruído + leituras atuais") }
            item { HistoryChart(data.history, data.snapshot.candidates.take(5)) }
            item { VariationCard(data.snapshot.candidates) }

            if (data.snapshot.runoffScenarios.isNotEmpty()) {
                item { SectionTitle("Cenários de 2º turno", "Cada confronto é agregado separadamente") }
                items(data.snapshot.runoffScenarios.take(4), key = { it.id }) { RunoffCard(it) }
            }

            item { SectionTitle("Fontes e validação", "Fontes atuais e estado de cada coleta") }
            items(data.snapshot.sources, key = { it.id }) { SourceCard(it) }
            item { MethodologyCard(data.snapshot) }
        } else if (loading) {
            item { LoadingBlock() }
        }
    }
}

@Composable
private fun TrendScreen(data: DashboardData?, loading: Boolean) {
    var period by remember { mutableIntStateOf(30) }
    val analysis = remember(data, period) { data?.let { TrendEngine.analyze(it, period) } }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(18.dp, 22.dp, 18.dp, 34.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        item {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("TENDÊNCIA E COMPARAÇÃO", color = BrazilGreen, fontWeight = FontWeight.Bold, fontSize = 13.sp)
                Text("Movimento das\npesquisas", fontSize = 36.sp, lineHeight = 38.sp, fontWeight = FontWeight.ExtraBold)
                Text(
                    "Acompanhe a variação observada nas pesquisas. Esta tela não transforma a curva em previsão própria de resultado eleitoral.",
                    color = Muted,
                    lineHeight = 21.sp
                )
            }
        }
        item {
            LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                items(listOf(5, 15, 30, 60, 90)) { days ->
                    FilterChip(
                        selected = period == days,
                        onClick = { period = days },
                        label = { Text("${days} dias") }
                    )
                }
            }
        }

        if (analysis != null && data != null) {
            item { TrendStatusCard(analysis, data.snapshot.quality) }
            item { SectionTitle("Curva de apoio", "Linha contínua = apoio agregado observado") }
            item { TrendChart(analysis, data.snapshot.candidates.take(5)) }

            item { SectionTitle("Mudança na janela", "Variação e inclinação estatística dentro do período escolhido") }
            items(analysis.candidates, key = { "trend-${it.id}" }) { CandidateTrendCard(it) }

            val marketCandidates = data.snapshot.candidates.filter { it.marketSignal != null }
            if (marketCandidates.isNotEmpty()) {
                item {
                    SectionTitle(
                        "Mercado de previsão · sinal externo",
                        "Informação separada; não entra na média das pesquisas"
                    )
                }
                items(marketCandidates, key = { "market-${it.id}" }) { MarketSignalCard(it) }
            }

            if (data.snapshot.runoffScenarios.isNotEmpty()) {
                item { SectionTitle("Comparação de 2º turno", "Resultados agregados por confronto pesquisado") }
                items(data.snapshot.runoffScenarios, key = { "runoff-${it.id}" }) { RunoffCard(it) }
            }

            item { TrendMethodCard(analysis) }
        } else if (loading) {
            item { LoadingBlock() }
        }
    }
}

@Composable
private fun PollsScreen(data: DashboardData?, loading: Boolean) {
    var periodDays by remember { mutableIntStateOf(30) }

    val filtered = remember(data, periodDays) {
        if (data == null) {
            emptyList()
        } else {
            val reference = runCatching {
                Instant.parse(data.snapshot.generatedAt)
                    .atZone(ZoneId.of("America/Sao_Paulo"))
                    .toLocalDate()
            }.getOrElse { LocalDate.now() }
            val cutoff = reference.minusDays(periodDays.toLong())
            data.polls.filter { poll ->
                runCatching { !LocalDate.parse(poll.date).isBefore(cutoff) }.getOrDefault(false)
            }
        }
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(18.dp, 22.dp, 18.dp, 34.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        item {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("BANCO DE PESQUISAS", color = BrazilGreen, fontWeight = FontWeight.Bold, fontSize = 13.sp)
                Text("Matéria-prima\ndo agregador", fontSize = 36.sp, lineHeight = 38.sp, fontWeight = FontWeight.ExtraBold)
                Text(
                    "Consulte os levantamentos que alimentam a curva: data, instituto, amostra, método, registro e resultados publicados.",
                    color = Muted,
                    lineHeight = 21.sp
                )
            }
        }

        item {
            LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                items(listOf(7, 30, 90, 365)) { days ->
                    FilterChip(
                        selected = periodDays == days,
                        onClick = { periodDays = days },
                        label = { Text(if (days == 365) "Ano" else "${days} dias") }
                    )
                }
            }
        }

        if (data != null) {
            item { PollDatabaseSummary(filtered) }
            items(
                filtered,
                key = { it.registration ?: "${it.date}-${it.institute}-${it.sample}" }
            ) { poll ->
                PollRecordCard(poll, data.snapshot.candidates)
            }
            if (filtered.isEmpty()) {
                item {
                    Card(shape = RoundedCornerShape(20.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
                        Text(
                            "Não há pesquisas no período selecionado.",
                            Modifier.padding(18.dp),
                            color = Muted
                        )
                    }
                }
            }
        } else if (loading) {
            item { LoadingBlock() }
        }
    }
}

@Composable
private fun PollDatabaseSummary(polls: List<PollRecord>) {
    val institutes = polls.map { it.institute }.distinct().size
    val methods = polls.map { it.method }.distinct().size
    val registrations = polls.count { !it.registration.isNullOrBlank() }

    Card(shape = RoundedCornerShape(22.dp), colors = CardDefaults.cardColors(containerColor = BrazilBlue)) {
        Column(Modifier.padding(17.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("RECORTE SELECIONADO", color = Color(0xFFBFD3EF), fontSize = 12.sp, fontWeight = FontWeight.Bold)
            Text("${polls.size} pesquisas", color = Color.White, fontSize = 25.sp, fontWeight = FontWeight.ExtraBold)
            Text(
                "${institutes} institutos · ${methods} métodos de coleta · ${registrations} com número de registro",
                color = Color.White.copy(alpha = .9f),
                lineHeight = 19.sp
            )
        }
    }
}

@Composable
private fun PollRecordCard(poll: PollRecord, candidates: List<Candidate>) {
    Card(shape = RoundedCornerShape(20.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(
                Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.Top
            ) {
                Column(Modifier.weight(1f)) {
                    Text(poll.institute, fontWeight = FontWeight.ExtraBold, fontSize = 17.sp)
                    Text(formatPollDate(poll.date), color = Muted, fontSize = 12.sp)
                }
                Surface(color = Color(0xFFEAF2ED), shape = RoundedCornerShape(50)) {
                    Text(
                        poll.sample.toString(),
                        Modifier.padding(horizontal = 10.dp, vertical = 6.dp),
                        color = BrazilGreen,
                        fontSize = 11.sp,
                        fontWeight = FontWeight.ExtraBold
                    )
                }
            }

            MetricRow("Método", poll.method)
            poll.registration?.let { registration ->
                MetricRow(
                    if (poll.verifiedTse) "Registro TSE validado" else "Registro TSE informado",
                    registration
                )
            }

            HorizontalDivider(color = Color(0xFFE8ECE9))

            candidates.forEach { candidate ->
                poll.candidates[candidate.id]?.let { value ->
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Box(Modifier.size(7.dp).background(candidateColor(candidate.id), CircleShape))
                            Spacer(Modifier.width(6.dp))
                            Text(candidate.name, fontSize = 13.sp)
                        }
                        Text("${value.one()}%", fontWeight = FontWeight.Bold, fontSize = 13.sp)
                    }
                }
            }
        }
    }
}

@Composable
private fun DiagnosticsScreen(data: DashboardData?, loading: Boolean) {
    var mode by remember { mutableIntStateOf(0) }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(18.dp, 22.dp, 18.dp, 34.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        item {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("CALIBRAÇÃO E CONTROLE", color = BrazilGreen, fontWeight = FontWeight.Bold, fontSize = 13.sp)
                Text("Diagnóstico\ndo agregador", fontSize = 36.sp, lineHeight = 38.sp, fontWeight = FontWeight.ExtraBold)
                Text(
                    "Mede diferenças entre fontes e o erro retrospectivo do agregador. Os diagnósticos não alteram automaticamente a média eleitoral.",
                    color = Muted,
                    lineHeight = 21.sp
                )
            }
        }

        if (data != null) {
            item { CalibrationPolicyCard(data.calibration) }
            item { RollingValidationCard(data.calibration.rollingValidation) }

            item {
                SectionTitle(
                    "Efeito de fonte",
                    "Comparação com pesquisas contemporâneas de outros institutos"
                )
            }

            item {
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    FilterChip(
                        selected = mode == 0,
                        onClick = { mode = 0 },
                        label = { Text("Institutos") }
                    )
                    FilterChip(
                        selected = mode == 1,
                        onClick = { mode = 1 },
                        label = { Text("Métodos") }
                    )
                }
            }

            val diagnostics = if (mode == 0) {
                data.calibration.instituteDiagnostics
            } else {
                data.calibration.methodDiagnostics
            }

            items(diagnostics, key = { "${mode}-${it.label}" }) { diagnostic ->
                SourceDiagnosticCard(diagnostic)
            }

            item {
                SectionTitle(
                    "Backtest histórico",
                    "Eleições anteriores usadas apenas como conjunto separado de validação"
                )
            }
            if (data.historicalBacktests.isEmpty()) {
                item {
                    Card(shape = RoundedCornerShape(22.dp), colors = CardDefaults.cardColors(containerColor = Color(0xFFFFF8E7))) {
                        Text(
                            "Nenhum estudo histórico disponível nesta leitura.",
                            Modifier.padding(17.dp),
                            color = Muted
                        )
                    }
                }
            } else {
                items(data.historicalBacktests, key = { "historical-${it.year}-${it.round}" }) {
                    HistoricalBacktestCard(it)
                }
            }
        } else if (loading) {
            item { LoadingBlock() }
        }
    }
}

@Composable
private fun CalibrationPolicyCard(calibration: CalibrationData) {
    val active = calibration.correctionApplied
    Card(
        shape = RoundedCornerShape(22.dp),
        colors = CardDefaults.cardColors(
            containerColor = if (active) Color(0xFFFFF8E7) else Color(0xFFEAF2ED)
        )
    ) {
        Column(Modifier.padding(17.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("Uso dos diagnósticos", fontWeight = FontWeight.ExtraBold, fontSize = 18.sp)
            Text(
                if (active) "Há ajuste de calibração ativo." else "Nenhuma correção automática está ativa.",
                color = if (active) Color(0xFF9A6700) else BrazilGreen,
                fontWeight = FontWeight.Bold
            )
            Text(calibration.correctionPolicy, color = Muted, lineHeight = 19.sp)
            Text(
                "Janela de comparação entre fontes: ±${calibration.peerWindowDays} dias.",
                color = Muted,
                fontSize = 12.sp
            )
        }
    }
}

@Composable
private fun RollingValidationCard(validation: RollingValidation) {
    Card(shape = RoundedCornerShape(22.dp), colors = CardDefaults.cardColors(containerColor = BrazilBlue)) {
        Column(Modifier.padding(17.dp), verticalArrangement = Arrangement.spacedBy(9.dp)) {
            Text("VALIDAÇÃO RETROSPECTIVA", color = Color(0xFFBFD3EF), fontSize = 12.sp, fontWeight = FontWeight.Bold)
            if (validation.status == "ok") {
                Text(
                    "${validation.caseCount} pesquisas-alvo",
                    color = Color.White,
                    fontSize = 24.sp,
                    fontWeight = FontWeight.ExtraBold
                )
                MetricRowLight("Comparações candidato/pesquisa", validation.comparisonCount.toString())
                validation.meanAbsoluteError?.let {
                    MetricRowLight("Erro absoluto médio", "${it.one()} p.p.")
                }
                validation.medianAbsoluteError?.let {
                    MetricRowLight("Erro absoluto mediano", "${it.one()} p.p.")
                }
                validation.simpleMeanAbsoluteError?.let {
                    MetricRowLight("MAE da média simples", "${it.one()} p.p.")
                }
                validation.errorDifferenceVsSimple?.let {
                    MetricRowLight(
                        "Diferença de erro vs média simples",
                        "${signed(it)} p.p."
                    )
                }
                validation.intervalCoverage?.let {
                    MetricRowLight("Cobertura dos intervalos", "${it.one()}%")
                }
                Text(
                    "O alvo é a próxima pesquisa publicada, não o resultado da eleição.",
                    color = Color(0xFFD8E8FF),
                    fontSize = 12.sp,
                    lineHeight = 17.sp
                )
            } else {
                Text("Dados ainda insuficientes para validação retrospectiva.", color = Color.White)
            }
        }
    }
}

@Composable
private fun MetricRowLight(label: String, value: String) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, color = Color(0xFFD8E8FF), fontSize = 13.sp)
        Text(value, color = Color.White, fontWeight = FontWeight.Bold)
    }
}

@Composable
private fun SourceDiagnosticCard(diagnostic: SourceDiagnostic) {
    Card(shape = RoundedCornerShape(20.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(9.dp)) {
            Text(diagnostic.label, fontWeight = FontWeight.ExtraBold, fontSize = 17.sp)
            Text(
                "${diagnostic.pollCount} pesquisas · ${diagnostic.comparisonCount} comparações válidas",
                color = Muted,
                fontSize = 12.sp
            )
            MetricRow("Desvio absoluto médio", "${diagnostic.meanAbsoluteDeviation.one()} p.p.")
            MetricRow("Dispersão dos resíduos", "${diagnostic.residualSd.one()} p.p.")

            if (diagnostic.candidateOffsets.isNotEmpty()) {
                HorizontalDivider(color = Color(0xFFE8ECE9))
                Text(
                    "Diferença média em relação aos pares",
                    color = Muted,
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Bold
                )
                diagnostic.candidateOffsets.forEach { offset ->
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Text(offset.name, fontSize = 13.sp)
                        Text(
                            "${signed(offset.meanOffset)} p.p.",
                            fontWeight = FontWeight.Bold,
                            fontSize = 13.sp,
                            color = Muted
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun HistoricalBacktestCard(study: HistoricalBacktestStudy) {
    Card(shape = RoundedCornerShape(22.dp), colors = CardDefaults.cardColors(containerColor = Color(0xFFFFF8E7))) {
        Column(Modifier.padding(17.dp), verticalArrangement = Arrangement.spacedBy(9.dp)) {
            Text("${study.year} · ${study.round}", fontWeight = FontWeight.ExtraBold, fontSize = 18.sp)
            Text(
                "${study.pollCountTotal} pesquisas históricas indexadas",
                color = Muted,
                fontSize = 12.sp
            )
            if (study.status == "ok") {
                study.averageWeightedMae?.let {
                    MetricRow("MAE médio · ponderado", "${it.one()} p.p.")
                }
                study.averageSimpleMae?.let {
                    MetricRow("MAE médio · média simples", "${it.one()} p.p.")
                }
                HorizontalDivider(color = Color(0xFFE8DDBD))
                Text("Erro por distância da eleição", fontWeight = FontWeight.Bold, fontSize = 13.sp)
                study.horizons.forEach { horizon ->
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Text(
                            "${horizon.daysBeforeElection} dias · ${horizon.pollCount} pesquisas / ${horizon.instituteCount} institutos",
                            color = Muted,
                            fontSize = 12.sp,
                            modifier = Modifier.weight(1f)
                        )
                        horizon.weightedMae?.let {
                            Text("${it.one()} p.p.", fontWeight = FontWeight.Bold, fontSize = 12.sp)
                        }
                    }
                }
            } else {
                Text("Dados históricos insuficientes para este estudo.", color = Muted)
            }
            Text(
                study.note,
                color = Muted,
                fontSize = 12.sp,
                lineHeight = 17.sp
            )
            Text(
                if (study.correctionApplied) "Há correção histórica ativa." else "Nenhuma correção histórica é aplicada à leitura de 2026.",
                color = if (study.correctionApplied) Color(0xFF9A6700) else BrazilGreen,
                fontSize = 12.sp,
                fontWeight = FontWeight.Bold
            )
        }
    }
}

@Composable
private fun Header() {
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(12.dp).background(BrazilGreen, CircleShape))
            Spacer(Modifier.width(8.dp))
            Text("BRASIL · ELEIÇÃO 2026", color = BrazilGreen, fontWeight = FontWeight.Bold, fontSize = 13.sp)
        }
        Text("Termômetro\nPresidencial", fontSize = 38.sp, lineHeight = 40.sp, fontWeight = FontWeight.ExtraBold)
        Text(
            "Agregação transparente de pesquisas públicas, com incerteza, histórico e validação de registros.",
            color = Muted,
            lineHeight = 21.sp
        )
    }
}

@Composable
private fun StatusCard(
    snapshot: Snapshot?,
    loading: Boolean,
    error: String?,
    notice: String?,
    onRefresh: () -> Unit
) {
    Card(shape = RoundedCornerShape(24.dp), colors = CardDefaults.cardColors(containerColor = BrazilBlue)) {
        Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(11.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Column {
                    Text("ÚLTIMA LEITURA", color = Color(0xFFBFD3EF), fontSize = 12.sp, fontWeight = FontWeight.Bold)
                    Text(snapshot?.generatedAt?.let(::formatDate) ?: "Buscando dados…", color = Color.White, fontWeight = FontWeight.SemiBold)
                }
                snapshot?.let {
                    Surface(color = Color.White.copy(alpha = .12f), shape = RoundedCornerShape(50)) {
                        Text("${it.daysToElection} dias", Modifier.padding(horizontal = 12.dp, vertical = 7.dp), color = Color.White, fontWeight = FontWeight.Bold)
                    }
                }
            }
            Button(
                onClick = onRefresh,
                enabled = !loading,
                modifier = Modifier.fillMaxWidth(),
                colors = ButtonDefaults.buttonColors(containerColor = Color.White, contentColor = BrazilBlue)
            ) {
                AnimatedContent(loading, label = "refresh") { active ->
                    Text(if (active) "Verificando fontes…" else "Atualizar leitura", fontWeight = FontWeight.Bold)
                }
            }
            notice?.let { Text(it, color = Color(0xFFD8E8FF), fontSize = 13.sp, lineHeight = 18.sp) }
            error?.let { Text(it, color = Color(0xFFFFD6D1), fontSize = 13.sp) }
        }
    }
}

@Composable
private fun QualityCard(q: QualityInfo) {
    Card(shape = RoundedCornerShape(22.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
        Column(Modifier.padding(17.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("Qualidade da leitura", fontWeight = FontWeight.ExtraBold, fontSize = 19.sp)
                Surface(color = Color(0xFFEAF2ED), shape = RoundedCornerShape(50)) {
                    Text(q.confidence.uppercase(), Modifier.padding(horizontal = 10.dp, vertical = 6.dp), color = BrazilGreen, fontSize = 11.sp, fontWeight = FontWeight.ExtraBold)
                }
            }
            MetricRow("Pesquisas na janela", q.pollCount.toString())
            MetricRow("Institutos diferentes", q.instituteCount.toString())
            MetricRow("Métodos de coleta diferentes", q.methodCount.toString())
            MetricRow("Pesquisas com nº de registro TSE", q.registrationCount.toString())
            if (q.verifiedTseCount > 0) {
                MetricRow("Registros validados diretamente", q.verifiedTseCount.toString())
            }
            MetricRow("Idade média dos levantamentos", "${q.averageAgeDays.one()} dias")
            MetricRow("Pesquisas efetivas após ponderação", q.effectivePolls.one())
        }
    }
}

@Composable
private fun MetricRow(label: String, value: String) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, color = Muted, fontSize = 13.sp)
        Text(value, fontWeight = FontWeight.Bold, color = TextDark)
    }
}

@Composable
private fun CandidateCard(candidate: Candidate) {
    val deltaColor = when {
        candidate.change > .09 -> Positive
        candidate.change < -.09 -> Negative
        else -> Muted
    }
    Card(shape = RoundedCornerShape(20.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(42.dp).background(candidateColor(candidate.id), CircleShape), contentAlignment = Alignment.Center) {
                        Text(candidate.name.take(1), color = Color.White, fontWeight = FontWeight.ExtraBold)
                    }
                    Spacer(Modifier.width(11.dp))
                    Column {
                        Text(candidate.name, fontWeight = FontWeight.Bold, fontSize = 17.sp)
                        Text(
                            "Intervalo: ${candidate.intervalLow.one()}% – ${candidate.intervalHigh.one()}%",
                            color = Muted,
                            fontSize = 12.sp
                        )
                    }
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text("${candidate.pollingSupport.one()}%", fontSize = 24.sp, fontWeight = FontWeight.ExtraBold, color = BrazilBlue)
                    Text(deltaText(candidate.change), color = deltaColor, fontSize = 12.sp, fontWeight = FontWeight.Bold)
                }
            }
            LinearProgressIndicator(
                progress = { (candidate.pollingSupport / 100.0).toFloat().coerceIn(0f, 1f) },
                modifier = Modifier.fillMaxWidth().height(7.dp),
                color = candidateColor(candidate.id),
                trackColor = Color(0xFFE8ECE9),
                strokeCap = StrokeCap.Round
            )
        }
    }
}

@Composable
private fun HistoryChart(history: List<HistoryPoint>, candidates: List<Candidate>) {
    Card(shape = RoundedCornerShape(22.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            if (history.size < 2) {
                Text("Ainda há pouco histórico para desenhar a curva.", color = Muted)
            } else {
                LazyRow(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    items(candidates, key = { "legend-${it.id}" }) { c ->
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Box(Modifier.size(8.dp).background(candidateColor(c.id), CircleShape))
                            Spacer(Modifier.width(4.dp))
                            Text(c.name, fontSize = 11.sp, color = Muted)
                        }
                    }
                }
                val shown = history.takeLast(120)
                Canvas(Modifier.fillMaxWidth().height(205.dp)) {
                    val all = shown.flatMap { p -> candidates.mapNotNull { c -> p.pollingSupport[c.id] } }
                    val rawMin = all.minOrNull() ?: 0.0
                    val rawMax = all.maxOrNull() ?: 50.0
                    val minY = (rawMin - 3.0).coerceAtLeast(0.0)
                    val maxY = (rawMax + 3.0).coerceAtMost(100.0).coerceAtLeast(minY + 10.0)
                    for (g in 0..4) {
                        val y = size.height * g / 4f
                        drawLine(Color(0xFFE7ECE8), Offset(0f, y), Offset(size.width, y), strokeWidth = 1f)
                    }
                    candidates.forEach { candidate ->
                        val path = Path()
                        shown.forEachIndexed { index, point ->
                            val value = point.pollingSupport[candidate.id] ?: return@forEachIndexed
                            val x = if (shown.size == 1) 0f else size.width * index / (shown.size - 1f)
                            val y = size.height - (((value - minY) / (maxY - minY)) * size.height).toFloat()
                            if (path.isEmpty) path.moveTo(x, y) else path.lineTo(x, y)
                        }
                        if (!path.isEmpty) drawPath(path, candidateColor(candidate.id), style = Stroke(width = 4f, cap = StrokeCap.Round))
                    }
                }
            }
        }
    }
}

@Composable
private fun VariationCard(candidates: List<Candidate>) {
    Card(shape = RoundedCornerShape(22.dp), colors = CardDefaults.cardColors(containerColor = Color(0xFFEAF2ED))) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(9.dp)) {
            Text("Variação desde a leitura anterior", fontWeight = FontWeight.Bold, fontSize = 17.sp)
            candidates.forEach { c ->
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text(c.name)
                    val color = if (c.change > .09) Positive else if (c.change < -.09) Negative else Muted
                    Text(deltaText(c.change), color = color, fontWeight = FontWeight.Bold)
                }
            }
        }
    }
}

@Composable
private fun TrendStatusCard(analysis: TrendAnalysis, quality: QualityInfo) {
    Card(shape = RoundedCornerShape(24.dp), colors = CardDefaults.cardColors(containerColor = BrazilBlue)) {
        Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("JANELA ANALISADA", color = Color(0xFFBFD3EF), fontSize = 12.sp, fontWeight = FontWeight.Bold)
            Text("${analysis.periodDays} dias", color = Color.White, fontSize = 25.sp, fontWeight = FontWeight.ExtraBold)
            Text(
                "Cobertura disponível: ${analysis.availableSpanDays.one()} dias · Qualidade da tendência: ${analysis.confidence}",
                color = Color.White.copy(alpha = .9f)
            )
            Text(
                "${analysis.historicalPoints} pontos reconstruídos + ${analysis.livePoints} leituras atuais · ${quality.instituteCount} institutos",
                color = Color(0xFFCDE9DA),
                fontSize = 13.sp
            )
        }
    }
}

@Composable
private fun TrendChart(analysis: TrendAnalysis, candidates: List<Candidate>) {
    Card(shape = RoundedCornerShape(22.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            if (analysis.points.size < 2) {
                Text("Ainda não há pontos suficientes nesta janela.", color = Muted)
            } else {
                LazyRow(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    items(candidates, key = { "trend-legend-${it.id}" }) { c ->
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Box(Modifier.size(8.dp).background(candidateColor(c.id), CircleShape))
                            Spacer(Modifier.width(4.dp))
                            Text(c.name, fontSize = 11.sp, color = Muted)
                        }
                    }
                }
                Canvas(Modifier.fillMaxWidth().height(230.dp)) {
                    val all = analysis.points.flatMap { p -> candidates.mapNotNull { c -> p.support[c.id] } }
                    val minY = ((all.minOrNull() ?: 0.0) - 3.0).coerceAtLeast(0.0)
                    val maxY = ((all.maxOrNull() ?: 50.0) + 3.0).coerceAtMost(100.0).coerceAtLeast(minY + 10.0)
                    val start = analysis.points.first().instant.toEpochMilli()
                    val end = analysis.points.last().instant.toEpochMilli()
                    val span = (end - start).coerceAtLeast(1L)

                    fun xOf(point: TrendCurvePoint) = (size.width * (point.instant.toEpochMilli() - start).toDouble() / span).toFloat()
                    fun yOf(value: Double) = size.height - (((value - minY) / (maxY - minY)) * size.height).toFloat()

                    for (g in 0..4) {
                        val y = size.height * g / 4f
                        drawLine(Color(0xFFE7ECE8), Offset(0f, y), Offset(size.width, y), strokeWidth = 1f)
                    }
                    candidates.forEach { candidate ->
                        val path = Path()
                        analysis.points.forEach { point ->
                            point.support[candidate.id]?.let { value ->
                                val x = xOf(point)
                                val y = yOf(value)
                                if (path.isEmpty) path.moveTo(x, y) else path.lineTo(x, y)
                            }
                        }
                        if (!path.isEmpty) drawPath(path, candidateColor(candidate.id), style = Stroke(width = 4f, cap = StrokeCap.Round))
                    }
                }
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text(formatDay(analysis.points.first().instant), color = Muted, fontSize = 11.sp)
                    Text("observado", color = Muted, fontSize = 11.sp)
                    Text(formatDay(analysis.points.last().instant), color = Muted, fontSize = 11.sp)
                }
            }
        }
    }
}

@Composable
private fun CandidateTrendCard(trend: CandidateTrend) {
    val color = when {
        trend.changeInWindow > .09 -> Positive
        trend.changeInWindow < -.09 -> Negative
        else -> Muted
    }
    Card(shape = RoundedCornerShape(18.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
        Column(Modifier.padding(15.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(trend.name, fontWeight = FontWeight.Bold)
                Text("${trend.current.one()}%", fontWeight = FontWeight.ExtraBold, color = BrazilBlue)
            }
            MetricRow("Mudança na janela", deltaText(trend.changeInWindow))
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text("Inclinação observada", color = Muted, fontSize = 13.sp)
                Text("${signed(trend.slopePerDay)} p.p./dia", color = color, fontWeight = FontWeight.Bold)
            }
        }
    }
}

@Composable
private fun MarketSignalCard(candidate: Candidate) {
    Card(shape = RoundedCornerShape(18.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
        Row(Modifier.fillMaxWidth().padding(15.dp), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(candidate.name, fontWeight = FontWeight.Bold)
            Text("${candidate.marketSignal?.one()}%", color = BrazilBlue, fontWeight = FontWeight.ExtraBold)
        }
    }
}

@Composable
private fun RunoffCard(scenario: RunoffScenario) {
    Card(shape = RoundedCornerShape(20.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Text(scenario.label, fontWeight = FontWeight.ExtraBold, fontSize = 17.sp)
            Text("${scenario.pollCount} pesquisas · ${scenario.instituteCount} institutos", color = Muted, fontSize = 12.sp)
            scenario.candidates.forEach { c ->
                Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                        Text(c.name, fontWeight = FontWeight.SemiBold)
                        Text("${c.support.one()}%", fontWeight = FontWeight.ExtraBold, color = BrazilBlue)
                    }
                    Text("${c.intervalLow.one()}% – ${c.intervalHigh.one()}%", color = Muted, fontSize = 12.sp)
                }
            }
        }
    }
}

@Composable
private fun SourceCard(source: SourceInfo) {
    val ok = source.status.equals("ok", true)
    Card(shape = RoundedCornerShape(18.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
        Row(Modifier.fillMaxWidth().padding(15.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(10.dp).background(if (ok) Positive else Color(0xFFD97706), CircleShape))
            Spacer(Modifier.width(10.dp))
            Column(Modifier.weight(1f)) {
                Text(source.label, fontWeight = FontWeight.Bold)
                Text(source.type, color = Muted, fontSize = 12.sp)
            }
            Text(if (ok) "ATIVA" else "FALLBACK", fontSize = 11.sp, fontWeight = FontWeight.ExtraBold, color = if (ok) Positive else Color(0xFFD97706))
        }
    }
}

@Composable
private fun MethodologyCard(snapshot: Snapshot) {
    Card(shape = RoundedCornerShape(22.dp), colors = CardDefaults.cardColors(containerColor = Color(0xFFFFF8E7))) {
        Column(Modifier.padding(17.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("Como a leitura é calculada", fontWeight = FontWeight.ExtraBold, fontSize = 18.sp)
            Text(
                "Cada pesquisa individual entra uma única vez. O peso considera recência, tamanho da amostra e repetição do mesmo instituto. O intervalo combina incerteza amostral aproximada e divergência entre levantamentos.",
                lineHeight = 20.sp
            )
            Text("Mercados de previsão aparecem separadamente e não alteram a média das pesquisas.", color = BrazilBlue, fontWeight = FontWeight.Bold)
            HorizontalDivider(color = Color(0xFFE8DDBD))
            Text(snapshot.note, color = Muted, fontSize = 12.sp, lineHeight = 17.sp)
        }
    }
}

@Composable
private fun TrendMethodCard(analysis: TrendAnalysis) {
    Card(shape = RoundedCornerShape(22.dp), colors = CardDefaults.cardColors(containerColor = Color(0xFFFFF8E7))) {
        Column(Modifier.padding(17.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("Como ler a tendência", fontWeight = FontWeight.ExtraBold, fontSize = 18.sp)
            Text(
                "A inclinação resume o movimento observado dentro de ${analysis.periodDays} dias. Ela descreve a série passada e recente; não é extrapolada como probabilidade de vitória futura.",
                lineHeight = 20.sp
            )
            Text("Qualidade da série: ${analysis.confidence}", color = BrazilBlue, fontWeight = FontWeight.Bold)
        }
    }
}

@Composable
private fun SectionTitle(title: String, subtitle: String) {
    Column(Modifier.padding(top = 6.dp)) {
        Text(title, fontWeight = FontWeight.ExtraBold, fontSize = 22.sp)
        Text(subtitle, color = Muted, fontSize = 13.sp)
    }
}

@Composable
private fun LoadingBlock() {
    Card(shape = RoundedCornerShape(22.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
        Row(Modifier.fillMaxWidth().padding(24.dp), verticalAlignment = Alignment.CenterVertically) {
            CircularProgressIndicator(Modifier.size(28.dp), strokeWidth = 3.dp)
            Spacer(Modifier.width(14.dp))
            Text("Carregando pesquisas e histórico…", color = Muted)
        }
    }
}

private fun refreshFeedback(before: DashboardData?, fresh: DashboardData): String {
    if (before == null) return "Leitura carregada."
    if (before.snapshot.generatedAt == fresh.snapshot.generatedAt) {
        return "Nenhuma nova leitura foi publicada desde ${formatDate(fresh.snapshot.generatedAt)}."
    }
    val old = before.snapshot.candidates.associateBy { it.id }
    val changed = fresh.snapshot.candidates.any { candidate ->
        abs(candidate.pollingSupport - (old[candidate.id]?.pollingSupport ?: candidate.pollingSupport)) >= 0.05
    }
    return if (changed) {
        "Nova leitura incorporada. Houve mudança mensurável no apoio agregado."
    } else {
        "Fontes verificadas e nova leitura recebida, sem mudança relevante nos percentuais."
    }
}

private fun candidateColor(id: String): Color = when (id) {
    "lula" -> Color(0xFFC43A3A)
    "flavio-bolsonaro" -> Color(0xFF2867B2)
    "augusto-cury" -> Color(0xFF7B5BB5)
    "renan-santos" -> Color(0xFF2A8B76)
    "ronaldo-caiado" -> Color(0xFFB2761B)
    "romeu-zema" -> Color(0xFF4C6678)
    "pablo-marcal" -> Color(0xFF7A4D2C)
    else -> Color(0xFF6B7280)
}

private fun Double.one() = String.format(java.util.Locale("pt", "BR"), "%.1f", this)
private fun signed(value: Double): String = if (value > 0) "+${value.one()}" else value.one()
private fun deltaText(value: Double): String = when {
    abs(value) < .05 -> "sem variação"
    value > 0 -> "+${value.one()} p.p."
    else -> "${value.one()} p.p."
}

private fun formatDate(raw: String): String = runCatching {
    val instant = Instant.parse(raw)
    DateTimeFormatter.ofPattern("dd/MM · HH:mm").withZone(ZoneId.of("America/Sao_Paulo")).format(instant)
}.getOrElse { raw }

private fun formatPollDate(raw: String): String = runCatching {
    LocalDate.parse(raw).format(DateTimeFormatter.ofPattern("dd/MM/yyyy"))
}.getOrElse { raw }

private fun formatDay(instant: Instant): String =
    DateTimeFormatter.ofPattern("dd/MM").withZone(ZoneId.of("America/Sao_Paulo")).format(instant)
