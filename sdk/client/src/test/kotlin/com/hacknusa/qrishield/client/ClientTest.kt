package com.hacknusa.qrishield.client
import com.hacknusa.qrishield.core.*
import kotlinx.coroutines.*
import kotlinx.serialization.json.*
import org.junit.Test
import org.junit.Assert.*
class ClientTest {
    private val valid = "00020101021251280014ID.CO.QRIS.WWW0206TEST0152045812530336054063500005802ID5913TEST MERCHANT6007JAKARTA63046D26"
    private val config = ClientConfiguration("http://127.0.0.1:8765", TokenProvider { "x".repeat(32) })
    private fun request(text: String? = "Bayar ke TEST MERCHANT") = AssessmentRequest(QrObservation(valid), ReviewedContext(text, text), ProcessingPermissions(semantic=true), System.currentTimeMillis()+30000)
    @Test fun deniedOversizedInvalidQrAndMissingContextMakeZeroRequests() = runBlocking {
        var calls = 0; val client = QriShieldClient(config, JsonTransport { _,_,_,_ -> calls++; error("unexpected") })
        for (r in listOf(request().copy(permissions=ProcessingPermissions()), request("x".repeat(4097)), request(null), request().copy(qr=QrObservation("broken")))) {
            val report = client.assess(r); assertNull(report.semantic); assertNotNull(report.unavailableReason)
        }
        assertEquals(0,calls)
        assertEquals("permission_denied", client.findContext(ContextMatchRequest(QrObservation(valid),emptyList(),ProcessingPermissions(),System.currentTimeMillis()+30000)).reason)
    }
    @Test fun nativePayloadContainsOnlyReviewedMessageAndQrWholeRupiahOrNull() = runBlocking {
        var state: JsonObject? = null
        val client = QriShieldClient(config, JsonTransport { _,_,body,_ -> state = Json.parseToJsonElement(body).jsonObject["state"]!!.jsonObject; HttpAnswer(503,"{}") })
        client.assess(request()); assertEquals(setOf("message","payment"),state!!.keys)
        assertEquals(350000L,state!!["payment"]!!.jsonObject["amount_minor"]!!.jsonPrimitive.long)
        val noAmount = valid.replace("5406350000","").dropLast(4)+"65D0"
        client.assess(request().copy(qr=QrObservation(noAmount)))
        assertEquals(JsonNull, state!!["payment"]!!.jsonObject["amount_minor"])
    }
    @Test fun transportFailureKeepsDeterministicFacts() = runBlocking {
        val result = QriShieldClient(config, JsonTransport { _,_,_,_ -> throw java.io.IOException() }).assess(request())
        assertEquals(ParseStatus.SUCCESS,result.facts.parseStatus); assertEquals(350000L,result.facts.transaction.amountMinor)
        assertTrue(result.coverage.parser); assertFalse(result.coverage.intent); assertTrue(result.validAt(result.createdAtMs+119999)); assertFalse(result.validAt(result.createdAtMs+120000))
    }
    @Test fun wrongResponseCorrelationCannotProduceSemanticCoverage() = runBlocking {
        val result = QriShieldClient(config, JsonTransport { _,_,_,_ -> HttpAnswer(200,"{\"schema_version\":\"1.0\",\"request_id\":\"other\"}") }).assess(request())
        assertNull(result.semantic); assertEquals("invalid_response_or_transport",result.unavailableReason)
    }
    @Test fun matchingPreservesOpaqueIdsStableTiesAndSnapshotIsolation() = runBlocking {
        val candidates = mutableListOf(ContextCandidate("first","one"),ContextCandidate("second","two"),ContextCandidate("oversized","x".repeat(4097)))
        val client = QriShieldClient(config,JsonTransport { _,_,body,_ ->
            val wire=Json.parseToJsonElement(body).jsonObject
            candidates.clear()
            val response=JsonObject(wire.filterKeys { it in listOf("schema_version","request_id","profile","snapshot_digest") } + mapOf(
                "status" to JsonPrimitive("experimental"),"matcher_fingerprint" to JsonPrimitive("a".repeat(64)),
                "input_digest" to JsonPrimitive(Wire.digest(buildJsonObject { put("qr",wire["qr"]!!);put("candidates",wire["candidates"]!!) })),
                "suggestions" to Json.parseToJsonElement("[{\"candidate_id\":\"first\",\"cosine\":0.9},{\"candidate_id\":\"second\",\"cosine\":0.9}]"),"skipped" to JsonArray(emptyList())))
            HttpAnswer(200,response.toString())
        })
        val result=client.findContext(ContextMatchRequest(QrObservation(valid),candidates,ProcessingPermissions(matching=true),System.currentTimeMillis()+30000))
        assertEquals(listOf("first","second"),result.suggestions.map { it.candidate.id }); assertEquals("oversized",result.skipped.single().candidateId)
    }
    @Test fun cancellationPropagatesAndOwnedTimeoutRetainsLocalFacts() = runBlocking {
        val client=QriShieldClient(config,JsonTransport { _,_,_,_ -> delay(5000);error("late") })
        val work=async { client.assess(request()) }; delay(20);work.cancelAndJoin();assertTrue(work.isCancelled)
        val result=client.assess(request().copy(deadlineUnixMs=System.currentTimeMillis()+30))
        assertEquals("deadline_exceeded",result.unavailableReason);assertEquals(ParseStatus.SUCCESS,result.facts.parseStatus)
        try { withTimeout(20) { client.assess(request()) };fail() } catch (_: TimeoutCancellationException) { }
    }
    @Test fun validatedNativeOutputProducesCoverageButMalformedUsageCannot() = runBlocking {
        var negativeUsage = false
        val client = QriShieldClient(config, JsonTransport { _,_,body,_ ->
            val wire = Json.parseToJsonElement(body).jsonObject
            fun task(labels: List<String>) = buildJsonObject {
                put("label", labels.first()); put("confidence", 1.0)
                put("probabilities", buildJsonObject { labels.forEachIndexed { i,label -> put(label, if (i == 0) 1.0 else 0.0) } })
            }
            val native = buildJsonObject {
                put("schema_version", "1.0"); put("model_id", "synthetic")
                put("intent", task(listOf("PAYMENT_REQUEST","PAST_PAYMENT","PAYMENT_PROHIBITION","NON_PAYMENT","AMBIGUOUS")))
                put("recipient_relation", task(listOf("CONSISTENT","INCONSISTENT","INSUFFICIENT_EVIDENCE")))
                put("usage", buildJsonObject { put("input_tokens", if (negativeUsage) -1 else 30); put("output_tokens",0);put("state_tokens",20);put("state_tokens_dropped",0);put("truncated",false);put("truncated_questions",JsonArray(emptyList())) })
            }
            val release = buildJsonObject {
                put("model_id","synthetic");put("fingerprint","a".repeat(64))
                put("task_readiness",buildJsonObject { for (name in listOf("intent","recipient_relation")) put(name,buildJsonObject { put("inference_ready",true);put("policy_approved",false) }) })
            }
            HttpAnswer(200, JsonObject(wire.filterKeys { it in listOf("schema_version","request_id","profile","snapshot_digest") } + mapOf("state_digest" to JsonPrimitive(Wire.digest(wire["state"]!!)),"release" to release,"status" to JsonPrimitive("experimental"),"native" to native)).toString())
        })
        val report = client.assess(request())
        assertNotNull(report.semantic);assertTrue(report.coverage.intent && report.coverage.recipientRelation)
        assertEquals("CONSISTENT",report.semantic!!.recipientRelation.label)
        negativeUsage = true
        val invalid = client.assess(request());assertNull(invalid.semantic);assertFalse(invalid.coverage.intent);assertEquals(ParseStatus.SUCCESS,invalid.facts.parseStatus)
    }
    @Test fun canonicalDigestAgreesWithPythonUnicodeAndEscapes() {
        val state=buildJsonObject { put("message","bayar 😀\n\"\\");put("payment",buildJsonObject {put("merchant","BUDI");put("amount_minor",JsonNull)}) }
        assertEquals("45a919ba7d9522ee732001e531cf6de0816df426d4db3e0b5bcb905294b5440e",Wire.digest(state))
    }
}
