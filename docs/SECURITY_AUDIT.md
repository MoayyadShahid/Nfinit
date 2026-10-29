# Nfinit independent security audit

Audit date: 2026-10-28  
Repository revision: `261ec0a9e6d6` (`claude/security-hardening`)  
Auditor posture: read-only, except for creation of this report

## 1. Summary

Nfinit has a working ownership model in the repository, but its CAD executor is not a security boundary: a short generator-frame payload passed the AST policy and reached unrestricted Python built-ins, producing local command execution. A second critical issue lets any authenticated user, including a non-subscriber, execute arbitrary saved revision comparisons without the subscription or sandbox-rate gates. Three high-severity issues allow sustained mesh CPU abuse, make billing fail open when its key is absent, and leave reachable outbound TLS on a vulnerable `certifi` trust store. The live review was only partial: Vercel was inspectable, Supabase reported the Nfinit project as paused, and the saved Railway CLI login was unauthorized.

Counts: **2 Critical, 3 High, 7 Medium, 3 Low, 0 Info**.

## 2. Findings table

| ID | Severity | Area | Title | Status |
|---|---|---|---|---|
| NFI-001 | Critical | Sandbox | Generator frames escape the Python sandbox | verified |
| NFI-002 | Critical | Billing / cost | Revision comparison executes CAD code without payment or rate limits | verified |
| NFI-003 | High | Signed links / cost | Reusable mesh links bypass the sandbox limiter and can force repeated rebuilds | verified |
| NFI-004 | High | Billing | Missing Stripe configuration silently grants paid features | verified |
| NFI-005 | High | Dependencies | Reachable `certifi` trust-store advisory affects secret-bearing outbound TLS | verified |
| NFI-006 | Medium | Input validation | Request bodies are buffered before any transport-size limit | verified |
| NFI-007 | Medium | Cost controls | Run and sandbox quotas are not safe across backend replicas | unverified |
| NFI-008 | Medium | Billing / deletion | Concurrent checkout can create multiple subscriptions, but only one is tracked and cancelled | verified |
| NFI-009 | Medium | Vercel | Preview deployments use the production backend and Supabase configuration | verified |
| NFI-010 | Medium | Signed links | Missing signing secret falls back to an ephemeral per-process key | verified |
| NFI-011 | Medium | Error handling | A database/save exception is returned to the user | verified |
| NFI-012 | Medium | Authentication | Production startup does not forbid the local authentication bypass | verified |
| NFI-013 | Low | Web | OAuth return path accepts a backslash open redirect | verified |
| NFI-014 | Low | Supply chain | The npm lockfile is intentionally untracked | verified |
| NFI-015 | Low | Privacy | Optional LangFuse and Pinecone processors are absent from the privacy notice | unverified |

## 3. Findings

### NFI-001 — Generator frames escape the Python sandbox

**What is wrong.** `backend/execution/policy.py:7-25` blocks explicit `yield` but permits generator expressions. Its attribute rule at `backend/execution/policy.py:110-117` only blocks leading underscores and a short denylist, so `gi_frame`, `f_back`, and `f_builtins` are allowed. `_execute()` then evaluates the code in-process at `backend/execution/worker.py:407-410`. The worker only replaces Python's `socket` object and applies resource limits (`backend/execution/worker.py:160-180`); it has no process-count limit and the image runs as root because `backend/Dockerfile:1-30` never selects a non-root user.

**Evidence.** The following minimal payload was accepted by `validate_cad_code()`:

```python
g = (g.gi_frame.f_back.f_back.f_builtins["vars"](
    g.gi_frame.f_back.f_back.f_builtins["__import__"]("os")
)["popen"]("id") for x in [0])
h = list(g)[0]
result = int("".join(list(h)))
```

The policy test printed `POLICY=accepted`. Calling the repository's exact `_execute()` with a locally stubbed `build123d` import produced:

```text
ValueError: invalid literal for int() with base 10: 'uid=501(...) ...'
```

The `id` output inside the conversion error proves that the generated code recovered unrestricted `__import__`, imported `os`, and ran a command. No production endpoint was tested.

