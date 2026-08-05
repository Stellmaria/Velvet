# Canonical media provider adapters

Issue: #459

## Result

- added a typed `MediaProviderAdapter` contract and registry;
- routed Kie and GRS through explicit adapters selected by stable model aliases;
- moved GRS violation parsing, image-only guard, balance fallback and retry policy
  into normal domain/infrastructure code;
- constructed the canonical friendly/economy worker directly instead of replacing
  `app.workers.KieGenerationWorker` during startup;
- made Vision model fallback an explicit `VisionClient` dependency rather than
  assigning `VisionClient.__init__` and `_read_json`;
- removed the GRS resilience, campaign, speedup and branding installer modules;
- retained the final Telegram-wide Auf redaction boundary;
- kept unknown-submit fail-closed semantics and sequential paid-attempt persistence.

## Validation

The exact implementation commit `14af196a3258e74bafb783a61d7671223856e36b`
passed Python compile, `git diff --check`, canonical architecture inventory checks
and 53 focused provider, worker, routing, composition and architecture tests in
GitHub Actions run `30991264086`.

## Safety

No migration, provider call, production restart or secret change is performed.
Provider cancellation remains explicitly unsupported and returns `False` without
network activity. Live provider payload/credit acceptance remains tracked by #412.
