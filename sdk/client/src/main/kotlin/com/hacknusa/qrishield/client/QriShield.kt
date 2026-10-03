package com.hacknusa.qrishield.client

import com.hacknusa.qrishield.core.*
import kotlinx.coroutines.*
import kotlinx.serialization.json.*
import java.net.HttpURLConnection
import java.net.URI
import java.security.MessageDigest
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

interface QriShieldRepository {
    suspend fun findContext(request: ContextMatchRequest): ContextMatchReport
    suspend fun assess(request: AssessmentRequest): AssessmentReport
}
fun interface TokenProvider { fun token(): String? }
data class ClientConfiguration(val baseUrl: String?, val tokenProvider: TokenProvider = TokenProvider { null }) {
    init {
        baseUrl?.let {
            val uri = URI(it)
            require(uri.scheme == "https" || (uri.scheme == "http" && uri.host in listOf("127.0.0.1", "localhost", "::1")))
            require(uri.userInfo == null && uri.query == null && uri.fragment == null)
        }
    }
    override fun toString() = "ClientConfiguration(configured=${baseUrl != null})"
}
data class HttpAnswer(val status: Int, val body: String)
fun interface JsonTransport { suspend fun post(url: String, token: String, body: String, timeoutMs: Int): HttpAnswer }
class UrlConnectionTransport : JsonTransport {
    override suspend fun post(url: String, token: String, body: String, timeoutMs: Int): HttpAnswer = suspendCancellableCoroutine { continuation ->
        val connection = URI(url).toURL().openConnection() as HttpURLConnection
        continuation.invokeOnCancellation { connection.disconnect() }
        Dispatchers.IO.dispatch(continuation.context, Runnable {
            try {
                connection.connectTimeout = timeoutMs; connection.readTimeout = timeoutMs
                connection.instanceFollowRedirects = false; connection.requestMethod = "POST"
                connection.doOutput = true; connection.setRequestProperty("Authorization", "Bearer $token")
                connection.setRequestProperty("Content-Type", "application/json")
                val bytes = body.toByteArray(Charsets.UTF_8); connection.setFixedLengthStreamingMode(bytes.size)
                connection.outputStream.use { it.write(bytes) }
                val code = connection.responseCode
                val data = (if (code in 200..299) connection.inputStream else connection.errorStream)?.use { stream ->
                    val output = java.io.ByteArrayOutputStream(); val buffer = ByteArray(4096)
                    while (true) { val n = stream.read(buffer); if (n < 0) break; require(output.size() + n <= 524288); output.write(buffer, 0, n) }
                    output.toString("UTF-8")
                } ?: "{}"
                if (continuation.isActive) continuation.resume(HttpAnswer(code, data))
            } catch (error: Exception) { if (continuation.isActive) continuation.resumeWithException(error) }
            finally { connection.disconnect() }
        })
    }
}

