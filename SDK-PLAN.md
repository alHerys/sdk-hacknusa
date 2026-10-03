# QRIShield SDK — revision 6

Approved implementation, 3 October 2026. This replaces revision 5. Android
baseline: `69c10057647205f513e0ee9a94faa255126ffe40` in
`/Users/hery/AndroidStudioProjects/HackNusa`. Previous checkout test results do
not validate this baseline. Implementation and measured results are recorded in
[IMPLEMENTATION.md](IMPLEMENTATION.md).

Flow: **selected QR → WhatsApp context search → three suggestions or manual
input → user review → Laya assessment**. Matching is retrieval assistance.
Neither matcher nor Laya authenticates a message, merchant, fraud, or payment.

## Components and contracts

- `sdk/core`: Kotlin/JVM authoritative parser, observations, provenance, text
  validation, immutable request/report contracts. No Android permission, URI,
  bitmap or notification service dependencies.
- `sdk/client`: suspend `findContext(ContextMatchRequest)` and
  `assess(AssessmentRequest)`, configurable transport/token provider, local
  fallback, strict response correlation and digest checks.
- Android host: acquisition, permissions, short-lived buffers, decoding and
  preview, user review, consent, repository injection and session cancellation.
- `services/laya`: loopback Python service; E5 retrieval and existing native
  Laya run on one shared worker, maximum four outstanding requests.

`findContext` freezes selected QR, candidate list and provenance, matching
permission, deadline and client configuration. It returns up to three cosine
suggestions, structured skipped candidates, experimental/unavailable status,
snapshot digest and matcher fingerprint. IDs are opaque. Local notification
keys, sender metadata and conversation maps are not sent.

`assess` freezes QR, observed and reviewed context, provenance, semantic
permission, deadline and configuration. It always retains deterministic parser
facts. Coverage identifies unassessed intent/recipient relation. Invalid QR or
unusable merchant prevents dependent checks. Reports expire at two minutes,
and the host clears them on input changes, session closure or access revocation.

Parser extraction preserves six statuses, Merchant Channel, strict CRC and
nested duplicate rejection, nullable observations, and exact whole rupiah.
There is one parser implementation; Android uses compatibility type aliases.
`amount_minor` is whole rupiah (350000 means Rp350000); absent tag54 maps to
explicit null. Caption text never supplies the amount or merchant.

No silent text truncation: over 4096 UTF-16 units is oversized and never sent as
an undisclosed fragment. Invalid Unicode is rejected. A user shortening oversized
text creates user-entered context. Full text as observed does not mean full chat.
Observed and edited text are kept separately in session memory.

## Notification acquisition

Filter `com.whatsapp` before content; exclude group summaries. API 30+ uses
MessagingStyle callbacks plus one `getActiveNotifications()` snapshot after
connection. Initial snapshot populates candidates without old warnings. This is
active notification data, not deleted notifications or chat history. API 24–29
keeps share/gallery/camera/manual assessment but shows notification matching
unavailable. No Settings scraping, Accessibility or WhatsApp database access.

One acquisition worker, queue eight; at most twenty messages and four media
reads per callback. Media limits: 4 MiB, two seconds, four million decoded pixels,
twenty unique QR payloads. Same-image preview: side at most 1024 px, 256 KiB;
preview failure does not discard the decoded QR.

Text buffer: twenty entries, five minutes, memory only, all texts regardless of
QRIS keyword. Valid source timestamps reject old messages; replay does not renew
lifetime. Unknown timestamps remain unknown. Media buffer: four entries, two
minutes. Warning dedup is independent of evidence acquisition and late media
updates. Unambiguous message identity can update existing evidence without a
second warning; ambiguous identities never auto-merge.

Only standalone QRIS text triggers warnings. No callback invokes a service.
Reading access, warning posting, matching and semantic assessment are separate
permissions. Stop, expiry, revocation, disconnect and process death clear buffers.
Revocation cancels sessions using notification evidence. History is metadata only.
Text/media on the same object uses `same_message_object`; same container does
not establish a conversation. Conversation and delivery delta remain unknown.

## Embedding matcher PoC

Pinned default: `intfloat/multilingual-e5-small`, revision
`614241f622f53c4eeff9890bdc4f31cfecc418b3`. CPU PyTorch/Transformers, masked mean
pooling, L2 normalization, 384 dimensions, prefixes `query: ` / `passage: `.
No APK embedding, generative LLM, fine-tuning or vector database.

