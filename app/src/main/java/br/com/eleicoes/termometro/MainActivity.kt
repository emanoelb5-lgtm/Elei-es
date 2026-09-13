package br.com.eleicoes.termometro

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.animation.AnimatedContent
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
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
import androidx.compose.ui.graphics.PathEffect
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
        ),
        typography = Typography(
            headlineLarge = MaterialTheme.typography.headlineLarge.copy(fontWeight = FontWeight.ExtraBold),
            titleLarge = MaterialTheme.typography.titleLarge.copy(fontWeight = FontWeight.Bold)
        )
    ) {
        Surface(Modifier.fillMaxSize(), color = SoftBg) {
            Box(
                modifier = Modifier
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
    val repo = remember { ElectionRepository() }
    val scope = rememberCoroutineScope()
    var data by remember { mutableStateOf<DashboardData?>(null) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf<String?>(null) }
    var selectedTab by remember { mutableIntStateOf(0) }

    fun refresh() {
        loading = true
        error = null
        scope.launch {
            runCatching { withContext(Dispatchers.IO) { repo.load() } }
                .onSuccess { data = it }
                .onFailure { error = "Não foi possível atualizar agora. Verifique a conexão e tente novamente." }
            loading = false
        }
    }

    LaunchedEffect(Unit) { refresh() }

    Column(Modifier.fillMaxSize()) {
        Box(Modifier.weight(1f).fillMaxWidth()) {
            if (selectedTab == 0) {
                HomeDashboard(data, loading, error, onRefresh = { refresh() })
            } else {
                ForecastScreen(data, loading)
            }
        }
        NavigationBar(containerColor = Color.White) {
            NavigationBarItem(
                selected = selectedTab == 0,
                onClick = { selectedTab = 0 },
                icon = { Text("⌂", fontSize = 22.sp, fontWeight = FontWeight.Bold) },
                label = { Text("Início") }
            )
            NavigationBarItem(
                selected = selectedTab == 1,
                onClick = { selectedTab = 1 },
                icon = { Text("↗", fontSize = 21.sp, fontWeight = FontWeight.Bold) },
                label = { Text("Previsão") }
            )
        }
    }
}

@Composable
private fun HomeDashboard(data: DashboardData?, loading: Boolean, error: String?, onRefresh: () -> Unit) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 18.dp, end = 18.dp, top = 22.dp, bottom = 32.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        item { Header() }
        item { StatusCard(data?.snapshot, loading, error, onRefresh) }
        if (data != null) {
            item { SectionTitle("Probabilidade estimada de vitória", "Combinação dos sinais disponíveis") }
            items(data.snapshot.candidates.take(7), key = { it.id }) { candidate ->
                CandidateCard(candidate, data.snapshot.candidates.first().winProbability)
            }
            item { SectionTitle("Evolução das leituras", "Histórico público gerado pelo modelo") }
            item { HistoryChart(data.history, data.snapshot.candidates.take(3)) }
            item { VariationCard(data.snapshot.candidates.take(5)) }
            item { SectionTitle("Fontes monitoradas", "Atualização automática e tolerante a falhas") }
            items(data.snapshot.sources, key = { it.id }) { SourceCard(it) }
            item { MethodologyCard(data.snapshot) }
        } else if (loading) {
            item { LoadingBlock() }
        }
    }
}