**Impact.** A subscriber, or a non-paying authenticated attacker through NFI-002/NFI-004, can execute commands inside the Railway container. The process can read the parent container filesystem and `/proc`, recover database, Stripe, OpenRouter and signing credentials, alter application files, make outbound requests through external binaries despite the Python socket patch, and inspect concurrent jobs' temporary directories. Because there is no `RLIMIT_NPROC`, command execution also makes fork-bomb denial of service possible. This is a production-secret compromise and cross-user compromise, not merely an escape into the attacker's own CAD part.

**Fix.** Stop treating an in-process Python AST denylist as the security boundary. Run every job in a separately isolated, non-root container or microVM with a read-only minimal filesystem, no service secrets, no host PID/proc access, no network namespace route, strict seccomp/AppArmor, PID/cgroup CPU and memory limits, and a per-job directory. As an immediate kill switch, disable generated-code execution until that boundary exists. Blocking `ast.GeneratorExp` and frame attributes (`gi_frame`, `f_back`, `f_builtins`, `f_globals`, `f_locals`) is useful defense in depth, but is not a complete fix for Python object-graph escapes.

**Effort:** large.

### NFI-002 — Revision comparison executes CAD code without payment or rate limits

**What is wrong.** `GET /projects/{project_id}/compare` uses the basic `UserId` dependency at `backend/projects/router.py:153-163`, then sends both saved revisions to `compare_code()` at lines 164-182. Unlike `/compare-models` and the other public sandbox routes (`backend/main.py:159-242`), it does not use `SandboxUserId`, so neither `require_subscription()` nor `limit_sandbox_calls()` runs. Creating a project and revisions also requires authentication but not a subscription.

**Evidence.** Route tracing shows the comparison handler accepts arbitrary revision `state.code` owned by the caller and directly executes the comparison. The corresponding guarded route is `backend/main.py:175-184`, whose `_user: SandboxUserId` dependency is absent here. This was not sent to production.

**Impact.** Any authenticated account can use a paid compute feature without paying and can continuously occupy sandbox capacity by comparing attacker-controlled revisions. In combination with NFI-001, this is also a no-payment path to container command execution.

**Fix.** Change the dependency and keep the authorization lookup:

```diff
-    user_id: UserId,
+    user_id: SandboxUserId,
```

Import `SandboxUserId` from `projects.limits` and add a test that an unsubscribed caller gets 402 and an over-limit caller gets 429.

**Effort:** small.

### NFI-003 — Reusable mesh links bypass the sandbox limiter and can force repeated rebuilds

**What is wrong.** The authenticated link-creation route is limited (`backend/projects/meshes.py:129-154`), but the direct `GET /meshes/{token}` handler has no limiter (`backend/projects/meshes.py:157-170`). A project stores only its most recently built mesh (`backend/projects/meshes.py:1-7, 91-112`). Two valid five-minute links for different revisions can therefore be alternated: each request sees the other revision's hash, executes `_build()`, and overwrites the one-entry cache.

**Evidence.** `LINK_SECONDS = 300` at line 33; `read_mesh_token()` binds user/project/revision at lines 38-54; `ensure_mesh()` rebuilds whenever the single stored hash differs at lines 91-112. The signed download handler calls it directly after token verification. No live requests were made.

**Impact.** One subscriber can keep all sandbox workers busy with CPU-heavy OpenCASCADE builds while bypassing the advertised 60-calls-per-minute user limit. The token is reusable for five minutes and new tokens can be issued, so the abuse can be sustained.

**Fix.** Consume the same user quota after extracting the signed token and before any build, and store meshes by `(project_id, revision_number, code_hash)` so a download never rebuilds an already issued artifact. Prefer issuing a link only after the artifact is complete and making the direct handler a pure read.

**Effort:** medium.

### NFI-004 — Missing Stripe configuration silently grants paid features

**What is wrong.** `billing_enabled()` checks only whether `STRIPE_SECRET_KEY` exists (`backend/projects/billing.py:40-41`). `require_subscription()` returns the caller without any subscription lookup when it does not (`backend/projects/billing.py:69-79`). Configuration validation does not require the Stripe variables.

**Evidence.** The exact branch is:

```python
if not billing_enabled():
    return user_id
```

The deployment example confirms this behavior at `deploy/railway.env.example:41-47`. Railway variables could not be read, so this audit does not claim the key is currently absent.