/** Canonical UTF-8 JSON matches the local Python service's sorted-key encoding. */
object Wire {
    fun canonical(value: JsonElement): String = when (value) {
        is JsonObject -> value.toSortedMap().entries.joinToString(",", "{", "}") { JsonPrimitive(it.key).toString() + ":" + canonical(it.value) }
        is JsonArray -> value.joinToString(",", "[", "]") { canonical(it) }
        else -> value.toString()
    }
    fun digest(value: JsonElement) = MessageDigest.getInstance("SHA-256").digest(canonical(value).toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }
    fun provenance(p: Provenance) = buildJsonObject {
        put("basis", p.basis.name.lowercase()); put("candidate_id", p.candidateId?.let(::JsonPrimitive) ?: JsonNull)
        put("source_timestamp_ms", p.sourceTimestampMs?.let(::JsonPrimitive) ?: JsonNull)
        put("same_conversation", p.sameConversation?.let(::JsonPrimitive) ?: JsonNull)
        put("message_media_delta_ms", p.messageMediaDeltaMs?.let(::JsonPrimitive) ?: JsonNull)
        put("notification_derived", p.notificationDerived)
    }
}
class QriShieldClient(
    private val configuration: ClientConfiguration,
    private val transport: JsonTransport = UrlConnectionTransport(),
    private val clock: () -> Long = System::currentTimeMillis
) : QriShieldRepository {
    private val json = Json { isLenient = false; allowSpecialFloatingPointValues = false }
    private fun envelope(id: String, snapshot: String, deadline: Long, permission: String) = buildJsonObject {
        put("schema_version", "1.0"); put("request_id", id); put("profile", "qris_artifact_context")
        put("snapshot_digest", snapshot); put("deadline_unix_ms", deadline)
        put("processing_permissions", buildJsonObject { put(permission, true) })
    }
    private suspend fun call(path: String, request: JsonObject, deadline: Long): JsonObject {
        val url = configuration.baseUrl ?: throw Unavailable("not_configured")
        val token = configuration.tokenProvider.token()?.takeIf { it.length >= 32 && it.all { c -> c.code in 33..126 } } ?: throw Unavailable("authentication_unavailable")
        val remaining = deadline - clock(); if (remaining <= 0) throw Unavailable("deadline_exceeded")
        if (remaining > 30_000) throw Unavailable("invalid_deadline")
        val body = Wire.canonical(request); val limit = if (path.endsWith("context-match")) 524288 else 32768
        if (body.toByteArray(Charsets.UTF_8).size > limit) throw Unavailable("body_too_large")
        val answer = withTimeout(remaining) { transport.post(url.trimEnd('/') + path, token, body, remaining.toInt()) }
        currentCoroutineContext().ensureActive()
        if (clock() >= deadline) throw Unavailable("deadline_exceeded")
        if (answer.body.toByteArray(Charsets.UTF_8).size > 524288) throw Unavailable("response_too_large")
        val result = json.parseToJsonElement(answer.body).jsonObject
        if (answer.status !in 200..299) throw Unavailable(result["unavailable_reason"]?.jsonPrimitive?.contentOrNull ?: when(answer.status) { 401 -> "unauthorized"; 408 -> "deadline_exceeded"; 503 -> "service_unavailable"; else -> "http_${answer.status}" })
        for (key in listOf("schema_version", "request_id", "profile", "snapshot_digest")) require(result[key] == request[key]) { "response_correlation" }
        return result
    }
    override suspend fun findContext(request: ContextMatchRequest): ContextMatchReport {
        val frozen = request.frozen(); val facts = frozen.qr.facts
        val snapshot = Wire.digest(buildJsonObject {
            put("qr", frozen.qr.payload); put("permission", frozen.permissions.matching)
            put("candidates", JsonArray(frozen.candidates.map { buildJsonObject { put("id", it.id); put("text", it.text); put("provenance", Wire.provenance(it.provenance)) } }))
        })
        fun unavailable(reason: String, skipped: List<SkippedCandidate> = emptyList()) = ContextMatchReport(frozen.requestId, snapshot, skipped = skipped, reason = reason)
        if (!frozen.permissions.matching) return unavailable("permission_denied")
        if (facts.usableMerchant() == null) return unavailable("unusable_qr")
        if (frozen.candidates.size > 20 || frozen.candidates.map { it.id }.toSet().size != frozen.candidates.size || frozen.candidates.any { !Regex("[A-Za-z0-9_.-]{1,128}").matches(it.id) }) return unavailable("invalid_candidates")
        val skipped = frozen.candidates.filter { it.condition != TextCondition.OBSERVED }.map { SkippedCandidate(it.id, it.condition.name.lowercase()) }
        val candidates = frozen.candidates.filter { it.condition == TextCondition.OBSERVED }
        if (candidates.isEmpty()) return unavailable("no_candidates", skipped)
        val qr = buildJsonObject { put("merchant", facts.usableMerchant()); put("city", facts.merchant.city?.let(::JsonPrimitive) ?: JsonNull); put("amount_minor", facts.transaction.amountMinor?.let(::JsonPrimitive) ?: JsonNull) }
        val entries = JsonArray(candidates.map { buildJsonObject { put("candidate_id", it.id); put("text", it.text) } })
        val wire = JsonObject(envelope(frozen.requestId, snapshot, frozen.deadlineUnixMs, "matching_local") + mapOf("qr" to qr, "candidates" to entries))
        try {
            val result = call("/v1/context-match", wire, frozen.deadlineUnixMs)
            require(result["input_digest"]?.jsonPrimitive?.content == Wire.digest(buildJsonObject { put("qr", qr); put("candidates", entries) }))
            require(result["status"]?.jsonPrimitive?.content == "experimental")
            val fingerprint = result["matcher_fingerprint"]!!.jsonPrimitive.content; require(Regex("[0-9a-f]{64}").matches(fingerprint))
            val byId = candidates.associateBy { it.id }
            val suggestions = result["suggestions"]!!.jsonArray.map { element ->
                val value = element.jsonObject; val score = value["cosine"]!!.jsonPrimitive.double
                require(score.isFinite() && score in -1.000001..1.000001)
                ContextSuggestion(byId[value["candidate_id"]!!.jsonPrimitive.content] ?: error("unknown_candidate"), score)
            }
            val remoteSkipped = result["skipped"]!!.jsonArray.map { e -> val v = e.jsonObject; val id = v["candidate_id"]!!.jsonPrimitive.content; require(id in byId); SkippedCandidate(id, v["reason"]!!.jsonPrimitive.content) }
            require(suggestions.size <= 3 && suggestions.map { it.candidate.id }.distinct().size == suggestions.size)
            require(remoteSkipped.map { it.candidateId }.distinct().size == remoteSkipped.size && remoteSkipped.none { s -> suggestions.any { it.candidate.id == s.candidateId } })
            require(suggestions.zipWithNext().all { (a,b) -> a.cosine >= b.cosine && (a.cosine != b.cosine || candidates.indexOf(a.candidate) < candidates.indexOf(b.candidate)) })
            return ContextMatchReport(frozen.requestId, snapshot, suggestions, skipped + remoteSkipped, "experimental", matcherFingerprint = fingerprint)
        } catch (error: TimeoutCancellationException) { currentCoroutineContext().ensureActive(); return unavailable("deadline_exceeded", skipped) }
        catch (error: CancellationException) { throw error }
        catch (error: Exception) { return unavailable((error as? Unavailable)?.reason ?: "invalid_response_or_transport", skipped) }
    }
    override suspend fun assess(request: AssessmentRequest): AssessmentReport {
        val facts = request.qr.facts
        val snapshot = Wire.digest(buildJsonObject { put("qr", request.qr.payload); put("text", request.context.text?.let(::JsonPrimitive) ?: JsonNull); put("observed", request.context.observedText?.let(::JsonPrimitive) ?: JsonNull); put("provenance", Wire.provenance(request.context.provenance)); put("permission", request.permissions.semantic) })
        fun report(reason: String? = null, semantic: SemanticResult? = null): AssessmentReport {
            val now = clock()
            return AssessmentReport(request.requestId, snapshot, facts, request.context, CheckCoverage(intent = semantic != null, recipientRelation = semantic != null), semantic, reason, now)
        }
        if (facts.usableMerchant() == null) return report("unusable_qr")
        if (!request.permissions.semantic) return report("permission_denied")
        if (textCondition(request.context.text) != TextCondition.OBSERVED) return report("context_${textCondition(request.context.text).name.lowercase()}")
        val state = buildJsonObject { put("message", request.context.text); put("payment", buildJsonObject { put("merchant", facts.usableMerchant()); put("amount_minor", facts.transaction.amountMinor?.let(::JsonPrimitive) ?: JsonNull) }) }
        val wire = JsonObject(envelope(request.requestId, snapshot, request.deadlineUnixMs, "semantic_remote") + ("state" to state))
        try {
            val result = call("/v1/semantic", wire, request.deadlineUnixMs)
            require(result["state_digest"]!!.jsonPrimitive.content == Wire.digest(state))
            require(result["status"]!!.jsonPrimitive.content == "experimental")
            val release = result["release"]!!.jsonObject
            val fingerprint = release["fingerprint"]!!.jsonPrimitive.content; require(Regex("[0-9a-f]{64}").matches(fingerprint))
            val native = result["native"]!!.jsonObject
            require(native.keys == setOf("schema_version", "model_id", "usage", "intent", "recipient_relation"))
            require(native["schema_version"]?.jsonPrimitive?.content == "1.0" && native["model_id"] == release["model_id"])
            val usage = native["usage"]!!.jsonObject
            val usageFields = setOf("input_tokens", "output_tokens", "state_tokens", "state_tokens_dropped", "truncated", "truncated_questions")
            require(usage.keys.containsAll(usageFields) && (usage.keys - usageFields - "options").isEmpty())
            for (field in listOf("input_tokens", "output_tokens", "state_tokens", "state_tokens_dropped")) require(usage[field]!!.jsonPrimitive.long >= 0)
            require(usage["truncated"]?.jsonPrimitive?.boolean == false && usage["state_tokens_dropped"]?.jsonPrimitive?.int == 0 && usage["output_tokens"]?.jsonPrimitive?.int == 0 && usage["truncated_questions"]!!.jsonArray.isEmpty() && (usage["options"] == null || usage["options"]!!.jsonObject.isEmpty()))
            fun task(name: String, labels: Set<String>): TaskResult {
                val readiness = release["task_readiness"]!!.jsonObject[name]!!.jsonObject
                require(readiness["inference_ready"]?.jsonPrimitive?.boolean == true && readiness["policy_approved"]?.jsonPrimitive?.boolean == false)
                val v = native[name]!!.jsonObject; require(v.keys == setOf("label", "confidence", "probabilities")); val label = v["label"]!!.jsonPrimitive.content
                val p = v["probabilities"]!!.jsonObject.mapValues { it.value.jsonPrimitive.double }; val confidence = v["confidence"]!!.jsonPrimitive.double
                require(p.keys == labels && label in labels && p.values.all { it.isFinite() && it in 0.0..1.0 } && confidence.isFinite() && confidence in 0.0..1.0 && kotlin.math.abs(p.values.sum() - 1) <= .001 && kotlin.math.abs(confidence - p.getValue(label)) <= .0001)
                return TaskResult(label, confidence, p.toMap())
            }
            return report(semantic = SemanticResult(task("intent", setOf("PAYMENT_REQUEST", "PAST_PAYMENT", "PAYMENT_PROHIBITION", "NON_PAYMENT", "AMBIGUOUS")), task("recipient_relation", setOf("CONSISTENT", "INCONSISTENT", "INSUFFICIENT_EVIDENCE")), fingerprint))
        } catch (error: TimeoutCancellationException) { currentCoroutineContext().ensureActive(); return report("deadline_exceeded") }
        catch (error: CancellationException) { throw error }
        catch (error: Exception) { return report((error as? Unavailable)?.reason ?: "invalid_response_or_transport") }
    }
    private class Unavailable(val reason: String) : Exception(reason)
}
