# QRIShield revision 6 — implementation evidence

Updated 3 October 2026. SDK workspace:
`/Users/hery/coding/sdk-hacknusa`. Android extraction baseline:
`/Users/hery/AndroidStudioProjects/HackNusa` at
`69c10057647205f513e0ee9a94faa255126ffe40`. The earlier temporary checkout's
results are historical, not validation of this baseline.

## Implemented

- Kotlin/JVM `qrishield-core` and `qrishield-client`, JVM 11 bytecode. The current
  Android parser is extracted once; host compatibility aliases delegate to it.
  All six statuses, Merchant Channel, CRC/duplicate checks, nullable fields and
  exact whole-rupiah observations remain intact.
- Neutral candidate/provenance/text/permission/request/report contracts.
  `findContext` freezes candidate collections. Assessment and matching snapshot
  digests bind QR/text/provenance/consent. Reports last at most two minutes.
  UTF-16 oversize and invalid Unicode are explicit, never silently shortened.
- Suspend repository operations, configurable HTTPS/loopback transport,
  in-memory token provider, HTTP response size limits, correlation/state/input
  digest checks, finite cosine and native label/probability/usage validation.
  Denied permission makes zero requests. Transport/timeout/model failures retain
  parser facts and expose unassessed semantic coverage. Cancellation propagates.
- Host WhatsApp adapter: callback and initial active snapshot without warnings,
  package/summary/API filters, one worker/queue eight, twenty messages/four media
  reads, all-text twenty-entry/five-minute buffer, source-age/replay checks.
  Caption and preview preserved; media four/two minutes; dedup independent of
  late-media evidence updates. Stop/revocation/disconnect clear buffers and
  invalidate notification-derived review work. No listener service calls.
- Review screen: explicit matching/semantic dialogs, three unselected suggestions,
  editable full observed text, manual and local-only options, actual SDK report,
  one tracked job, cancellation on edit/selection/reset/closure, report expiry.
- Local CPU E5 matcher staged and checksum verified, loaded offline once. Pinned
  revision `614241f622f53c4eeff9890bdc4f31cfecc418b3`; masked mean/L2, 384 dimensions,
  query/passage prefixes, 512-token preflight without truncation, batches <=4,
  stable cosine ranking. `/v1/context-match` 512 KiB/30 seconds shares one worker
  and four outstanding slots with the unchanged `/v1/semantic` 32 KiB contract.
  Timed-out native work keeps its slot; matcher failure leaves Laya available.
- Native Laya bundle/questions/labels/budgets are unchanged. Mapping sends only
  confirmed context plus QR merchant and whole-rupiah amount, null when absent.
  Raw QR/image/sender/notification linkage never enters native state.

## Host coordination

The user selected the new bank demo as primary host while another authorized
chat prepares that UI. Its owner handles MainActivity/bank files/manifests/build
and visual/device finalization. SDK changes are preserved through a bridge and
runtime debug seam; default bank remains **SDK belum terhubung**, without network.
SDK-owned review/notification adapters and tests remain available for explicit
owned debug validation. Release defaults to local facts only. Bank UI language
and preparation scope follow that chat's newer approved Indonesian bank plan.

The latest direct user instruction limits this chat to `sdk-hacknusa`; all
Android source/build/device work is owned by the bank chat. App changes before
that boundary are handed to its owner; this SDK chat will not edit or commit
HackNusa files. Device evidence is accepted only from that owner's actual runs.

`SdkRepository.configured()` exposes whether a repository was injected or a
runtime debug token explicitly configured. `RuntimeSdkConfiguration` never
compiles a token or URL into release. ADB reverse uses loopback port 8765.
Debug-only owned instrumentation receives its token over a temporary forwarded
socket (device8766 → host18766) after a READY handshake; no device token file,
command argument, APK secret or token logging is used.

## Verified so far

- Initial standalone SDK run: 11 JVM tests passed (four core, seven client).
  Final standalone rerun passed12 unit tests (four core/eight client), including
  validated native success and rejection of negative usage counts. An additional
  real Kotlin HTTP smoke test passed against both live E5 and Laya models,
  validating ranking/token overflow, request/digest/response mapping, auth failure
  and deterministic fallback facts. This run does not touch the Android checkout.