**Impact.** A missing, renamed, or accidentally removed production key turns off the paywall and grants every authenticated user model, export, preview, and sandbox features. This can rapidly consume OpenRouter and Railway spend.

**Fix.** Fail startup when any required billing variable is missing in a production deployment. If an explicit free/local mode is needed, require a separate opt-in such as `NFNIT_DISABLE_BILLING=true` and reject it when the deployment environment is production.

**Effort:** small.

### NFI-005 — Reachable `certifi` trust-store advisory affects secret-bearing outbound TLS

**What is wrong.** The locked main dependency set includes `certifi==2026.7.22`, flagged as `PYSEC-2026-4320`; the fixed line is `2026.10.18/2026.10.19`. Unlike the numerous Pillow/VTK advisories, `certifi` is reachable: HTTP clients use it while sending prompts and bearer credentials to OpenRouter and while contacting Stripe and other HTTPS services.

**Evidence.** A requirements list generated from `backend/poetry.lock` was checked with:

```text
uvx pip-audit --no-deps --disable-pip -r <generated-main-requirements>
Found 83 known vulnerabilities in 6 packages
certifi 2026.7.22 PYSEC-2026-4320 ...
```

The other flagged packages were `langgraph-sdk`, `opentelemetry-api`, Pillow, Pygments and VTK. Their vulnerable entry points are not used: the app builds a local LangGraph rather than `RemoteGraph`, has no inbound OpenTelemetry extraction middleware, does not decode user images with Pillow, and does not invoke the vulnerable VTK/Pygments paths.

**Impact.** An on-path attacker able to use the affected CA trust condition could impersonate an outbound service and receive OpenRouter/Stripe credentials, prompts, images, or generated code.

**Fix.** Update the locked `certifi` package to at least `2026.10.19`, regenerate the Poetry lock, and rerun the backend suite and `pip-audit`.

**Effort:** small.

### NFI-006 — Request bodies are buffered before any transport-size limit

**What is wrong.** Pydantic and `validate_run_request()` apply useful semantic limits (`backend/projects/limits.py:34-112`), but FastAPI must first parse the complete JSON body. The Next.js proxy likewise calls `request.arrayBuffer()` before forwarding (`frontend/src/lib/backend-proxy.ts:77-86`). The public Railway service has no repository-level ASGI or server request-body cap, so direct requests can consume memory before authentication and field limits run.

**Evidence.** The largest accepted run can already include eight 10 MB images, 400,000 text characters and 200,000 code characters. Repository search found no `Content-Length`/body-size middleware or Uvicorn/proxy request limit. Thumbnail and webhook handlers also read the entire body before their own checks.

**Impact.** An unauthenticated client can send oversized or chunked bodies to consume backend memory and worker time. Several concurrent requests could restart the service without needing a valid JWT.

**Fix.** Enforce a hard byte limit at the public edge before buffering, and add an ASGI receive wrapper that stops streaming after the same limit. Use a separate smaller limit for webhook/thumbnail routes and a documented upper bound for run JSON.

**Effort:** medium.

### NFI-007 — Run and sandbox quotas are not safe across backend replicas

**What is wrong.** `_run_locks` is a process-local `defaultdict` (`backend/projects/limits.py:115-121`). The count and insert occur under that lock (`backend/projects/runs.py:328-338`) but in separate database operations, so two replicas can both pass the same quota. `_sandbox_limiter` is also process-local (`backend/projects/limits.py:156-193`). Snapshot memory is intentionally local (`backend/projects/runs.py:75-89`).

**Evidence.** Code inspection verifies the process-local design. The current Railway replica count could not be read because the CLI login was unauthorized, so current production exploitability is marked unverified.

**Impact.** With `N` replicas, an account can approximately multiply the 60/minute sandbox limit by `N`, and parallel run starts can exceed concurrent/hour/day quotas. Snapshot previews become replica-dependent, as documented, but the cost controls are the security-relevant part.

**Fix.** Make quota check-and-create one PostgreSQL transaction protected by a per-user advisory lock or a serializable database function. Move the sliding-window limiter to a shared atomic store, or enforce it at a single gateway. Add a two-process concurrency test.

**Effort:** medium.

### NFI-008 — Concurrent checkout can create multiple subscriptions, but only one is tracked and cancelled

