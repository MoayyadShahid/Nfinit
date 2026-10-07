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

4–6 parts, each a short build story (3–5 prompts). Stored as static files in
`frontend/public/demos/<slug>/`: `demo.json` (title, steps with the user
prompt, the agent's plan/trace summary and code) and one `step-N.glb` per
step. Generated once by a script that runs the real agent, then committed.

The studio's welcome screen keeps the prompt box (Send → paywall) and adds a
"See how it's built" row of demo cards. Opening a demo shows the viewport and
the chat replay; stepping through the chat swaps in that step's model.

Candidate set: wall-mount phone stand, Raspberry Pi enclosure with vents,
L-bracket with countersunk holes, 20-tooth spur gear, cable clip, desk
headphone hook.

## Build order

1. Backend: subscriptions table, billing routes, webhook, `402` gate on runs
   and sandbox endpoints, tests.
2. Frontend: proxy routes for sandbox endpoints, billing client, paywall
   panel, gate on send / face select / editor / export, resume after Checkout,
   "Manage subscription" in the account menu.
3. Demo gallery and replay; generate and commit the demo parts.
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
