# Privacy and security

The supplied fixture data contains no real conversations, addresses or identities. Source labels are visible in the UI, events and evidence. Neither camera credentials nor AWS keys enter frontend code. Live connectors are blocked until the owner's accounts and permissions are available.

Authentication uses generated per-installation passwords, memory-only salted scrypt hashes and random 256-bit session tokens. The private ignored bootstrap file is chmod 0600 within a 0700 data directory; deployments must protect the persistent volume and use owner-controlled HTTPS. Session tokens are SHA-256 hashed in storage, expire after eight hours and are revoked on logout. Cookies are HttpOnly/SameSite Strict, with Secure on HTTPS. The API checks household scope on state, contracts, incidents and media. The administrator may mutate only the isolated synthetic namespace; owners cannot invoke judge tools.

API mutations require idempotency keys and strict request models. Conflicting reuse returns 409. Origin checks prevent cross-origin commands; content types and max request sizes are checked at the application edge, and deployments must enforce request-size/time limits at a reverse proxy as well. Login and command routes have per-client rate limits; this local limiter is not distributed. The service sets CSP, no-referrer and no-sniff policies. Sensitive reads use no-store.

Consent revocation pauses collection, watchdogs and workouts. Resuming consent is an authenticated action; no hidden browser service records audio/video. There is no face matching or allegation of criminal intent. An uncertain arrival object stays uncertain. Human confirmations are labeled USER_CONFIRMED; they never masquerade as a sensor result.

Evidence defaults to seven-day accessibility. Expired media routes return 410. Disk removal/backup destruction are an operator responsibility in this local version; retention deletion across backups and cloud objects must be completed before live collection. Hashes detect modification, not truth or legal admissibility. SQLite is protected by filesystem permissions, not application-level at-rest encryption; use encrypted host volumes for real household data.

Reports end at an export or the isolated synthetic receiver. Approval requires the exact manifest digest, destination and deliberate confirmation phrase. MCP's `human_confirmed_boolean` is always denied as an authorization source. A signed/correctly timestamped Ring webhook still fails closed until account mapping and verified provider contracts are configured. The provisional HMAC wire contract must be checked against the actual partner documentation before live use.

Tests in `test_security.py` cover unauthorized access, cross-household media, forged webhooks, tampered blobs/manifests, revoked consent, expired evidence, count setters, approval bypass, stale revisions and rate limits. This is implementation testing, not an independent penetration-test certification.