**What is wrong.** Customer creation has an idempotency key, but `checkout.sessions.create()` does not (`backend/projects/billing.py:210-268`), and there is no per-user/database lock around the active check. Two requests can create two subscription-mode sessions for the same customer. Webhook synchronization stores one `stripe_subscription_id`; account deletion cancels only that one (`backend/projects/account.py:30-46`).

**Evidence.** Lines 223-227 pass `options={"idempotency_key": ...}` only to customer creation. Lines 240-265 create the Checkout Session without options. The deletion path calls `subscriptions.cancel(record.stripe_subscription_id)` once. No Stripe object was created during this audit.

**Impact.** A double click, retry, or race can leave two active subscriptions. The last webhook wins the local record; billing portal/account deletion may leave the other subscription charging after the account is gone or after the user believes cancellation is complete.

**Fix.** Serialize checkout attempts per user and persist an attempt-specific Stripe idempotency key until the attempt completes/expires. Before deletion, list all active subscriptions for the stored customer and cancel every Nfinit-price subscription, then delete local data only after all cancellations succeed.

**Effort:** medium.

### NFI-009 — Preview deployments use the production backend and Supabase configuration

**What is wrong.** Vercel assigns the same four configuration entries to both Production and Preview: `BACKEND_URL`, `NEXT_PUBLIC_BACKEND_URL`, `NEXT_PUBLIC_SUPABASE_URL`, and `NEXT_PUBLIC_SUPABASE_ANON_KEY`. There is no separate preview backend/database.

**Evidence.** `vercel env ls --project nfinit` listed those names with targets `Production, Preview` and no Development entries. Values were not read or printed. Preview URLs returned a 302 to Vercel SSO with `noindex` and a Secure/HttpOnly SSO nonce, so deployment protection is enabled.

**Impact.** A preview built from unreviewed branch code can send an authorized preview user's production token and data to production services. SSO protection reduces who can reach the preview, but does not isolate production data from preview code or preview collaborators.

**Fix.** Give Preview its own Supabase project and Railway service. Restrict production variables to the Production target and keep preview SSO enabled.

**Effort:** medium.

### NFI-010 — Missing signing secret falls back to an ephemeral per-process key

**What is wrong.** If `NFNIT_MESH_URL_SECRET` is unset, `backend/projects/signed_links.py:23-38` generates a random in-memory key and only logs a warning. Startup validation does not reject the configuration.

**Evidence.** `_fallback_secret = secrets.token_bytes(32)` is returned by `_secret()` after the warning. Tokens therefore fail on a different replica or after a restart. Railway variables were unavailable, so this does not assert that production is currently missing the secret.

**Impact.** Mesh and SSE links become intermittently invalid in a multi-replica deployment and all outstanding links fail after a restart. This can expose users to broken downloads/streams and cause retry-driven extra work. Sharing the same secret across environments also removes cryptographic environment separation; purpose/user/resource/expiry binding still limits practical reuse unless those environments share data.

**Fix.** Require `NFNIT_MESH_URL_SECRET` at production startup, use a distinct random secret per environment, and support deliberate key rotation with a short verification-key overlap if needed.

**Effort:** small.

### NFI-011 — A database/save exception is returned to the user

**What is wrong.** Most unexpected agent failures are replaced with a generic message, but the post-generation save path interpolates the caught exception at `backend/projects/runs.py:271-278`.

**Evidence.** The persisted and API-visible error is:

```python
error = f"The part was generated but could not be saved: {failure}"
```

**Impact.** Driver exceptions can disclose internal hostnames, relation/column names, constraint details, SQL fragments, or operational state to the requesting user. The impact is limited to failures on that user's save path.

**Fix.** Log the exception server-side and persist a fixed user-facing message, matching the generic handling at lines 229-232.

**Effort:** small.

### NFI-012 — Production startup does not forbid the local authentication bypass

**What is wrong.** The backend bypass is a single environment flag (`backend/projects/config.py:4-9`). If it is true and Supabase auth is absent, `backend/projects/auth.py:79-86` returns a shared legacy user. `validate_project_configuration()` at `backend/projects/config.py:12-33` deliberately skips required production settings when the flag is true. The frontend similarly honors an explicit true value even in production (`frontend/src/lib/backend-proxy.ts:10-16`).