@Composable
private fun ForecastScreen(data: DashboardData?, loading: Boolean) {
    var periodDays by remember { mutableIntStateOf(15) }
    val analysis = remember(data, periodDays) { data?.let { ForecastEngine.analyze(it, periodDays) } }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(start = 18.dp, end = 18.dp, top = 22.dp, bottom = 32.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        item {
            Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text("PREVISÃO E COMPARAÇÃO", color = BrazilGreen, fontWeight = FontWeight.Bold, fontSize = 13.sp)
                Text("Curva de\ntendência", fontSize = 36.sp, lineHeight = 38.sp, fontWeight = FontWeight.ExtraBold, color = TextDark)
                Text("Compare os últimos dias e veja uma projeção matemática da tendência até a eleição.", color = Muted, lineHeight = 21.sp)
            }
        }
        item {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf(5, 15, 30).forEach { days ->
                    FilterChip(
                        selected = periodDays == days,
                        onClick = { periodDays = days },
                        label = { Text("$days dias") },
                        modifier = Modifier.weight(1f)
                    )
                }
            }
        }

        if (analysis != null && data != null) {
            item { ForecastStatusCard(analysis, data.snapshot) }
            item { SectionTitle("Curva observada + projeção", "Linha contínua: histórico · tracejada: tendência futura") }
            item { ForecastChart(analysis, data.snapshot.candidates.take(3)) }
            item { SectionTitle("Probabilidade futura", "Comparação entre o valor atual e a projeção para a eleição") }
            items(analysis.candidates, key = { it.id }) { projection ->
                ProjectionCard(projection, data.snapshot.electionDate)
            }
            item { SectionTitle("Comparação dos sinais atuais", "Pesquisa, mercado e resultado combinado do modelo") }
            items(data.snapshot.candidates.take(5), key = { "signal-${it.id}" }) { candidate ->
                SignalComparisonCard(candidate)
            }
            item { ForecastMethodCard(analysis) }
        } else if (loading) {
            item { LoadingBlock() }
        }
    }
}

@Composable
private fun ForecastStatusCard(analysis: ForecastAnalysis, snapshot: Snapshot) {
    Card(shape = RoundedCornerShape(24.dp), colors = CardDefaults.cardColors(containerColor = BrazilBlue)) {
        Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("JANELA SELECIONADA", color = Color(0xFFBFD3EF), fontSize = 12.sp, fontWeight = FontWeight.Bold)
            Text("${analysis.periodDays} dias", color = Color.White, fontWeight = FontWeight.ExtraBold, fontSize = 24.sp)
            Text(
                "Histórico efetivamente disponível: ${analysis.availableSpanDays.one()} dias · Confiança da tendência: ${analysis.confidence}",
                color = Color.White.copy(alpha = .88f),
                lineHeight = 19.sp
            )
            Text("Projeção até ${formatElectionDate(snapshot.electionDate)}", color = Color.White, fontWeight = FontWeight.SemiBold)
        }
    }
}

@Composable
private fun ForecastChart(analysis: ForecastAnalysis, candidates: List<Candidate>) {
    val combined = analysis.actual + analysis.projected
    Card(shape = RoundedCornerShape(22.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            if (analysis.actual.size < 2) {
                Text("Ainda há pouco histórico para formar uma curva. O aplicativo continuará acumulando leituras reais automaticamente.", color = Muted)
            }
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                candidates.forEach { candidate ->
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(Modifier.size(8.dp).background(candidateColor(candidate.id), CircleShape))
                        Spacer(Modifier.width(4.dp))
                        Text(candidate.name, fontSize = 11.sp, color = Muted)
                    }
                }
            }
            if (combined.isNotEmpty()) {
                Canvas(Modifier.fillMaxWidth().height(230.dp)) {
                    val allValues = combined.flatMap { point -> candidates.mapNotNull { point.probabilities[it.id] } }
                    val rawMin = allValues.minOrNull() ?: 0.0
                    val rawMax = allValues.maxOrNull() ?: 100.0
                    val minY = (rawMin - 4.0).coerceAtLeast(0.0)
                    val maxY = (rawMax + 4.0).coerceAtMost(100.0).coerceAtLeast(minY + 10.0)
                    val startMs = combined.minOf { it.instant.toEpochMilli() }
                    val endMs = combined.maxOf { it.instant.toEpochMilli() }
                    val spanMs = (endMs - startMs).coerceAtLeast(1L)

                    fun xOf(point: ForecastCurvePoint): Float =
                        (size.width * (point.instant.toEpochMilli() - startMs).toDouble() / spanMs).toFloat()
                    fun yOf(value: Double): Float =
                        size.height - (((value - minY) / (maxY - minY)) * size.height).toFloat()

                    for (g in 0..4) {
                        val y = size.height * g / 4f
                        drawLine(Color(0xFFE7ECE8), Offset(0f, y), Offset(size.width, y), strokeWidth = 1f)
                    }

                    candidates.forEach { candidate ->
                        val actualPath = Path()
                        analysis.actual.forEachIndexed { index, point ->
                            val value = point.probabilities[candidate.id] ?: return@forEachIndexed
                            val x = xOf(point)
                            val y = yOf(value)
                            if (actualPath.isEmpty) actualPath.moveTo(x, y) else actualPath.lineTo(x, y)
                        }
                        if (!actualPath.isEmpty) {
                            drawPath(actualPath, candidateColor(candidate.id), style = Stroke(width = 5f, cap = StrokeCap.Round))
                        }

                        if (analysis.projected.isNotEmpty()) {
                            val forecastPath = Path()
                            val current = analysis.actual.lastOrNull()
                            current?.probabilities?.get(candidate.id)?.let { value ->
                                forecastPath.moveTo(xOf(current), yOf(value))
                            }
                            analysis.projected.forEach { point ->
                                point.probabilities[candidate.id]?.let { value -> forecastPath.lineTo(xOf(point), yOf(value)) }
                            }
                            if (!forecastPath.isEmpty) {
                                drawPath(
                                    forecastPath,
                                    candidateColor(candidate.id),
                                    style = Stroke(
                                        width = 4f,
                                        cap = StrokeCap.Round,
                                        pathEffect = PathEffect.dashPathEffect(floatArrayOf(14f, 10f))
                                    )
                                )
                            }
                        }
                    }
                }
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text(formatDay(combined.first().instant), color = Muted, fontSize = 11.sp)
                    Text("hoje", color = Muted, fontSize = 11.sp)
                    Text(formatDay(combined.last().instant), color = Muted, fontSize = 11.sp)
                }
            }
        }
    }
}

