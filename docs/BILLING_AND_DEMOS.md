# Billing and demo parts

## Product rule

Anything pre-built is free to look at. Anything you create or take away needs
the $20/month subscription (USD, tax added at checkout). There is no free
trial and no free generation.

| Action | Free (signed in) | Subscribed |
| --- | --- | --- |
| Browse demo parts, orbit, zoom | ✓ | ✓ |
| Replay a demo's chat step by step | ✓ | ✓ |
| Type in the chat box | ✓ (Send opens the paywall) | ✓ |
| Send a prompt / generate | Paywall: "Your turn." | ✓ |
| Select a face to edit | Paywall: "Your turn." | ✓ |
| Advanced code editor | Paywall: "Your turn." | ✓ |
| Download STL / STEP (demo or own) | Paywall: "Take it into the real world." | ✓ |

## Paywall behaviour

- A panel slides up over the bottom of the studio. It never blocks typing and
  never appears on page load or on a timer.
- One click closes it. No guilt-trip wording, countdowns or fake urgency.
- Shown once per attempted action.
- Before Checkout, the pending action is stored (`sessionStorage`): the prompt
  text, or the export format and part. After Checkout the studio waits for the
  subscription to become active, then resumes it automatically — the prompt
  is sent, or the download starts.

Copy:

> **Your turn.**
> You've seen how it's built. Now describe yours.
> **Start building — $20/mo + tax** · Cancel anytime

> **Take it into the real world.**
> Export any part you build as STL or STEP — ready for printing or your CAD tool.
> **Start building — $20/mo + tax** · Cancel anytime

## Enforcement is on the backend

Hiding buttons is not a paywall. Today the sandbox endpoints
(`/generate-mesh`, `/inspect-model`, `/analyze-model`, `/compare-models`,
`/export-model`) take no login and are called from the browser directly, so
anyone can run the sandbox and export for free. As part of this work:

1. Those endpoints move behind the Next.js proxy (`/api/cad/...`) like
   projects and runs already are, so they carry the user's Supabase token.
2. The backend requires an active subscription on `POST /cad/runs` and on
   every sandbox endpoint, answering `402` with
   `{"detail": "subscription_required"}` otherwise.
3. Demo parts are static files, so viewing them never touches the sandbox.

Local development keeps working without Stripe: when Stripe is unconfigured
and `NFNIT_ALLOW_LOCAL_AUTH_BYPASS` is on, everyone counts as subscribed.

## Stripe design

Stripe lives in the backend, which already owns the database.

- `public.subscriptions` (one row per user): `user_id`, `stripe_customer_id`,
  `stripe_subscription_id`, `status`, `current_period_end`,
  `cancel_at_period_end`, `updated_at`. Same RLS pattern as `projects`.
- Access is granted for status `active`, `trialing` and `past_due` (Stripe is
  retrying the card). `canceled`, `unpaid`, `incomplete` lose access.
- Routes:
  - `GET /billing/status` — the signed-in user's subscription.
  - `POST /billing/checkout` — Stripe Checkout Session for the monthly price;
    reuses the user's Stripe customer; `user_id` is written to the
    subscription's metadata so every webhook can find the user.
  - `POST /billing/portal` — Stripe Customer Portal (cancel, change card,
    invoices).
  - `POST /billing/webhook` — public, signature-verified. Handles
    `checkout.session.completed` and `customer.subscription.created|updated|deleted`.
- The studio page reads `/billing/status` on the server so the paywall state
  is known on first paint.

## Demo parts

Six recorded build stories, served as static files from
`frontend/public/demos/` (6.4 MB):

| Demo | Steps |
| --- | --- |
| 5-inch drone frame (first for free users) | body and arms → motor holes → flight-controller holes → weight-saving slots → corner fillets |
| Desk phone stand | base, lip and back support → cable slot → edge fillets |
| Desk cable clip | plate and cradles → countersunk holes → corner fillets |
| Under-desk headphone hook | plate, drop and arm → retaining lip → countersunk holes |
| Raspberry Pi base tray | tray → standoffs → floor vents → port openings |
| L-bracket | legs → countersunk holes → gusset |

Each folder has `demo.json` (for every step: the prompt, the agent's plan,
trace and recorded progress events, the code, the finished GLB and the
previews of the features that step adds) and the GLB files. `index.json`
lists the demos.

**Replay.** The studio plays a step like a live run: the prompt appears in the
chat, the recorded progress events play in the step list (compressed to at
most 7 seconds; the durations shown are the recorded ones), the step's new
features grow in the viewport, and then the finished part appears. "Next
step", "Replay step" and "Watch again" move through the story. Replays make no
backend calls.

**Who sees what.**

- A free user with nothing open lands in the drone-frame demo.
- Everyone sees "See how it's built" cards under the prompt box on the
  welcome screen, and `/studio?demo=<slug>` opens a demo directly.
- Sending a prompt, selecting a face and exporting open the paywall for free
  users. For subscribers, a prompt builds on the demo part as a new project,
  and export works as for any part.

**Regenerate.** From `backend/`, with `OPENROUTER_API_KEY` set:

```bash
CAD_SANDBOX_MODE=fork poetry run python -m demos.build [--only drone-frame]
```

The script runs the production agent on the prompts in `backend/demos/specs.json`,
step by step, as the studio would. Each first step asks for the base shape
only ("no holes, slots, cutouts or fillets yet") and each later step for one
change ("keep everything else exactly as it is"): without this the agent adds
most features in step 1 and the later steps show nothing new. A demo whose
step fails or times out is left out. The 2026-10-08 builds cost about $4 in
total with Claude Sonnet 5.5.

The phone stand's fillet step first timed out twice. With `effort: "high"`,
OpenRouter reserves 80% of `max_tokens` for an Anthropic model's reasoning,
which left about 1,600 of 8,192 tokens for the code, so calls ended with
`finish_reason=length` and no content. The agent now gives Anthropic models an
explicit reasoning budget and 32,000 tokens of output room; with that, the
step built on its first try.

## Build order

1. Backend: subscriptions table, billing routes, webhook, `402` gate on runs
   and sandbox endpoints, tests.
2. Frontend: proxy routes for sandbox endpoints, billing client, paywall
   panel, gate on send / face select / editor / export, resume after Checkout,
   "Manage subscription" in the account menu.
3. Demo gallery and replay; generate and commit the demo parts (done).
4. End-to-end in Stripe test mode, then switch to live keys.

## Setup the owner does in Stripe (test mode first)

1. Product "Nfinit", recurring price $20/month → copy the price ID.
2. Developers → API keys → secret key.
3. Developers → Webhooks → endpoint `https://<railway-backend>/billing/webhook`
   with the four events above → copy the signing secret.
4. Settings → Billing → Customer portal → enable cancel and payment-method
   updates.
5. Railway env: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`,
   `STRIPE_PRICE_ID`, `APP_URL=https://nfinit.dev`.