**Evidence.** Vercel's environment-name listing did not contain `NFNIT_ALLOW_LOCAL_AUTH_BYPASS`. Railway variables could not be read. The code path itself is verified; no production bypass request was attempted.

**Impact.** One accidental production variable can disable authentication and collapse all callers into the same account, exposing or changing that account's projects and permitting paid operations when combined with billing misconfiguration.

**Fix.** Make startup fail if the flag is true when `RAILWAY_ENVIRONMENT`, `VERCEL_ENV=production`, or an explicit `NFNIT_ENV=production` is present. Require loopback backend URLs and SQLite for bypass mode.

**Effort:** small.

### NFI-013 — OAuth return path accepts a backslash open redirect

**What is wrong.** `safeNextPath()` accepts any value starting `/` except `//` (`frontend/src/app/auth/callback/route.ts:5-7` and `frontend/src/components/LoginButtons.tsx:9-11`). URL parsing normalizes backslashes as authority separators.

**Evidence.** Local Node reproduction:

```text
new URL("/\\\\evil.example", "https://nfinit.dev/auth/callback").href
=> https://evil.example/
```

The accepted value can arrive from the query or `nfinit-auth-next` cookie and is passed to `NextResponse.redirect(new URL(path, requestUrl.origin))` at callback lines 20-22.

**Impact.** An attacker can send a login/callback link that redirects the victim to an attacker-controlled host after authentication. The Supabase authorization code is exchanged before the redirect and is not placed in the destination, so this is a phishing/open-redirect issue rather than direct session theft.

**Fix.** Reject `\\`, control characters and encoded separator variants, and validate by resolving then comparing `resolved.origin === requestUrl.origin` before redirecting.

**Effort:** small.

### NFI-014 — The npm lockfile is intentionally untracked

**What is wrong.** `.gitignore:3` excludes `package-lock.json`. Production installs can therefore resolve newer transitive versions than those audited locally, even when the source commit is unchanged.

**Evidence.** `npm audit --omit=dev --json` was clean for the locally resolved tree (0 advisories; 174 production dependencies), but that exact dependency graph is not committed.

**Impact.** A newly compromised or vulnerable compatible dependency can enter a Vercel build without review, and a clean audit cannot be tied reproducibly to the deployed artifact.

**Fix.** Remove the ignore rule, commit the lockfile, and use `npm ci` in CI/production.

**Effort:** small.

### NFI-015 — Optional LangFuse and Pinecone processors are absent from the privacy notice

**What is wrong.** The privacy page lists Supabase, OpenRouter, Anthropic, Stripe, Vercel and Railway (`frontend/src/app/privacy/page.tsx:17-49`), but not LangFuse or Pinecone. The backend can enable LangFuse when its two keys exist (`backend/agent/tracing.py:55-69`) and can enable Pinecone retrieval through environment configuration. LangFuse receives run identifiers plus counts and 16-character SHA-256 fingerprints, not raw prompt/image content (`backend/agent/tracing.py:13-47`). Pinecone receives a user-derived retrieval query and returns untrusted patterns.

**Evidence.** Code and privacy-page comparison verifies the omission. Railway environment names were unavailable, so whether either processor is active in production is unverified.

**Impact.** If enabled, personal-content-derived metadata or queries are sent to subprocessors that the published notice says are exhaustively listed, creating a transparency/compliance mismatch. Raw LangFuse prompt/image leakage was not found.

**Fix.** If either service is enabled, add it to the processor table with the exact data, purpose, region/retention, and link; otherwise explicitly keep the integration disabled in production.

**Effort:** small.

## 4. Verified checks with no finding

### Authentication and authorization

