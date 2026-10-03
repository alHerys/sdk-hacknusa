# QRIShield SDK PoC

JVM core/client with a local CPU E5 matcher and native Laya service. Experimental
context retrieval and semantic labels; no merchant authentication/payment approval.

## Build

Use Gradle 9.6, Kotlin 2.2.10, Java 11 bytecode (build runtime JDK 25):

```sh
./gradlew test
```

Modules: `qrishield-core`, `qrishield-client`. Android consumes this checkout with
`-PqrishieldSdkDir=/absolute/path/to/sdk-hacknusa` in a composite build.

## Service

Existing local environment is `services/laya/.venv`. Runtime versions are pinned
in `requirements-macos.txt` and `runtime-lock.txt`. Supplied Laya bundle stays
immutable. Stage the pinned E5 model once (network needed only for staging):

```sh
services/laya/.venv/bin/python services/laya/stage_matcher.py
services/laya/.venv/bin/python services/laya/run_local.py
```

The launcher creates a private local `.env` bearer token without printing it.
Default loopback is port 8765. E5 release checksums are in `matcher-release.json`.
Weights are ignored build artifacts, never included in the APK.

```sh
services/laya/.venv/bin/python -m unittest discover -s services/laya
services/laya/.venv/bin/python services/laya/verify_native_http.py
services/laya/.venv/bin/python services/laya/benchmark_matcher.py
adb reverse tcp:8765 tcp:8765
```

Enter the server token in the host's “Configure local service · debug” dialog;
configuration is process memory only. Release has no Internet permission or
loopback configuration from the SDK integration and defaults to local reports.
Do not paste tokens into logs, source or release build configuration.

## Usage

```kotlin
val sdk = QriShieldClient(ClientConfiguration(
    "http://127.0.0.1:8765", TokenProvider { runtimeToken }
))
val matching = sdk.findContext(ContextMatchRequest(
    QrObservation(selectedPayload), candidates.toList(),
    ProcessingPermissions(matching = true), System.currentTimeMillis() + 30_000
))
// User chooses and edits context, then gives separate assessment permission.
val report = sdk.assess(AssessmentRequest(
    QrObservation(selectedPayload), reviewedContext,
    ProcessingPermissions(semantic = true), System.currentTimeMillis() + 30_000
))
```

The host must cancel the job and discard the report on input/config changes,
closure and notification evidence revocation. Reports expire in two minutes.
Zero permission means zero transport requests. Do not interpret cosine or native
class probabilities as payment confidence.

See [revision 6](SDK-PLAN.md) and [implementation evidence](IMPLEMENTATION.md).

For a real-model JVM client smoke test after the service is ready, run
`./gradlew :qrishield-client:localHttpSmoke`. It reads the private local token only
inside the test process; it never passes it as a command argument.
