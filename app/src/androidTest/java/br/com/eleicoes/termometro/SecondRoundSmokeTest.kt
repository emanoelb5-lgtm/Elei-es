package br.com.eleicoes.termometro

import android.content.Context
import android.os.ParcelFileDescriptor
import androidx.test.platform.app.InstrumentationRegistry
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.*
import org.junit.runner.RunWith
import java.io.File
import java.io.IOException
import java.util.UUID

@RunWith(AndroidJUnit4::class)
class SecondRoundSmokeTest {
    @get:Rule val compose = createComposeRule()
    private val context get() = ApplicationProvider.getApplicationContext<Context>()
    private fun repository(download: (String) -> String = { throw IOException("offline") }) =
        SecondRoundRepository(context, download, "test-" + UUID.randomUUID() + ".json")

    private fun screenshot(name: String) {
        // Capturas em pasta do shell sobrevivem à limpeza do pacote pelo UTP.
        val shell = InstrumentationRegistry.getInstrumentation().uiAutomation
        fun command(text: String) {
            ParcelFileDescriptor.AutoCloseInputStream(shell.executeShellCommand(text)).use { it.readBytes() }
        }
        command("mkdir -p /sdcard/Download/termometro-qa")
        command("screencap -p /sdcard/Download/termometro-qa/" + name + ".png")
    }

    @Test fun firstOpeningWorksOfflineAndTabsRemainUsable() {
        val repo = repository()
        compose.setContent { SegundoTurnoApp(repo) }
        compose.waitUntil(15_000) { compose.onAllNodesWithText("Atualizar pesquisas").fetchSemanticsNodes().isNotEmpty() }
        screenshot("home")
        compose.onNode(hasScrollToIndexAction()).performScrollToNode(hasText("Ver pesquisas"))
        screenshot("diagnostico")
        compose.onNodeWithText("Ver pesquisas").performClick()
        compose.onNodeWithText("Buscar instituto ou registro").performTextInput("Ipespe")
        compose.onNodeWithText("Ipespe/Abrapel").assertExists()
        screenshot("pesquisas")
        compose.onNodeWithText("Evolução").performClick()
        compose.onNodeWithText("Apoio em válidos").assertExists()
        screenshot("evolucao")
        compose.onNodeWithText("Chance no modelo").performClick()
        compose.onNodeWithText("Estimativa exploratória (%)").assertExists()
        compose.onNodeWithText("Pesquisas").performClick()
        compose.onNodeWithText("Ipespe/Abrapel").assertExists()
        compose.onNodeWithText("Fontes").performClick()
        compose.onNodeWithText("FONTES E MÉTODO").assertExists()
        screenshot("fontes")
    }

    @Test fun sameEvidenceReportsNoNewPoll() {
        val raw = context.assets.open("runoff-2026.json").bufferedReader().use { it.readText() }
        val repo = repository { raw }
        compose.setContent { SegundoTurnoApp(repo) }
        compose.waitUntil(15_000) { compose.onAllNodesWithText("Atualizar pesquisas").fetchSemanticsNodes().isNotEmpty() }
        compose.onNodeWithText("Atualizar pesquisas").performScrollTo().performClick()
        compose.waitUntil(15_000) {
            compose.onAllNodesWithText("Nenhuma pesquisa nova. Consulta concluída.").fetchSemanticsNodes().isNotEmpty()
        }
        compose.onNodeWithText("Nenhuma pesquisa nova. Consulta concluída.").assertExists()
    }

    @Test fun corruptLegacyCacheAndMalformedNetworkCannotEraseBundledReading() {
        val name = "test-corrupt-" + UUID.randomUUID() + ".json"
        val file = File(context.filesDir, name)
        file.writeText("{\"schemaVersion\":1}")
        try {
            val repo = SecondRoundRepository(context, { "{\"schemaVersion\":2}" }, name)
            val before = repo.initial()
            Assert.assertEquals("bundled", before.origin)
            Assert.assertTrue(runCatching { repo.fetch(before.reading) }.isFailure)
            Assert.assertEquals(before.reading.revision, repo.initial().reading.revision)
        } finally { file.delete() }
    }
}
