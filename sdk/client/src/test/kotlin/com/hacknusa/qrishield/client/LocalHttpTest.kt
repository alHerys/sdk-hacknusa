package com.hacknusa.qrishield.client
import com.hacknusa.qrishield.core.*
import kotlinx.coroutines.runBlocking
import org.junit.Test
import org.junit.Assert.*
import java.io.File

/** Explicit opt-in task against the real local models, synthetic content only. */
class LocalHttpTest {
    private val valid = "00020101021251280014ID.CO.QRIS.WWW0206TEST0152045812530336054063500005802ID5913TEST MERCHANT6007JAKARTA63046D26"
    @Test fun matcherAndNativeLayaThroughJvmHttp() = runBlocking {
        val token = File(System.getProperty("qrishield.serviceDir"), ".env").readText().trim().substringAfter("QRISHIELD_API_TOKEN=")
        val client = QriShieldClient(ClientConfiguration("http://127.0.0.1:8765", TokenProvider { token }))
        val qr = QrObservation(valid)
        val candidates = listOf(ContextCandidate("relevant", "Bayar pesanan ke TEST MERCHANT pakai QRIS ya"), ContextCandidate("unrelated", "Besok rapat jam 9"), ContextCandidate("overflow", "x ".repeat(2000)))
        val match = client.findContext(ContextMatchRequest(qr,candidates,ProcessingPermissions(matching=true),System.currentTimeMillis()+30000))
        assertEquals("experimental",match.status); assertEquals("relevant",match.suggestions.first().candidate.id)
        assertEquals("token_overflow",match.skipped.single().reason)
        val text=match.suggestions.first().candidate.text
        val report=client.assess(AssessmentRequest(qr,ReviewedContext(text,text,Provenance(basis=ContextBasis.USER_SELECTED,candidateId="relevant")),ProcessingPermissions(semantic=true),System.currentTimeMillis()+30000))
        assertNull(report.unavailableReason);assertNotNull(report.semantic)
        assertTrue(report.coverage.intent && report.coverage.recipientRelation);assertEquals(350000L,report.facts.transaction.amountMinor)
        assertTrue(report.validAt(System.currentTimeMillis()));assertEquals(64,report.semantic!!.releaseFingerprint.length)
        val unauthorized=QriShieldClient(ClientConfiguration("http://127.0.0.1:8765",TokenProvider { "incorrect-"+"x".repeat(32) })).assess(AssessmentRequest(qr,ReviewedContext(text,text),ProcessingPermissions(semantic=true),System.currentTimeMillis()+30000))
        assertEquals("unauthorized",unauthorized.unavailableReason);assertEquals(ParseStatus.SUCCESS,unauthorized.facts.parseStatus)
    }
}
