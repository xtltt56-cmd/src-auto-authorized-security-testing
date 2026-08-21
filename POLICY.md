# SRC-Auto Policy v1

## Authorization gate

`scope_candidate.yaml` is descriptive only. A real run requires a separately reviewed `scope_confirmed.yaml` containing `confirmed: true`, `allow_network_contact: true`, explicit hosts/ports, and a recorded authorization source. The control layer rejects a scope hash mismatch.

## Default-deny rules

The guard denies third-party SSO/CDN/payment/cloud/API hosts unless explicitly listed, denies excluded hosts and subdomains, rejects credentials in URLs, rejects non-HTTP(S) schemes, rejects disallowed ports, and fails closed on redirects outside the confirmed set.

## Allowed testing

Only non-destructive, platform-permitted observations are allowed: asset inventory, HTTP metadata, bounded crawling, passive checks, and safe candidate detection. Stop after sufficient proof. No brute force, credential testing, modification/deletion, DoS, persistence, lateral movement, or bulk personal-data collection.

## Cost and resource limits

- Default profile: `balanced`.
- The automatic local pipeline retains the monthly/daily `BudgetGovernor` controls for the existing Ollama route (`¥100`/`¥10` defaults).
- Manually confirmed remote Finding reviews have no monetary or call-count ceiling by design; they remain bounded per request (`2000` input tokens / `256` output tokens), require an exact preview digest and are recorded in `ai_reviews` for after-the-fact accounting.
- No paid asset APIs, VPS, residential proxies, or commercial scanners in V1.
- Project data warning at 80 GiB and hard stop at 90 GiB; evidence is retained minimally.
- CPU target <=70% and RAM target <=20 GiB; unknown metrics are reported as unknown rather than fabricated.

## Human decisions

The user must manually confirm the first real target's authorization snapshot, handle login/CAPTCHA, approve any paid action, and review the final report before submitting it to 补天.