- Latest Android baseline debug/release/instrumentation builds and unit tests
  passed before final bank wiring. New final host build is coordinated with the
  bank owner. One interim build reported a debug/main listener label conflict;
  the owner has the exact merge repair. Do not count that build as passing.
- Fifteen Python contract/HTTP/shared-capacity tests pass, including matcher auth,
  distinct endpoint body limits, duplicate IDs, consent, shared worker timeout,
  native validation and existing Laya regressions.
- Four supplied native fixtures pass actual authenticated HTTP with unchanged
  labels/confidences/probabilities. Omitted/null amount, authentication, expired
  deadline, native token overflow and UTF-16 oversize probes pass.
- E5 smoke verifies finite unit-normalized `(N,384)` vectors. Synthetic HTTP
  benchmark: eight Indonesian cases, seven relevant-context cases; top-1 and
  top-3 both 7/7. Duplicate merchant/chat and no-relevant-context cases remain
  ambiguous and demonstrate why retrieval has no correctness threshold.
  Final fingerprint `04525d806eaab4ef443e2ea0d0d5490aa28fc480ea324a1a1b6aec03a4934fdf`.
  Recorded median 253.55 ms/max1914.1 ms under concurrent development load;
  earlier warm run median34 ms/max475.9 ms. Tiny synthetic sample, no quality or
  payment-safety generalization. Full rows: `services/laya/matcher-benchmark.json`.
- vivo V2043/API31 is connected. In-place APK upgrade succeeded. The first owned
  HTTP test timed out waiting for the token before injection; the test transport
  now has a READY handshake and a single orchestrator. Final device HTTP and
  SDK-specific review/notification acceptance have now passed, as reported by
  the authorized bank chat; results are recorded below. No uninstall or data clearing was performed.

## Commands

JDK25 build runtime, Java11 bytecode; Gradle9.6/Kotlin2.2.10. SDK:

```sh
JAVA_HOME='/Applications/Android Studio.app/Contents/jbr/Contents/Home' \
  ./gradlew --offline --no-daemon test :qrishield-client:localHttpSmoke
```

Android (owner controls concurrent build/device slot):

```sh
JAVA_HOME='/Applications/Android Studio.app/Contents/jbr/Contents/Home' \
ANDROID_HOME='/Users/hery/Library/Android/sdk' \
./gradlew --offline --no-daemon \
  -PqrishieldSdkDir=/Users/hery/coding/sdk-hacknusa \
  -Dorg.gradle.java.installations.paths='/Applications/Android Studio.app/Contents/jbr/Contents/Home' \
  testDebugUnitTest assembleDebug assembleRelease assembleDebugAndroidTest
```

Service:

```sh
services/laya/.venv/bin/python services/laya/run_local.py
services/laya/.venv/bin/python -m unittest discover -s services/laya -v
services/laya/.venv/bin/python services/laya/verify_native_http.py
services/laya/.venv/bin/python services/laya/benchmark_matcher.py
```

Native model outputs remain experimental. No production policy approval,
authentication, OCR, persistent chat/archive, retraining or payment execution is
included. SDK-specific device/host validation is now recorded below. Final bank UI
preparation remains owned by the bank chat.

## Coordinated Android acceptance — 3 October 2026

Sanitized results supplied by the authorized bank chat, using synthetic fixtures
and isolated history. This SDK chat did not edit or run commands in HackNusa
following the user’s workspace restriction.

| Suite | Result |
| --- | --- |
| SdkIntegrationTest | 1 passed; actual device HTTP E5 + Laya, 6.223 seconds |
| App JVM | 25 passed |
| BankQrFlow | 6 passed |
| NotificationContext | 3 passed |
| SdkReview | 2 passed |
| NotificationPreview | 5 passed |
| ProductionWarning | 3 passed |
| QrisReviewAcceptance | 5 passed |

Device token used the temporary memory-only READY handshake. The bank chat copied
the harness and its output to `/tmp`, making no SDK workspace writes. Default
bank repository remains null; debug `BankRepositoryProvider` permits explicit
configured/injected integration; release remains null/offline.

Bank fake consent/cancellation acceptance passed. Its remaining fallback
selector assertion and final large-text/landscape UI review are owned by the bank
chat and are not claimed complete here. These pending bank UI checks do not
change the recorded SDK unit, service, actual Kotlin HTTP or device HTTP results.