Deterministic query uses QR merchant, optional QR city and encoded amount only:
a QRIS payment request to that merchant. Candidate passages are checked before
inference. Over 512 tokens (including prefix/special tokens) is skipped with
`token_overflow`; no inference truncation. Encode batches of at most four.
Cosine is finite and sorted descending; exact ties preserve input order, which
is newest first. Maximum twenty candidates, top three, no correctness threshold.
Same-object text is directly observed context; matcher assists separate messages.

The model loads once from the local revision/checksum bundle. Fingerprint covers
weights/tokenizer, pooling/prefix/query template, runtime and inference config.
Smoke and a labeled synthetic benchmark are required before treating the PoC
embedding integration as verified. These tests do not establish payment safety.

`POST /v1/context-match`: schema `1.0`, request ID, profile
`qris_artifact_context`, snapshot digest, deadline, permission
`matching_local: true`, minimal QR `{merchant, city, amount_minor}`, and
`[{candidate_id, text}]`. Body maximum 512 KiB; deadline maximum 30 seconds.
Response echoes schema/request/profile/snapshot, hashes the QR/candidate payload
as `input_digest`, returns matcher fingerprint, suggestions `{candidate_id,
cosine}`, structured skips and status. Authentication is bearer token.

`POST /v1/semantic` remains unchanged: 32 KiB; `semantic_remote: true`; native
state only `{message, payment:{merchant, amount_minor}}`. No raw QR, images,
sender, notification keys or linkage enters Laya. Native task questions, label
sets and token budgets remain the supplied release's configuration.

One shared inference executor and four outstanding jobs cover both endpoints.
Timeout never releases a running native job's capacity. Expired queued jobs are
skipped when dequeued. Matcher failure does not disable manual-context Laya.

## Review and runtime

Scope update from the user: this chat owns `sdk-hacknusa` only and must not edit
`HackNusa`. The coordinated bank chat owns Android integration, manifests,
builds/device tests and the new Indonesian bank UI. Default bank remains
unconfigured/offline; explicit debug injection may consume this now-working SDK.
The English legacy review described below is the preserved debug integration
reference, not a request to replace the new bank interface.


English Compose review retains current design and automatic QR details/preview.
“Find related messages” discloses up to twenty texts processed by the local
service and asks matching permission. Three suggestions have no preselection,
plus “Type or paste context”, editable full context, and local-only checks.
A separate semantic dialog permits only confirmed context and QR merchant/amount.
Show loading, oversized, unavailable, no candidates and experimental states.
Matching failure leaves manual input available.

One tracked SDK job; double taps cannot start another. QR/context/config changes,
related evidence updates, reset and closure cancel work and ignore stale results.
New unrelated notifications do not alter a request's frozen candidate snapshot;
refresh is explicit. SDK repository is injected and actual reports are consumed.

Demo uses ADB reverse to loopback 8765 and debug-only network configuration.
Bearer is provided through in-memory debug configuration, never logged or
compiled into release. Release defaults to local facts only. Shared HTTPS
service deployment is a future increment.

## Delivery and acceptance

1. Authoritative core parser/contracts/local reports.
2. Notification context buffers, caption, independent dedup, cleanup/late media.
3. Pinned E5 matcher endpoint, resource bounds, smoke and synthetic benchmark.
4. Review/client selection/manual/consent/lifecycle and existing Laya integration.
5. Actual HTTP on device, debug/release builds and owned instrumentation, without
   uninstalling or clearing user data.

Acceptance covers package/summary filters, text/image-only, denied URI, API gate,
full queue, expiry/stop/revocation; same-object and separate/different chat cases,
replay/restart and late media without duplicate warnings; Unicode/UTF-16, text
oversize/token overflow, all parser statuses/channel/null/whole amounts;
prefix/pooling/finite cosine/stable ties/opaque ID/correlation; denied consent
makes zero requests; auth/offline/timeout/model failure preserve local facts;
stale results discarded; synthetic clear merchant/Indonesian slang/duplicate
merchant/no relevant context top-1/top-3 and latency; all existing Laya regressions
and four native smoke fixtures pass.

Provider pre-submit, OCR, persistent notification/chat archive, Laya retraining,
production policy approval and payment authorization are outside this PoC.

Sources: [Android active notifications](https://developer.android.com/reference/android/service/notification/NotificationListenerService#getActiveNotifications()),
[AOSP notification service](https://android.googlesource.com/platform/frameworks/base/+/refs/heads/android16-release/services/core/java/com/android/server/notification/NotificationManagerService.java),
[E5 model card](https://huggingface.co/intfloat/multilingual-e5-small/raw/main/README.md).
