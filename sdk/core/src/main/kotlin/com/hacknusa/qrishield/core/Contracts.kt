package com.hacknusa.qrishield.core

/** UTF-16 is the JVM/Android editor unit; no implicit shortening at any boundary. */
enum class TextCondition { ABSENT, OBSERVED, OVERSIZED, INVALID_UNICODE }
fun textCondition(text: String?): TextCondition = when {
    text.isNullOrBlank() -> TextCondition.ABSENT
    text.length > 4096 -> TextCondition.OVERSIZED
    else -> {
        var i = 0
        var valid = true
        while (i < text.length) {
            val c = text[i++]
            if (c.isHighSurrogate()) { if (i >= text.length || !text[i++].isLowSurrogate()) valid = false }
            else if (c.isLowSurrogate()) valid = false
        }
        if (valid) TextCondition.OBSERVED else TextCondition.INVALID_UNICODE
    }
}
enum class ContextBasis { NONE, SAME_MESSAGE_OBJECT, USER_SELECTED, USER_ENTERED }
data class Provenance(
    val basis: ContextBasis = ContextBasis.NONE,
    val candidateId: String? = null,
    val sourceTimestampMs: Long? = null,
    val sameConversation: Boolean? = null,
    val messageMediaDeltaMs: Long? = null,
    val notificationDerived: Boolean = false
)
/** Opaque ID only; sender, notification key and conversation mapping stay in the host. */
data class ContextCandidate(val id: String, val text: String, val provenance: Provenance = Provenance()) {
    val condition get() = textCondition(text)
    override fun toString() = "ContextCandidate(id=$id, condition=$condition)"
}
data class ReviewedContext(val observedText: String?, val text: String?, val provenance: Provenance = Provenance()) {
    override fun toString() = "ReviewedContext(condition=${textCondition(text)}, basis=${provenance.basis})"
}
data class ProcessingPermissions(val matching: Boolean = false, val semantic: Boolean = false)
data class QrObservation(val payload: String) {
    val facts get() = QrisParser.parse(payload)
    override fun toString() = "QrObservation(redacted)"
}
data class ContextMatchRequest(
    val qr: QrObservation, val candidates: List<ContextCandidate>,
    val permissions: ProcessingPermissions, val deadlineUnixMs: Long,
    val requestId: String = java.util.UUID.randomUUID().toString()
) {
    fun frozen() = copy(candidates = candidates.toList())
}
data class AssessmentRequest(
    val qr: QrObservation, val context: ReviewedContext,
    val permissions: ProcessingPermissions, val deadlineUnixMs: Long,
    val requestId: String = java.util.UUID.randomUUID().toString()
)
data class ContextSuggestion(val candidate: ContextCandidate, val cosine: Double)
data class SkippedCandidate(val candidateId: String, val reason: String)
data class ContextMatchReport(
    val requestId: String, val snapshotDigest: String,
    val suggestions: List<ContextSuggestion> = emptyList(),
    val skipped: List<SkippedCandidate> = emptyList(),
    val status: String = "unavailable", val reason: String? = null,
    val matcherFingerprint: String? = null
)
data class TaskResult(val label: String, val probability: Double, val probabilities: Map<String, Double>)
data class SemanticResult(val intent: TaskResult, val recipientRelation: TaskResult, val releaseFingerprint: String)
data class CheckCoverage(val parser: Boolean = true, val intent: Boolean = false, val recipientRelation: Boolean = false)
data class AssessmentReport(
    val requestId: String, val snapshotDigest: String, val facts: ParsedQris,
    val context: ReviewedContext, val coverage: CheckCoverage,
    val semantic: SemanticResult? = null, val unavailableReason: String? = null,
    val createdAtMs: Long, val expiresAtMs: Long = createdAtMs + 120_000
) {
    fun validAt(nowMs: Long) = nowMs >= createdAtMs && nowMs < expiresAtMs
    override fun toString() = "AssessmentReport(requestId=$requestId, status=${facts.parseStatus}, semantic=${semantic != null})"
}
fun ParsedQris.usableMerchant(): String? = merchant.name?.takeIf { parseStatus == ParseStatus.SUCCESS && integrity.crcValid == true && it.isNotBlank() }
