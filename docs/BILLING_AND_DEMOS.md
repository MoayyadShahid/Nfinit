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

Six example builds, served as static files from `frontend/public/demos/`
(27 MB; the studio downloads only the versions a visitor opens):

| Demo | Versions |
| --- | --- |
| 5-inch FPV drone frame (first for free users) | bottom plate → motor mounts → stack, standoff and strap holes → arm weight relief → standoffs and top plate → camera cage → motors and camera |
| Robot gripper | base plate → micro servo → spur gears → cranks and idler links → fingers |
| Miniature glider | fuselage → main wing → horizontal stabilizer → vertical fin → nose pocket and launch hook |
| Model rocket | body tube → nose cone → fin can → launch lug → motor mount and retainer |
| Desk catapult | ladder frame → A-frame uprights → axle and throwing arm → bucket → stop bar → wheels |
| Electronics enclosure | shell → board standoffs → USB-C and button openings → vent slots → lid → screw bosses and lid holes |

**Where they come from.** Each demo is a design file in
`backend/demos/designs/<slug>.cad`: build123d code with comment markers
that split it into steps, each with the request, the reply and the code it
adds (`backend/demos/authored.py` documents the format). The code of a
version is the complete script of steps 1 to N, so every version is a real,
runnable script, and the next version only adds to it. The demos are written
by hand, not recorded agent runs, so `demo.json` says `"source": "example"`
and the studio labels them "Example build". The progress steps in a replay
show the plan and the real build result, without timings.

Each folder has `demo.json` (for every version: the request, the reply,
the trace, the code, the finished GLB and the previews of the features that
version adds) and the GLB files. `index.json` lists the demos in order.

**Replay as a version history.** The replay panel shows a timeline with one
point per version, named after the features it adds. "Build next version"
plays the next version like a live run: the request appears in the chat, the
progress steps play, the new features grow in the viewport (new faces
highlighted), and then the finished part appears. Clicking a point on the
timeline, or a reply in the chat history, shows that version at once; later
turns stay in the chat, dimmed, like the rest of a CAD timeline. "Replay this
version" plays the shown version again, and "Watch again" plays the whole
story from version 1. Replays make no backend calls.

**Who sees what.**

- A free user with nothing open lands in the FPV drone demo.
- Everyone sees "See how it's built" cards under the prompt box on the
  welcome screen, and `/studio?demo=<slug>` opens a demo directly.
- Sending a prompt, selecting a face and exporting open the paywall for free
  users. For subscribers, a prompt builds on the shown version as a new
  project, and export works as for any part.

**Rebuild.** From `backend/` (no model calls, so no key and no cost):

```bash
poetry run python -m demos.build [--only fpv-drone]
```

The script runs every version of each design through the CAD sandbox, writes
the GLBs, the previews and `demo.json`, and removes demo folders that are no
longer listed. A demo with a step that does not build is left out. The tests
in `backend/tests/test_demos.py` check that the shipped code is exactly the
design's code for each version and that every version builds on the one
before it.

**Next: version history for projects.** Projects should get the same
behaviour: each assistant turn in a project's chat is a revision, and
clicking it opens that revision. `ChatPane` already takes a `versions` prop
for this, and the studio already loads revisions (`loadRevision`), so the
remaining work is to map each assistant message to its revision number.

## Build order

1. Backend: subscriptions table, billing routes, webhook, `402` gate on runs
   and sandbox endpoints, tests.
2. Frontend: proxy routes for sandbox endpoints, billing client, paywall
   panel, gate on send / face select / editor / export, resume after Checkout,
   "Manage subscription" in the account menu.
3. Demo gallery and replay; build and commit the demo parts (done).
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