- JWTs: `alg:none` and unknown algorithms are refused; HS256 uses only `SUPABASE_JWT_SECRET`; RS256/ES256 use the Supabase JWKS; audience is fixed to `authenticated`; issuer is fixed when `SUPABASE_URL` is present; UUID subject is required. PyJWT checks expiry when the signed token has an `exp` claim. No algorithm-confusion path was found.
- Route inventory: `/health` is intentionally public; `/billing/webhook` is public but signature-verified; `/meshes/{token}` and run event streams are signed-link routes. Project CRUD, thumbnails, revision CRUD/listing, billing checkout/portal/status, runs, snapshots, link creation and account deletion all require a user. Every repository query inspected includes `user_id`; PostgreSQL also sets `request.jwt.claim.sub` and `SET LOCAL ROLE nfinit_backend` (`backend/projects/postgres_store.py:31-45`).
- IDOR: run reads, stream-link creation, stream polling, snapshots, meshes, thumbnails and revision compare all re-check owner-scoped rows. No cross-user identifier path was found.
- Account deletion: the function deletes the authenticated caller only. Repository migrations cascade projects, revisions, runs, events, subscriptions and meshes from `auth.users`. If Stripe cancellation succeeds and database deletion fails, the account and data remain while billing is stopped, and the API reports that state. NFI-008 is the exception for untracked duplicate subscriptions.

### Signed links, billing and prompt boundaries

- Signed tokens use HMAC-SHA256, `hmac.compare_digest`, explicit purposes, resource/user identifiers and absolute expiry (`backend/projects/signed_links.py:41-66`). They are replayable only until expiry by design. Cross-purpose substitution failed by construction.
- Stripe webhook signatures are checked with `STRIPE_WEBHOOK_SECRET` before parsing. Subscription events are re-read from Stripe, which makes duplicates and reordering largely idempotent. Checkout/portal `returnPath` rejects `//` and backslashes, so no Stripe return-path redirect was found.
- Models are allowlisted and each run has bounded repair/model steps. User text, images and current code are sent only to the configured model service; image inputs must be inline data URLs. Retrieved pattern text is bounded, delimiter-sanitized and labeled untrusted. No agent tool can reach another user's records or perform non-CAD application actions.

### Web, SSRF, logging and secrets

- No user/model content is rendered with `dangerouslySetInnerHTML`; React text escaping is used. No model-output XSS was found.
- State-changing backend proxy routes enforce same origin with `Sec-Fetch-Site` or `Origin`. The separate sign-out route is POST-only; Supabase SSR sets its auth cookies `SameSite=Lax`, so browsers omit them from cross-site POST navigations. No sign-out CSRF was established. Production headers on `/`, `/studio`, `/terms` and `/api/projects` matched `frontend/next.config.ts`: frame denial, `nosniff`, referrer policy, HSTS, permissions policy and the documented limited CSP. The statuses were 200, 307, 200 and 401 respectively. HTTP redirected to HTTPS with 308.
- No user-controlled server-side URL fetch was found. Backend egress destinations come from operator configuration; user images must be data URLs. Proxy path components are encoded and the backend base URL is an environment setting.
- Agent traces contain counts, role lists and short hashes rather than raw prompts, code or images. Backend logs can contain internal exception text but no intentional access-token, payment-card or prompt logging was found.
- Full-history scan across 150 commits found no non-placeholder OpenRouter, Stripe, JWT, AWS, GitHub, private-key or database-URL candidate and no committed `.env` other than examples. The successful webpack production build produced 60 static client files; scans found 0 server-secret variable-name hits and 0 secret-shaped value candidates.

### Repository Supabase design

The migrations define six public tables: `projects`, `project_revisions`, `cad_runs`, `subscriptions`, `project_meshes`, and `run_events`. Every one enables RLS. Policies are owner-scoped: projects (select/insert/update/delete), revisions (select/insert through owned projects), runs (select/insert/update), subscriptions (select/insert/update), meshes (select/insert/update through owned projects), and events (select/insert through owned runs). `anon` and `authenticated` table grants are revoked; `nfinit_backend` receives only the operations used by the store.

`nfinit_request_user_id()` has empty `search_path` and execute only for `nfinit_backend`. `nfinit_delete_my_account()` is `SECURITY DEFINER`, has empty `search_path`, takes no user argument, derives the caller from the request claim, and is executable only by `nfinit_backend`. No storage bucket is created by the repository. These are repository findings only; the live database could not be compared.

## 5. Claims in `docs/SECURITY.md` that are false or out of date

