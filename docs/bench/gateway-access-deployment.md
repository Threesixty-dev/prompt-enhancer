# Protected gateway deployment follow-up

Date: 2026-10-13. Status: implementation candidate; live activation pending.

Task ID / atlas nodes / gate: bench-gateway-access; MA18, A20, W03, W07;
bounded deployment qualification under ADR 0025, not general beta acceptance.

Approved source baseline: the integrated core/bench implementation promoted in
`c068d93ee1f899704865eafd734a57f311f25219`. This follow-up changes only gateway
authentication, deployment composition, related synthetic checks and this guide.

Observable outcome: a dedicated consumer and separate rubric evaluator can
authenticate to a fixed HTTPS gateway protected by Cloudflare Access. Previously
both sent only the model Bearer key, which cannot satisfy a separate Access
service-token policy. Browser sign-in does not authenticate a container.
Both clients also send a fixed, descriptive application User-Agent; the gateway
must explicitly allow authenticated machine traffic under its existing policy.

Implementation: optional, paired deployment credentials supply the fixed
`CF-Access-Client-Id` and `CF-Access-Client-Secret` headers. Core configuration
contains environment-variable names only. Secrets pass through the existing
private worker input, never provenance or experiment definitions. The consumer
does not receive these service credentials; its isolated relay supplies them.
TLS verification, no redirects, bounded traffic, loopback listeners and separate
model keys remain enforced. Hosted model revision/license may be unknown and
remain `null`; local model manifest pinning remains required.

Checks: synthetic relay coverage rejects caller header replacement, redirects,
partial pairs and header injection; the HTTPS adapter withholds credentials on
a TLS pin mismatch. Core coverage checks explicit environment resolution,
separate model credentials and unknown provenance. The Compose checker verifies
the existing default, CPU and CUDA variants. No full suite or hosted CI wait is
part of this deployment follow-up.

Result: 53 targeted adapter/relay cases pass, as do Compose syntax validation,
the privacy scanner and whitespace checks. These are synthetic local results;
live service authentication and consumer/evaluator execution remain pending.

Completion criterion: immutable images, gateway-scoped service authorization,
separate restricted consumer/evaluator keys, authenticated readiness, one bounded
fictional consumer/evaluator attempt and owned-resource cleanup. Passing local
checks does not establish live gateway access or model quality.

Owner decisions: review this source change and authorize any newly provisioned
gateway credentials. Creating a gateway binding does not approve new transcript
sources, public exposure, unrelated infrastructure changes or release publication.
Deployment-specific endpoints, credentials and receipts stay outside Git.
