# Repository review and migration decisions — revision 4

Reviewed 3 October 2026 (Asia/Jakarta). Current repository: [alHerys/HackNusa-Mobile](https://github.com/alHerys/HackNusa-Mobile), branch `main`, commit `73e1449d5362029c3fe057d6e5ca6d7b5a6c6626`. Commit timestamp: 3 October 2026, 09:01:15 +07:00; subject: “Add project documentation and update gitignore”.

## Review scope and access correction

Source was successfully obtained through a shallow HTTPS Git clone. The connected GitHub metadata tool still returned 404; that failure did not prevent Git access. Revision 3's statement that current source could not be inspected is superseded by this review.

Inspected production acquisition, parser, request/repository boundary, notification routing, history, manifests, build configuration, and selected unit/instrumentation tests. README statements were checked against source where discussed below. No ancestry comparison with HacknusaQRIS was performed. The old commit `ac373a17f58d8763b9a898388ca851f1ee8ec0ca` remains historical context only.

No `AGENTS.md`, tracked `.github` workflow, or license file was found in the inspected checkout. Absence of a license file leaves redistribution terms unresolved; it does not establish permission or prohibition by itself.

## Verified current application

| Item | Observed state |
|---|---|
| Stack and layout | Native Android/Kotlin/Compose; one Gradle module `:app`; package/application ID `com.example.hacknusa` |
| Build configuration | AGP 9.4.1; Kotlin Compose plugin catalog 2.2.10; wrapper 9.6.0; daemon toolchain 25; Java source/target 11; minSdk 24; compile/target SDK 37 |
| Acquisition | Share image, gallery, system camera photo, MediaProjection single-frame capture, and available WhatsApp notification media |
| Decoder | Local ZXing 3.5.3; multiple QR candidates, explicit selection; no ML Kit dependency in current app build |
| User context | Reviewed note/share text; no OCR; notification media acquired with null supplied text |
| Verification boundary | Typed `VerificationRequestFactory` → suspend `VerificationRepository.examine` |
| Active implementation | `UnavailableVerificationRepository`; sealed result has only `Unavailable` |
| Network/model | No INTERNET permission in production manifest; no active HTTP/Gemini/Firebase/Laya integration found in inspected production source/dependencies |
| Payment provider | No authenticated provider inquiry/final-instruction/payment-submission hook found in inspected flow |
| Local history | SQLite summaries, maximum 50 rows/seven days; time/source/candidate count, no request/payload/message columns; backup disabled |
| Tests | Parser JVM tests and acquisition/request/routing/history/capture/UI instrumentation tests present; execution limits below |

Build observations are source configuration, not a recommendation to upgrade another project. In particular, daemon toolchain 25 and Java source compatibility 11 describe different concerns. See [app build](https://github.com/alHerys/HackNusa-Mobile/blob/73e1449d5362029c3fe057d6e5ca6d7b5a6c6626/app/build.gradle.kts), [version catalog](https://github.com/alHerys/HackNusa-Mobile/blob/73e1449d5362029c3fe057d6e5ca6d7b5a6c6626/gradle/libs.versions.toml), and [daemon toolchain](https://github.com/alHerys/HackNusa-Mobile/blob/73e1449d5362029c3fe057d6e5ca6d7b5a6c6626/gradle/gradle-daemon-jvm.properties).

## Actual flow and contract

Production acquisition hands session evidence to `EvidenceReviewActivity`. QR decoding is local; multiple candidates require selection. The user reviews a note and taps **Periksa**. The activity prepares one selected payload and note, calls a directly constructed unavailable repository, discards its return value, and sets the unavailable UI state. This is an acquisition/request MVP, not a working semantic verification service. See [review activity](https://github.com/alHerys/HackNusa-Mobile/blob/73e1449d5362029c3fe057d6e5ca6d7b5a6c6626/app/src/main/java/com/example/hacknusa/acquisition/EvidenceReviewActivity.kt) and [repository](https://github.com/alHerys/HackNusa-Mobile/blob/73e1449d5362029c3fe057d6e5ca6d7b5a6c6626/app/src/main/java/com/example/hacknusa/verification/VerificationRepository.kt).

The request has `message`, `qris`, and `context` only. It contains parsed observations rather than raw QR/image. `message.language` is hardcoded `id`; blank text becomes null and other text is silently limited with `take(4096)`. `merchant_id` remains null. All three context values default to null and the production call uses those defaults. Caption proximity or notification membership is not authenticated evidence of payment context. See [request and serializer](https://github.com/alHerys/HackNusa-Mobile/blob/73e1449d5362029c3fe057d6e5ca6d7b5a6c6626/app/src/main/java/com/example/hacknusa/verification/VerificationRequest.kt).

`amount_minor` means whole rupiah in this MVP: Rp350,000 serializes as `350000`, not `35000000`. It must be mapped explicitly when introducing any generic SDK money representation. Tag54 alone supplies amount; text does not. Fractional nonzero rupiah yields `UNSUPPORTED_AMOUNT`, while `.00` is representable. Unknown nullable fields are retained as JSON null.

The parser handles bounded printable ASCII EMV-style TLV, rejects duplicates/truncation, checks mandatory fields and selected nested templates, and recognizes its supported QRIS subset through country `ID`, currency `360`, and GUI `ID.CO.QRIS.WWW`. It checks a final uppercase hexadecimal CRC with UTF-8 computation; ASCII restriction removes the earlier Latin-1 fallback. This remains conservative local recognition, not full scheme certification or merchant authentication. See [parser](https://github.com/alHerys/HackNusa-Mobile/blob/73e1449d5362029c3fe057d6e5ca6d7b5a6c6626/app/src/main/java/com/example/hacknusa/qris/QrisParser.kt).

The WhatsApp listener reads structured messages for `com.whatsapp`, ignores group summaries, and uses a standalone QRIS-word trigger for a local reminder. It does not assign a fraud verdict. Missing/expired buffered evidence routes users to scanner reacquisition. Capture, overlay permissions, notification permissions, and backend consent must remain separate. See [notification protection](https://github.com/alHerys/HackNusa-Mobile/blob/73e1449d5362029c3fe057d6e5ca6d7b5a6c6626/app/src/main/java/com/example/hacknusa/notification/Protection.kt), [capture](https://github.com/alHerys/HackNusa-Mobile/blob/73e1449d5362029c3fe057d6e5ca6d7b5a6c6626/app/src/main/java/com/example/hacknusa/probe/ScreenCapture.kt), and [manifest](https://github.com/alHerys/HackNusa-Mobile/blob/73e1449d5362029c3fe057d6e5ca6d7b5a6c6626/app/src/main/AndroidManifest.xml).

## Historical findings reclassified against current code

“Fixed” below means the reviewed current implementation addresses the old behavior by source inspection. It does not mean a cross-repository patch was identified or tests passed in this session. Test references indicate assertions present in source.

| ID | Current status | Evidence and remaining scope |
|---|---|---|
| R01 | fixed for duplicate overwrite; extraction refinement remains | `tlv` rejects duplicate IDs at every parsed level. CRC is computed separately; tag62 is parsed again during unsupported-field detection. Consolidate into one structured observation when extracting; do not claim existing single-pass parsing. |
| R02 | fixed | Malformed amount returns `MALFORMED`; absent tag54 has `amountEncoded=false`; fractional nonzero values return `UNSUPPORTED_AMOUNT`. Parser tests cover malformed, absent, and fractional cases. Failure results currently discard field-level details; richer diagnostics are future SDK work. |
| R03 | fixed for historical permissiveness; recognition still bounded | Exact payload header/value plus ID/360/QRIS GUI gate. Other GUI returns `NOT_QRIS`; some unvalidated fields return `UNSUPPORTED`. No authoritative full QRIS conformance mapping was checked. |
| R04 | fixed | Last TLV must be63 with four uppercase hex digits; appended tail becomes malformed; UTF-8 only, printable ASCII gate. Tests include appended data and corrupted CRC. |
| R05 | replaced_not_applicable | No current `MerchantNormalizer` or authoritative substring merchant matching was found. The active path produces no semantic relation. |
| R06 | replaced_not_applicable | No `LocalResultValidator`/CONSISTENT verdict; only unavailable result exists. Required-check policy remains to be implemented in SDK. |
| R07 | replaced_not_applicable | There is no consistency headline to override CRC. Keep invalid-artifact precedence when adding real reports. |
| R08 | replaced_not_applicable; new integration gap M01 | No current `runGemini` inference timeout. Generation/job protection exists for acquisition, but the Periksa coroutine does not reuse it for future remote results. |
| R09 | fixed for inspected historical logging pattern | Request `toString()` is redacted, no production `Log.*`/println content logging found, history schema holds metadata only. No runtime/crash-SDK privacy audit was executed. |
| R10 | replaced_not_applicable | Current UI collects reviewed text; it does not depend on Gemini extracted recipient/amount fields. Preserve this input for Laya; do not reintroduce arbitrary entity extraction. |

Relevant regression source: [parser unit tests](https://github.com/alHerys/HackNusa-Mobile/blob/73e1449d5362029c3fe057d6e5ca6d7b5a6c6626/app/src/test/java/com/example/hacknusa/qris/QrisParserTest.kt) and [request instrumentation tests](https://github.com/alHerys/HackNusa-Mobile/blob/73e1449d5362029c3fe057d6e5ca6d7b5a6c6626/app/src/androidTest/java/com/example/hacknusa/QrisRequestTest.kt).

## Current integration gaps that change the SDK plan

These are implementation gaps or inferred future risks, not reproduced exploits in the current offline MVP.

| ID | Finding | Required plan change |
|---|---|---|
| M01 | Activity constructs unavailable repository directly, ignores returned result, and does not track verification as acquisition job/busy/generation | Inject repository; freeze selected QR/note; track one assessment job; map typed results; guard completion after reset/new selection; handle owned timeout separately from external cancellation. Current immediate stub does not demonstrate a remote race. |
| M02 | Factory silently truncates text to4096; language is fixed `id` | SDK must reject oversized input or record visible truncation and disable affected semantic approval. Retain compatible MVP limit; do not silently score a shortened message as complete evidence. Specify language support. |
| M03 | MVP wire contract lacks request/profile IDs, provenance, permissions, deadlines, digests and authoritative final instruction | Introduce explicit versioned SDK/semantic DTOs with a deliberate adapter. Do not silently rename/reinterpret existing request fields or pretend its null context proves linkage. |
| M04 | Parser returns aggregate statuses and may discard all observations on failure; some nested TLV parsing repeats | Extract structured diagnostics and one parse tree; retain supported fixtures and conservative unsupported behavior. Invalid content must gate dependent tasks locally. |
| M05 | No network/service response contract or model artifact in inspected app | Build typed unavailable flow first, agree HTTPS/auth/response contract, then add transport and independently gated Laya tasks. No endpoint or trained-model readiness is established here. |
| M06 | UI currently promises no upload; local summary history intentionally drops evidence | Before enabling explicit-user remote assessment, update disclosure/consent and keep request ephemeral. Do not reconstruct from summary history or add background upload/retry persistence as an incidental integration change. |

## Revised extraction map

All current production Kotlin paths below are relative to `app/src/main/java/com/example/hacknusa/`. Destinations are proposals, not modules already present.

| Current file | Planned responsibility |
|---|---|
| `qris/QrisParser.kt` and its data types | Pure JVM core parsing/observations; preserve corrected duplicate, amount, profile and CRC behavior; add diagnostics |
| `verification/VerificationRequest.kt` | Core request contracts plus explicit host/MVP wire mapper; move Android-free serializer only if its versioned role is retained |
| `verification/VerificationRepository.kt` | Keep host seam; SDK-backed adapter delegates to client assessment; unavailable adapter remains usable |
| `acquisition/EvidenceReviewActivity.kt` | Host selection/review, permissions, lifecycle and result rendering; inject adapter instead of hardcoding stub |
| `acquisition/SharedImageReader.kt`, `ShareActivity.kt` | Android URI/image acquisition and ZXing decoding remain host-side |
| `notification/Protection.kt`, `probe/ScreenCapture.kt` | Android-only reminders/capture; no automatic semantic invocation |
| `probe/AcquisitionHistory.kt` | Host summary retention; preserve schema/migration and deletion behavior |
| New `PolicyComposer`, binding and semantic adapter | New SDK responsibilities; no current code claimed as equivalent |

## Validation evidence and limits

`./gradlew --offline --no-daemon testDebugUnitTest` was attempted in the review checkout. It stopped before tests because the sandbox could not create the Gradle wrapper lock under `/Users/hery/.gradle`. No build, unit-test pass, device test, CI result or real-model evaluation is claimed. The installed shell Java reports21; the repository daemon configuration requests25. README's prior build verification is a repository claim, not execution evidence from this review.

For implementation validation, use a compatible isolated Gradle/JDK/Android SDK environment, run `testDebugUnitTest`, `assembleDebug`, and `assembleRelease`, then selected instrumentation tests with the existing `OwnedTestRunner` and isolated history database. Do not clear real user data. Add remote-adapter tests for deadline/auth/schema/offline failures and stale completion when that feature is implemented.

Only the two documentation files in the SDK planning workspace were changed. HackNusa-Mobile source and the original Downloads documents were not modified. Companion documents named by the earlier plan were not provided in this workspace and have not been validated.