| Claim | Assessment |
|---|---|
| Line 14: every live table has owner-only RLS | Repository migrations support the claim, but the live project could not be inspected because it is paused; production status is unverified. |
| Line 15: every route checks a Supabase JWT | Literally false for intentionally public `/health`, Stripe webhook, signed mesh downloads and signed SSE. More importantly, production can be configured into the local bypass described in NFI-012. |
| Line 17: backend least privilege | Unverified live. `deploy/supabase.env.example:18` still recommends a `postgres` superuser URL, while the Railway example recommends `nfinit_api`; the former is unsafe and out of date. |
| Line 19: one-hour session expiry | A live Supabase auth setting, not proven by code; the paused project prevented verification. The decoder verifies `exp` if present but does not require the claim explicitly. |
| Line 20: run errors never include internal exception text | False; `backend/projects/runs.py:278` returns the save exception (NFI-011). |
| Line 28: all sandbox calls are limited to 60/minute | False; saved-revision compare and signed mesh downloads bypass the limiter (NFI-002/NFI-003). The limiter is also per replica (NFI-007). |
| Line 30: race conditions are done | False across replicas, and Checkout Session creation is not idempotent/serialized (NFI-007/NFI-008). |
| Line 31: checkout idempotency is in place | Only customer creation is idempotent; subscription-mode Checkout Session creation is not (NFI-008). |
| Line 32: malicious prompt can only affect the user's part | False; the reproduced sandbox escape executes container commands (NFI-001). |
| Line 46: dependency vulnerabilities are done | Out of date; reachable `certifi` advisory `PYSEC-2026-4320` is present (NFI-005). |
| Line 64: migrations are safe to run again | False as written: multiple `create table`, `create policy`, and role statements are not consistently guarded for idempotent reruns. |
| Line 68: preview deployments are a staging environment | Misleading: previews use production backend/Supabase settings, not an isolated staging environment (NFI-009). |

## 6. Test and tool results

### Existing tests

- `cd backend && pytest -q`: **failed during collection with 22 errors**. The system Python was 3.9 and did not have the locked application dependencies; the existing Poetry environment was also incomplete (including missing LangGraph/build123d imports). This is an environment/dependency failure, so no backend tests executed.
- `cd frontend && npx tsc --noEmit`: **passed**.
- `cd frontend && npx eslint .`: **failed with 4 errors and 4 warnings**. Errors were one React immutability violation at `LoginButtons.tsx:73` and three `set-state-in-effect` violations at `Studio.tsx:982`, `:999`, and `:1060`.
- Default `next build` with Turbopack failed in this sandbox because its internal CSS worker could not bind a port (`EPERM`). `npx next build --webpack` then **passed** and was used for the client-bundle secret scan.

### Dependencies

- `npm audit --omit=dev --json` from the repository root: **0 advisories**.
- `pip-audit` was not installed globally; `uvx pip-audit` was used against the exact Poetry main-package versions. It reported 83 advisory records in six packages. Only NFI-005 was reachable in this application; the other entry points were traced and excluded above.

### Vercel

- CLI authenticated; project `nfinit`, production domain `nfinit.dev`, root directory `frontend`, Node 24. Current deployment was READY.
- Environment names only: `BACKEND_URL`, `NEXT_PUBLIC_BACKEND_URL`, `NEXT_PUBLIC_SUPABASE_URL`, and `NEXT_PUBLIC_SUPABASE_ANON_KEY`, all targeted to Production and Preview. No Development entries and no `NFNIT_ALLOW_LOCAL_AUTH_BYPASS`. No server secret is named `NEXT_PUBLIC_*`; the Supabase anon key and URL are designed to be public.
- Preview deployment protection is enabled (Vercel SSO redirect). The visible scope was a personal owner scope; a complete collaborator/team access list was not available from the inspected CLI output.
- HTTPS and HTTP-to-HTTPS redirect worked. `nfinit.dev`, `www.nfinit.dev`, `nfinit.vercel.app`, the project alias and git-main alias remain reachable; `www` does not canonicalize to the apex. No direct security exploit was established from the extra aliases.

### Static Railway configuration

`backend/railway.toml:5-9` configures `/health`, a 30-second health timeout, restart-on-failure, and three retries. The Dockerfile exposes port 8000. Live settings, actual public domains/ports, replicas, resource limits, variables, deploy logs and response headers were not available.

## 7. Checks that could not be completed

### Supabase