@Composable
private fun ProjectionCard(projection: CandidateProjection, electionDate: String) {
    val deltaColor = when {
        projection.delta > .05 -> Positive
        projection.delta < -.05 -> Negative
        else -> Muted
    }
    Card(shape = RoundedCornerShape(20.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Box(Modifier.size(12.dp).background(candidateColor(projection.id), CircleShape))
                    Spacer(Modifier.width(9.dp))
                    Text(projection.name, fontWeight = FontWeight.Bold, fontSize = 17.sp)
                }
                Text(deltaText(projection.delta), color = deltaColor, fontWeight = FontWeight.Bold)
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Column {
                    Text("Agora", color = Muted, fontSize = 12.sp)
                    Text("${projection.current.one()}%", fontSize = 24.sp, fontWeight = FontWeight.ExtraBold, color = BrazilBlue)
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text(formatElectionDate(electionDate), color = Muted, fontSize = 12.sp)
                    Text("${projection.projectedElection.one()}%", fontSize = 24.sp, fontWeight = FontWeight.ExtraBold, color = TextDark)
                }
            }
            Text("Inclinação recente: ${signed(projection.slopePerDay)} p.p./dia", color = Muted, fontSize = 12.sp)
        }
    }
}

@Composable
private fun SignalComparisonCard(candidate: Candidate) {
    Card(shape = RoundedCornerShape(18.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
        Column(Modifier.padding(15.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(9.dp).background(candidateColor(candidate.id), CircleShape))
                Spacer(Modifier.width(8.dp))
                Text(candidate.name, fontWeight = FontWeight.Bold)
            }
            SignalRow("Apoio nas pesquisas", "${candidate.pollingSupport.one()}%")
            SignalRow("Mercado de previsão", candidate.marketProbability?.let { "${it.one()}%" } ?: "indisponível")
            SignalRow("Modelo combinado", "${candidate.winProbability.one()}%", emphasize = true)
        }
    }
}

@Composable
private fun SignalRow(label: String, value: String, emphasize: Boolean = false) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
        Text(label, color = if (emphasize) TextDark else Muted, fontSize = 13.sp, fontWeight = if (emphasize) FontWeight.SemiBold else FontWeight.Normal)
        Text(value, color = if (emphasize) BrazilBlue else TextDark, fontWeight = if (emphasize) FontWeight.ExtraBold else FontWeight.SemiBold)
    }
}

