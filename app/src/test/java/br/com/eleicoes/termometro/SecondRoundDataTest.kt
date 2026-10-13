package br.com.eleicoes.termometro

import org.junit.Assert.*
import org.junit.Test
import org.json.JSONObject
import java.io.File
import java.time.LocalDate

class SecondRoundDataTest {
    private fun raw() = javaClass.classLoader!!.getResource("runoff-fixture.json")!!.readText()
    private fun parse(text: String = raw()) = parseRoundReading(text, LocalDate.of(2026, 10, 12))

    @Test fun bundledReadingContainsExclusiveRunoffAndPreinstallHistory() {
        val reading = parse()
        assertEquals(RoundIds, reading.candidates.map { it.id }.toSet())
        assertEquals(3, reading.polls.size)
        assertEquals(2, reading.history.size)
        assertNotNull(reading.model)
        assertEquals(100.0, reading.model!!.probability.values.sum(), .001)
        assertEquals(100.0, reading.model.support.values.sum(), .001)
    }
    @Test fun checkingAgainDoesNotClaimNewPoll() {
        val before = parse()
        val fresh = before.copy(checkedAt = "2026-10-13T01:00:00Z")
        assertEquals("Nenhuma pesquisa nova. Consulta concluída.", roundRefreshFeedback(before, fresh))
    }
    @Test fun duplicatePollIdAndOldFieldworkAreRejected() {
        val obj = JSONObject(raw())
        val polls = obj.getJSONArray("polls")
        polls.put(polls.getJSONObject(0))
        obj.put("pollCount", polls.length())
        assertTrue(runCatching { parse(obj.toString()) }.isFailure)
        val old = JSONObject(raw())
        old.getJSONArray("polls").getJSONObject(0).put("fieldworkStart", "2026-10-03")
        assertTrue(runCatching { parse(old.toString()) }.isFailure)
    }
    @Test fun corruptModelAndFuturePublicationAreRejected() {
        val obj = JSONObject(raw())
        obj.getJSONObject("model").getJSONObject("winProbability").put("lula", 140)
        assertTrue(runCatching { parse(obj.toString()) }.isFailure)
        val future = JSONObject(raw())
        future.getJSONArray("polls").getJSONObject(0).put("publishedAt", "2026-11-01")
        assertTrue(runCatching { parse(future.toString()) }.isFailure)
    }
}
