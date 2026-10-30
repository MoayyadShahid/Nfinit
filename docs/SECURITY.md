# Security checklist

Status of each item after the security hardening PR (#38) and the fixes for the independent audit in `docs/SECURITY_AUDIT.md` (October 2026).

- **Done**: fixed or added in that PR.
- **In place**: already handled before it; checked during the review.
- **Owner**: a setting or account action outside the code.
- **Later**: not needed at the current size; the trigger says when.

## Access and data

| Item | Status | Notes |
|---|---|---|
| Row-level security | In place | Every table has owner-only RLS. The backend connects as `nfinit_backend` and sets the user per request. |
| Authorization bypass | In place / Done | Every user route checks the Supabase JWT (signature, issuer, audience, subject); `alg: none` and unknown algorithms are refused. Public by design: `/health`, the signature-checked Stripe webhook, and HMAC-signed mesh and event-stream links. Production startup refuses `NFNIT_ALLOW_LOCAL_AUTH_BYPASS`, and the website ignores it on Vercel production (audit NFI-012). |
| IDOR | In place | Every store query filters by the signed-in user's id, as well as RLS. Run snapshots and streams check the owner. |
| Least privilege | In place / Owner | The backend connects as `nfinit_api` and acts as `nfinit_backend`, which reaches only its own tables (never `postgres`). Every sandbox job drops root to a unique numeric uid, so concurrent jobs cannot read one another's files (audit NFI-001). Owner: use a Stripe restricted key (Checkout, Customers, Subscriptions, Billing Portal) instead of the full secret key. |
| Signed URLs | In place / Done | HMAC-SHA256, bound to a purpose, user and expiry. Production startup requires `NFNIT_MESH_URL_SECRET` to contain at least 32 bytes (audit NFI-010); use a different random value per environment. |
| Session expiration | Owner | Supabase access tokens default to 1 hour and refresh automatically; confirm the setting in Supabase → Authentication. Sign-out ends the session. |
| Secret exposure | Done | No secrets in the repository or its history. Only public values use `NEXT_PUBLIC_`. Errors shown to users never include internal exception text (audit NFI-011). Sandbox jobs cannot read the server's environment. |
| Audit logs | Later | Payments are logged in Stripe, and account deletion is logged by the backend. Trigger: team members or enterprise customers. |
| Data retention policies | In place | Stated in the Privacy Policy. Users delete projects and their account themselves. |

## Abuse and cost

| Item | Status | Notes |
|---|---|---|
| Rate limiting | Done | Runs: at most 2 concurrent, 30 per hour and 150 per day per user. Sandbox calls, including revision comparison and mesh rebuilds through download links: 60 per minute per user (audit NFI-002, NFI-003). Request bodies over 20 MiB are refused while streaming at both the Vercel proxy and backend; decoded images may total 10 MiB (NFI-006). Run reservations and sandbox windows are shared in Postgres across replicas (NFI-007). |
| Server-side validation | Done | Runs may use only the studio's models (`CAD_ALLOWED_MODELS`). Limits on message count, text size, code size, and image count, type and size. |
| Race conditions | Done | A PostgreSQL transaction-scoped advisory lock serializes each user's run count-and-insert and sandbox sliding window across every replica. SQLite uses `BEGIN IMMEDIATE` locally. Checkout's key remains stable for the unchanged billing state across time and return paths, and account deletion cancels every active subscription at Stripe (NFI-007, NFI-008). |
| Idempotency | In place | Webhooks read the subscription again from Stripe, so repeated or reordered events are safe. Customer creation and Checkout sessions use idempotency keys. |
| Prompt injection / sandbox | Done / Later | Generated code is checked by an AST policy, which refuses frame, generator, code and traceback internals, string formatting by attribute, structural pattern matching, and dunder strings (audit NFI-001). Each job then gets a fresh process and unique unprivileged uid, a secret-free environment, CPU/memory/file/process limits, Landlock write confinement to its private directory, bounded result transport, and a Linux seccomp filter that denies sockets, external programs, process creation, `io_uring`, ptrace, mounts and namespace changes while allowing CAD threads. The kernel controls fail closed if unavailable. Later defense in depth before enterprise customers: move jobs into a separate container or microVM. |
| SSRF | Done | The backend never fetches user-supplied URLs. Images must be inline `data:` pictures, so the model provider is not asked to fetch addresses either. |
| File upload validation | In place / Done | Thumbnails: WebP, PNG or JPEG, at most 512 KB. Chat images: type and size checked on the server. |
| Cost monitoring | Owner | Set a monthly credit limit and an alert in OpenRouter, and usage alerts in Railway and Vercel. Each run records its cost in USD. |
| Load testing | Later | Trigger: before a launch push or paid marketing. The sandbox limits concurrent jobs to `CAD_SANDBOX_MAX_CONCURRENCY`. |

## Web

| Item | Status | Notes |
|---|---|---|
| XSS | In place | React escapes all output. The only raw HTML is the static theme script. No user content is rendered as HTML. |
| CSRF | Done | The proxy refuses data-changing requests from another site (`Sec-Fetch-Site` or `Origin`). Session cookies are also `SameSite=Lax`. |
| Security headers | Done | Website: `X-Frame-Options`, `nosniff`, `Referrer-Policy`, HSTS, `Permissions-Policy`, and a CSP that blocks framing, plugins and foreign forms. API: the same, plus `default-src 'none'`. Later: a full script CSP with nonces. |
| Webhook verification | In place | Stripe signature checked with `STRIPE_WEBHOOK_SECRET`; invalid signatures get 400. |
| Dependency vulnerabilities | Done | Next.js 16.4.3, DOMPurify 3.4.17, Starlette 1.7, FastAPI 0.162, python-multipart 0.0.32, urllib3 2.8, anyio 4.15, certifi 2026.10.23 (audit NFI-005). `package-lock.json` is committed, so Vercel installs the audited versions (NFI-014). Pillow and VTK advisories are not reachable: they never read user files. Later: enable GitHub Dependabot. |

## Reliability and operations

| Item | Status | Notes |
|---|---|---|
| Timeouts | In place | Run deadline 300 s, model calls 120 s, sandbox jobs 90 s, proxy 30–110 s. |
| Retry logic / exponential backoff | In place | Model calls retry once. Stripe retries webhooks with backoff, and a failed sync returns 502 so Stripe retries. The studio retries polls and reconnects streams. |
| Background jobs | In place | Runs continue after the request ends and are saved on the server. Runs lost by a restart are reported as failed and do not count against limits. |
| Dead letter queues | Later | Stripe keeps failed webhook deliveries and lets you resend them. Trigger: a job queue (more than one backend replica). |
| Health checks | In place | `/health`, used by Railway. |
| Error monitoring / alerting | Owner, later | Railway logs and Vercel logs now. Trigger: paying users. Add Sentry (backend and frontend) with an email alert. |
| Structured logging | Later | Plain logs with run ids now. Trigger: more than one replica or a log search tool. |
| Database indexing | In place | Indexes on `(user_id, updated_at)`, `(user_id, created_at)`, revisions, run events and sandbox rate events. The quota queries use those indexes. |
| N+1 queries | In place | Lists use one query each. |
| Connection pooling | In place / Later | Through the Supabase session pooler. Trigger: connection errors under load; then use a pool in the backend. |
| Cache invalidation | In place | Meshes are cached by a hash of the code, so new code never shows an old mesh. Thumbnails use a version in the URL. |
| Feature flags | In place | Environment variables (`STRIPE_AUTOMATIC_TAX`, `PATTERN_RAG_ENABLED`, `CAD_SANDBOX_MODE`). |
| Database migrations | In place | `supabase/migrations`, applied once each by `supabase db push`, which records what it applied. Not every statement can be run twice by hand. |
| Rollback strategies | In place | Railway and Vercel can redeploy any earlier deployment. Migrations only add tables, columns and functions. |
| Automated backups / restore testing | Owner | Supabase Free has no point-in-time recovery. Before paying users: Supabase Pro (daily backups), and restore one backup into a test project once. |
| Disaster recovery | Owner | Code is on GitHub; the database is the only state. Covered by backups above. |
| Staging environment | Done / Owner | Preview builds disable Supabase authentication and backend API access by default, even if production-valued variables are accidentally assigned to Preview (audit NFI-009). Owner: create a separate Supabase project and Railway service, then set `NEXT_PUBLIC_NFNIT_PREVIEW_ISOLATED=true` on Preview only when preview data access is needed. Keep Vercel deployment protection enabled. |
| Zero-downtime deployments | In place | Vercel switches atomically. Railway starts the new backend before it stops the old one; runs in flight on the old one are reported as failed and can be retried. |

## Testing

| Item | Status | Notes |
|---|---|---|
| Payment webhook testing | In place | `test_billing.py` covers signatures, events, ordering and checkout. Owner: one real test-mode checkout with `stripe listen`. |
| End-to-end testing | Later | Browser checks were run by hand for each feature. Trigger: more than one developer; then Playwright in CI. |
| Contract testing | Later | One frontend and one backend in one repository. |
| Accessibility / mobile browser testing | Later | Pages are checked at 390 px width. Trigger: before a public launch push. |