@Composable
private fun ForecastMethodCard(analysis: ForecastAnalysis) {
    Card(shape = RoundedCornerShape(22.dp), colors = CardDefaults.cardColors(containerColor = Color(0xFFFFF8E7))) {
        Column(Modifier.padding(17.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            Text("Como a previsão é calculada", fontWeight = FontWeight.ExtraBold, fontSize = 18.sp)
            Text(
                "A curva usa somente leituras realmente registradas dentro da janela escolhida. As leituras são resumidas em blocos de 6 horas, a tendência recente recebe um pouco mais de peso e a extrapolação é amortecida para evitar que uma inclinação curta cresça indefinidamente.",
                color = TextDark,
                lineHeight = 20.sp
            )
            Text("Confiança da curva: ${analysis.confidence}", color = BrazilBlue, fontWeight = FontWeight.Bold)
            HorizontalDivider(color = Color(0xFFE8DDBD))
            Text("A linha tracejada é uma projeção matemática experimental, não uma pesquisa, resultado oficial ou certeza sobre o futuro. Com pouco histórico disponível, a projeção tende a ficar conservadora.", color = Muted, fontSize = 12.sp, lineHeight = 17.sp)
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
        Text("Termômetro\nPresidencial", fontSize = 38.sp, lineHeight = 40.sp, fontWeight = FontWeight.ExtraBold, color = TextDark)
        Text("Uma leitura probabilística, transparente e sempre identificada como estimativa — nunca como pesquisa oficial.", color = Muted, lineHeight = 21.sp)
    }
}

@Composable
private fun StatusCard(snapshot: Snapshot?, loading: Boolean, error: String?, onRefresh: () -> Unit) {
    Card(shape = RoundedCornerShape(24.dp), colors = CardDefaults.cardColors(containerColor = BrazilBlue)) {
        Column(Modifier.padding(18.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Column {
                    Text("ÚLTIMA LEITURA", color = Color(0xFFBFD3EF), fontSize = 12.sp, fontWeight = FontWeight.Bold)
                    Text(snapshot?.generatedAt?.let(::formatDate) ?: "Buscando dados…", color = Color.White, fontWeight = FontWeight.SemiBold)
                }
                if (snapshot != null) {
                    Surface(color = Color.White.copy(alpha = .12f), shape = RoundedCornerShape(50)) {
                        Text("${snapshot.daysToElection} dias", Modifier.padding(horizontal = 12.dp, vertical = 7.dp), color = Color.White, fontWeight = FontWeight.Bold)
                    }
                }
            }
            Button(onClick = onRefresh, enabled = !loading, modifier = Modifier.fillMaxWidth(), colors = ButtonDefaults.buttonColors(containerColor = Color.White, contentColor = BrazilBlue)) {
                AnimatedContent(loading, label = "refresh") { isLoading ->
                    Text(if (isLoading) "Atualizando leitura…" else "Atualizar leitura", fontWeight = FontWeight.Bold)
                }
            }
            if (error != null) Text(error, color = Color(0xFFFFD6D1), fontSize = 13.sp)
        }
    }
}

@Composable
private fun SectionTitle(title: String, subtitle: String) {
    Column(Modifier.padding(top = 6.dp)) {
        Text(title, fontWeight = FontWeight.ExtraBold, fontSize = 22.sp, color = TextDark)
        Text(subtitle, color = Muted, fontSize = 13.sp)
    }
}

@Composable
private fun CandidateCard(candidate: Candidate, leader: Double) {
    val deltaColor = when { candidate.change > .049 -> Positive; candidate.change < -.049 -> Negative; else -> Muted }
    Card(shape = RoundedCornerShape(20.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
        Column(Modifier.padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.Top) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Surface(shape = CircleShape, color = candidateColor(candidate.id)) {
                        Box(Modifier.size(44.dp), contentAlignment = Alignment.Center) {
                            Text(candidate.name.take(1), color = Color.White, fontWeight = FontWeight.ExtraBold)
                        }
                    }
                    Spacer(Modifier.width(12.dp))
                    Column {
                        Text(candidate.name, fontWeight = FontWeight.Bold, fontSize = 17.sp)
                        Text("Pesquisas: ${candidate.pollingSupport.one()}%" + (candidate.marketProbability?.let { " · Mercado: ${it.one()}%" } ?: ""), color = Muted, fontSize = 12.sp)
                    }
                }
                Column(horizontalAlignment = Alignment.End) {
                    Text("${candidate.winProbability.one()}%", fontWeight = FontWeight.ExtraBold, fontSize = 24.sp, color = BrazilBlue)
                    Text(deltaText(candidate.change), color = deltaColor, fontSize = 12.sp, fontWeight = FontWeight.Bold)
                }
            }
            LinearProgressIndicator(
                progress = { (candidate.winProbability / maxOf(leader, 1.0)).toFloat().coerceIn(0f, 1f) },
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
                Text("O gráfico começará a ganhar linhas após as próximas atualizações automáticas.", color = Muted)
            } else {
                Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                    candidates.forEach { c ->
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Box(Modifier.size(8.dp).background(candidateColor(c.id), CircleShape))
                            Spacer(Modifier.width(5.dp))
                            Text(c.name, fontSize = 11.sp, color = Muted)
                        }
                    }
                }
                Canvas(Modifier.fillMaxWidth().height(190.dp)) {
                    val shown = history.takeLast(40)
                    val allValues = shown.flatMap { p -> candidates.mapNotNull { c -> p.probabilities[c.id] } }
                    val minY = (allValues.minOrNull() ?: 0.0).coerceAtMost(10.0)
                    val maxY = (allValues.maxOrNull() ?: 100.0).coerceAtLeast(60.0)
                    for (g in 0..4) {
                        val y = size.height * g / 4f
                        drawLine(Color(0xFFE7ECE8), Offset(0f, y), Offset(size.width, y), strokeWidth = 1f)
                    }
                    candidates.forEach { c ->
                        val path = Path()
                        shown.forEachIndexed { i, point ->
                            val v = point.probabilities[c.id] ?: return@forEachIndexed
                            val x = if (shown.size == 1) 0f else size.width * i / (shown.size - 1f)
                            val y = size.height - (((v - minY) / (maxY - minY).coerceAtLeast(1.0)) * size.height).toFloat()
                            if (path.isEmpty) path.moveTo(x, y) else path.lineTo(x, y)
                        }
                        drawPath(path, candidateColor(c.id), style = Stroke(width = 5f, cap = StrokeCap.Round))
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
                    Text(c.name, color = TextDark)
                    val color = if (c.change > .049) Positive else if (c.change < -.049) Negative else Muted
                    Text(deltaText(c.change), color = color, fontWeight = FontWeight.Bold)
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
            Text("Como ler este número", fontWeight = FontWeight.ExtraBold, fontSize = 18.sp)
            Text("O modelo transforma a média de intenção de voto em um sinal probabilístico e combina esse sinal com preços de mercados de previsão. Fontes indisponíveis são retiradas do cálculo, e o resultado é renormalizado.", color = TextDark, lineHeight = 20.sp)
            Text("Confiança: ${snapshot.confidence}", color = BrazilBlue, fontWeight = FontWeight.Bold)
            HorizontalDivider(color = Color(0xFFE8DDBD))
            Text(snapshot.note, color = Muted, fontSize = 12.sp, lineHeight = 17.sp)
        }
    }
}

@Composable
private fun LoadingBlock() {
    Card(shape = RoundedCornerShape(22.dp), colors = CardDefaults.cardColors(containerColor = Color.White)) {
        Row(Modifier.fillMaxWidth().padding(24.dp), verticalAlignment = Alignment.CenterVertically) {
            CircularProgressIndicator(Modifier.size(28.dp), strokeWidth = 3.dp)
            Spacer(Modifier.width(14.dp))
            Text("Carregando o retrato eleitoral mais recente…", color = Muted)
        }
    }
}

private fun candidateColor(id: String): Color = when (id) {
    "lula" -> Color(0xFFC43A3A)
    "flavio-bolsonaro" -> Color(0xFF2867B2)
    "augusto-cury" -> Color(0xFF7B5BB5)
    "renan-santos" -> Color(0xFF2A8B76)
    "ronaldo-caiado" -> Color(0xFFB2761B)
    "romeu-zema" -> Color(0xFF4C6678)
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
private fun formatDay(instant: Instant): String =
    DateTimeFormatter.ofPattern("dd/MM").withZone(ZoneId.of("America/Sao_Paulo")).format(instant)
private fun formatElectionDate(raw: String): String = runCatching {
    LocalDate.parse(raw).format(DateTimeFormatter.ofPattern("dd/MM/yyyy"))
}.getOrElse { raw }