The Supabase CLI was installed and authenticated. `supabase projects list` identified the Nfinit project in `us-east-1` with status `INACTIVE`; `supabase link --project-ref <Nfinit project> --yes` returned `ProjectPausedError: project is paused`. Consequently, no SELECT-only live comparison could be made for migration history, tables, RLS/policies, role grants, function ownership/execute grants, login role, auth providers, redirect allowlist, JWT expiry, refresh rotation, email confirmation, signup controls, Data API access, storage buckets, backups/PITR, or Security/Performance Advisor findings. No credentials were requested and no project state was changed.

### Railway

The Railway CLI was installed, but `railway status` reported no linked project and `railway list --json` returned that the saved login was no longer valid (`Unauthorized`). Therefore the audit could not verify variable presence, whether the Stripe key begins with the restricted or full-key prefix, the exact `CORS_ORIGINS`, absence of localhost/wildcards, the local-auth bypass variable, public networking, replica count, health/restart/resource settings, latest deploy logs, or production `/health` headers. The Vercel backend URL values were not read, so the API domain could not be recovered indirectly.

### Production behavior

Per the engagement rules, no production endpoint was attacked, no test user or Stripe object was created, and no settings or data were changed. Sandbox exploit validation was local only. Supabase Data API checks and authenticated Vercel-preview flows were not attempted because no approved test account/project was available.

## 8. Resolution (October 28, 2026)

Each finding was checked against the code before it was fixed. NFI-001 was reproduced through the real `inspect_code()` path, and the payload ran `id`.

| ID | Resolution |
|---|---|
| NFI-001 | Fixed in three layers. The policy refuses frame/generator/coroutine/code/traceback attributes, dangerous formatting, dunder strings, and structural pattern matching (which a follow-up review used to bypass the first fix). Every job gets a unique unprivileged uid, secret-free environment and process limits. On Linux, a fail-closed seccomp filter denies sockets, external program execution, ptrace, mounts and namespace changes. Root CI tests verify the original escape cannot read secrets/app files/another job, execute a binary, or create a raw socket. A separate container or microVM remains recommended defense in depth before enterprise use. |
| NFI-002 | Fixed. Revision comparison requires a subscription and counts against the sandbox limit. |
| NFI-003 | Fixed. A mesh rebuild through a download link counts against the sandbox limit. |
| NFI-004 | Fixed. Production startup requires the Stripe settings unless `NFNIT_ALLOW_FREE_ACCESS=true` is set on purpose. |
| NFI-005 | Fixed. certifi 2026.10.23. |
| NFI-006 | Fixed. The Next.js proxy and backend both stop declared or streamed bodies over `CAD_MAX_REQUEST_BYTES` (20 MiB by default). Decoded images may total 10 MiB, which fits after base64 expansion plus bounded text/code. |
| NFI-007 | Fixed. Run quota check-and-insert is one transaction under a per-user PostgreSQL advisory lock. Sandbox sliding-window events are stored in an owner-RLS table and updated under the same kind of cross-replica lock. Two-store concurrent tests cover both paths. Apply migration `20261029120000_shared_usage_limits.sql` before deploying the backend. |
| NFI-008 | Fixed. Checkout idempotency is derived from stable customer/subscription state, not the minute or return path, so concurrent retries resolve to the same Stripe session until a webhook changes billing state. Account deletion cancels every active subscription of the customer at Stripe. |
| NFI-009 | Fixed in code, with an operational follow-up. Vercel Preview builds disable Supabase auth and backend access by default. Enable them only with `NEXT_PUBLIC_NFNIT_PREVIEW_ISOLATED=true` after Preview has separate Supabase/Railway resources; production variables should still be removed from the Preview target. |
| NFI-010 | Fixed. Production startup requires `NFNIT_MESH_URL_SECRET`. |
| NFI-011 | Fixed. The save error is generic; details stay in the log. |
| NFI-012 | Fixed. Production startup refuses the bypass; the website ignores it on Vercel production. |
| NFI-013 | Fixed. One shared check resolves the return path and keeps it only on the site's own origin; backslashes and control characters are refused. |
| NFI-014 | Fixed. `package-lock.json` is committed. |
| NFI-015 | Fixed. The Privacy Policy lists LangFuse and Pinecone as optional processors, with the data each receives. |
| Section 5 | `docs/SECURITY.md` claims corrected. `deploy/supabase.env.example` no longer suggests connecting as `postgres`. |
