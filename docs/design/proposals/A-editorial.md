# A — Editorial Workshop

## 1. Concept: "The Parts Catalogue"
**Thesis:** nfinit reads like a printed catalogue of useful objects. Each part is shown as a numbered *plate*: a still-life on paper, captioned with the sentence that made it. The prompt is the headline and the object is the photograph.

## 2. What to steal

**Research note:** WebFetch was blocked by the egress proxy for suzanne3d.com, teenage.engineering, arc.net, thebrowser.company, family.co, aesop.com and nothing.tech. moidshahid.com did not resolve in DNS. I could not look at any of them. The techniques below come from my general knowledge of these brands, not from a fresh visit, so check them before relying on them.

| Source | Technique to steal |
|---|---|
| **Teenage Engineering** | Products are shown on flat colour with no staging, and each has a tiny mono spec caption (model no., mass, dims). We do the same: every render gets a mono spec line such as `PETG · 14 g · 0:42`. |
| **Aesop** | Warm paper and ink, *very* slow pacing, and product still-lifes with one hard light source. Copy is a single serif line per screen. We borrow the pacing: one idea per viewport. |
| **Kinfolk / Cereal** | Big margins, captions set apart in a narrow side column, numbered features ("No. 01"), and thin rules between sections. We borrow the side-column caption and the numbering. |
| **Arc / The Browser Company** | A serif display face used with *wit*: italic on the one emotional word of a headline. Our rule is exactly one italic word per headline. |
| **Family (family.co)** | Small, springy, physical micro-interactions on a restrained page. Only our buttons and plates get this bounce. |
| **Printed engineering drawings** | Dimension lines become the page's section rules. |

**Suzanne:** search results show suzanne3d.com titled *"Physical AI for industrial design teams"* and suzanne3d.studio titled *"Turn any idea into a 3D model in minutes."* That is an enterprise, industrial-design pitch. **We beat it on:**
1. We speak to makers holding a printer, not to design teams.
2. We show *print facts* (grams, hours, material) instead of "production-ready" claims.
3. We treat the prompt itself as a beautiful artefact.
4. We have an actual point of view: paper, ink and one filament colour, not a generic dark 3D tool page.

## 3. Colour system
Porcelain is the hero theme. Midnight is the same page printed on black card, not a blue-grey SaaS dark.

| Token | Porcelain | Midnight | Use |
|---|---|---|---|
| `--paper` (bg) | `#F4F1EA` | `#0F0E0C` | page |
| `--sheet` (surface) | `#FBF9F4` | `#181714` | plates, popovers, auth card |
| `--inset` | `#ECE7DC` | `#0A0908` | wells, code, input bg |
| `--ink` (primary) | `#191815` | `#EDE8DE` | text, primary buttons, rules |
| `--ink-2` | `#4A463E` | `#B6B0A4` | secondary text, captions |
| `--muted` | `#7A746A` | `#7F796E` | meta, disabled |
| `--hairline` | `rgba(25,24,21,.14)` | `rgba(237,232,222,.13)` | all rules and borders |
| `--kraft` (secondary) | `#D8CCB4` | `#2E2A22` | plate backdrops, selected chips, revision-strip active |
| `--vermilion` (accent) | `#E2462A` | `#FF6B47` | selected face, focus ring, 1 mark per screen |
| `--vermilion-text` | `#B8361C` | `#FF8566` | accent used *as text* (AA contrast) |
| `--danger` | `#A3261B` | `#FF7A6E` | errors only |

- **Primary = Ink.** Every primary CTA is ink on paper. **Secondary = Kraft**, the brown of cardboard and packing paper, used for surfaces that need to be "picked up". **Accent = Vermilion**, named after a real filament colour ("Signal Vermilion PLA").
- Vermilion covers **≤3% of any viewport**. It is only allowed on:
  - the selected face in a render
  - the wordmark's nozzle square
  - focus rings
  - the extrusion motion (§8)
  - primary-button hover fill
- Contrast: `#E2462A` on `#F4F1EA` is about 4.4:1, which is fine for UI marks and large text. Small text uses `--vermilion-text` (about 5.2:1).
- **Render swatches** apply only to part renders, never to UI: Vermilion, Graphite `#2B2A28`, Bone `#E6DECF`, Sage `#8A987A`, Cobalt `#2F4FA8`. Each plate uses one filament colour.
- Midnight's `--page-bg` moves from `#08090b` (cool) to `#0F0E0C` (warm), so both themes feel like the same paper stock. Delete `--ambient-glow` entirely.

## 4. Type system
- **Serif display:** **Newsreader** (Google, variable wght 200–800, `opsz` 6–72, true italics). It has more editorial character than Instrument Serif, which every AI startup now uses. Load it with `next/font/google`, `style: ['normal','italic']`, `axes: ['opsz']`, variable `--font-serif`.
- **Sans:** keep **Geist** (`--font-sans`) so the studio app stays continuous.
- **Mono / label:** keep **Geist Mono** (`--font-mono`).

| Role | Font | Desktop / Mobile | Wt | LH | Tracking |
|---|---|---|---|---|---|
| Display | Newsreader | 112 / 54px | 380 | 0.92 | -0.035em |
| H1 | Newsreader | 72 / 42px | 400 | 0.98 | -0.03em |
| H2 | Newsreader | 48 / 34px | 400 | 1.02 | -0.02em |
| Pull-quote (prompts) | Newsreader *italic* | 40 / 27px | 300 | 1.12 | -0.015em |
| H3 | Newsreader | 28 / 23px | 450 | 1.12 | -0.01em |
| H4 | Geist | 17 / 16px | 600 | 1.3 | -0.01em |
| Body L | Geist | 18 / 17px | 400 | 1.55 | -0.005em |
| Body | Geist | 15 / 15px | 400 | 1.55 | 0 |
| Caption | Geist | 13 / 12px | 400 | 1.45 | 0 (ink-2) |
| Label | Geist Mono | 11 / 11px | 500 | 1.2 | +0.08em, UPPERCASE |
| Spec | Geist Mono | 12 / 11px | 400 | 1.4 | 0, tabular-nums |

**Rules**
- **Serif:** H1–H3, pull-quotes, the wordmark, and anything a *human would say* (the prompts).
- **Sans:** anything the *interface* says (buttons, body, form UI). H4 and smaller is always sans.
- **Mono:** anything a *machine measures* (mm, g, time, file types, section numbers `No. 01`).
- One italic word per headline, never more. Never bold the serif above 500.
- Headlines are left-aligned. Centred text is only allowed on the auth card.

## 5. Spacing, radius, borders, shadows, buttons
- **Spacing:** 4px base. Scale `4 8 12 16 24 32 48 72 112 160`.
  - Section padding is 160 desktop / 96 mobile.
  - The page uses a 12-col grid, max 1280, 32px gutter (20px on mobile).
  - Asymmetric layout: the headline takes cols 1–8 and the caption column takes cols 10–12, as in magazine layouts.
- **Radius:**
  - `0` for plates, images and rules (paper doesn't round)
  - `3px` for buttons and inputs (letterpress-crisp)
  - `8px` for popovers and the auth card
  - `999px` only for 6px status dots
  - No 22px "app window" rounding.
- **Borders:** 1px `--hairline` everywhere. Section dividers are *dimension rules*: a hairline with 5px end ticks and a centred mono label (`— 160 mm —`).
- **Shadows:** none on UI. The only shadow is the soft cast shadow baked into each render. Popovers use `0 1px 0 var(--hairline), 0 16px 40px -16px rgba(25,24,21,.22)`.
- **Buttons** (Geist 500, 15px, height 48 or 40 small, x-padding 22, radius 3):
  - *Primary:* `--ink` bg, `--paper` text, trailing typographic `→`. On hover, the bg becomes `--vermilion`, the text stays paper, and the arrow moves 3px right. Active: translateY(1px).
  - *Secondary:* transparent, 1px `--ink` border. On hover, the bg becomes `--inset`.
  - *Ghost:* text only in `--ink-2`. On hover, `--ink` plus an underline.
  - Focus is always `outline: 2px solid var(--vermilion); outline-offset: 3px`.
- **Links:** `--ink`, underline 1px `--hairline` color, `text-underline-offset: 4px`. On hover, the underline turns vermilion at 1.5px.
- **Wordmark:** replaces the sparkle logo. It is `nfinit` in Newsreader italic 400, lowercase, followed by a 6×6px vermilion square (the "nozzle"). No icon tile.

## 6. Landing page (≈95 visible words)

```
┌──────────────────────────────────────────────────────────────┐
│ nfinit■        No.01 Describe  02 Refine  03 Print   Log in ◐ │  masthead, 64px, hairline below
├──────────────────────────────────────────────────────────────┤
│                                                              │
│ Describe a part.                        ┌──────────────────┐ │
│ Hold it by *tonight.*                   │  [still-life:    │ │  Display serif, cols 1–7
│                                         │  bracket on      │ │  plate cols 8–12, bleeds right
│ [Start a part →]  Log in                │  kraft, 1 light] │ │
│                                         └──────────────────┘ │
│                                 PLATE 01 · SHELF BRACKET     │
│                                 PETG · 80×48×6 MM · 1H 12M   │  mono caption
├──|──────────────────── — 01 — ───────────────────────────|───┤  dimension rule
│ No.01  Describe                                              │
│                                                              │
│   "A wall hook for my helmet.                                │  pull-quote, italic serif,
│    Two screws, no overhangs."                                │  typed on scroll-in
│                                         [hook render, bone]  │
├──|──────────────────── — 02 — ───────────────────────────|───┤
│ No.02  Refine                                                │
│  [render: one face in vermilion]   ← FACE 7 · +12 MM         │  leader line to mono tag
│  ▢ v1  ▢ v2  ▢ v3  ▣ v4                                      │  contact-sheet revision strip
├──|──────────────────── — 03 — ───────────────────────────|───┤
│ No.03  Print                                                 │
│  [photo: printed part in hand / on PEI bed]                  │  the ONLY photograph
│  STL   STEP                                                  │  mono chips
├──────────────────────────────────────────────────────────────┤
│ The catalogue                                                │  H2
│ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐                    │  6 plates, 3×2 / 2×3 mobile
│ │hook│ │clip│ │box │ │adpt│ │hnge│ │knob│                    │
│ └────┘ └────┘ └────┘ └────┘ └────┘ └────┘                    │
│ Cable clip  Pi case  32→25 mm  Lid hinge  M6 knob  Hook      │  caption, Geist 13
├──────────────────────────────────────────────────────────────┤
│ Make the next *thing.*                 [Start a part →]      │  H1 colophon
│ nfinit · Terms · Privacy                         © 2026      │  mono 11
└──────────────────────────────────────────────────────────────┘
```

**Exact copy**
- **Masthead:** `No. 01 Describe` · `02 Refine` · `03 Print` · `Log in`
- **Hero:** "Describe a part. Hold it by *tonight.*"
  - CTAs: **Start a part →** · Log in
  - Caption: `PLATE 01 · SHELF BRACKET` / `PETG · 80 × 48 × 6 MM · 1H 12M`
- **01 Describe:**
  - Pull-quote: "A wall hook for my helmet. Two screws, no overhangs."
  - Side caption: *Plain words in. Parametric CAD out.*
- **02 Refine:**
  - Tag: `FACE 7 · +12 MM`
  - Side caption: *Click a face. Say what changes.*
  - Revision strip: `v1 v2 v3 v4`
- **03 Print:**
  - Side caption: *Export and slice.*
  - Chips: `STL` `STEP`
- **Catalogue:** H2 "The catalogue". Captions:
  - "Cable clip"
  - "Pi 5 case"
  - "32 → 25 mm adapter"
  - "Lid hinge"
  - "M6 knob"
  - "Helmet hook"
  - Hovering a plate reveals its prompt in italic serif: max 8 words, ≤6 prompts shown at once.
- **Colophon:** "Make the next *thing.*" **Start a part →**
- **Footer:** `nfinit · Terms · Privacy · © 2026`

**Visual assets:** 7 renders exported from the real nfinit viewer, all shot the same way:
- 35° three-quarter view, one key light from top-left, matte material, rendered on `--kraft`
- 1 real photograph (§03), taken by the founder
- No fake app window, no floating glass cards. The product UI appears only as a cropped face-selection detail in §02.

## 7. Auth page (`/login`)
- **Desktop layout:** split 7/5.
  - Left: a full-bleed plate (the catalogue render changes on each visit, chosen from 6) on `--kraft`, with a mono caption at the bottom left: `PLATE 04 · LID HINGE · PLA · 0H 38M`.
  - Right: `--paper` with the content vertically centred, max-width 360, left-aligned.
- **Mobile:** the plate becomes a 180px strip at the top and the content sits below it.
- **Copy**
  - Wordmark `nfinit■` at top left.
  - H1 (Newsreader 48/36): "Back to the *bench.*"
  - Caption: *Your parts and revisions are where you left them.*
  - [**Continue with Google**] (primary ink, official multicolour G glyph as SVG, not the letter "G")
  - [**Continue with GitHub**] (secondary outline, lucide `Github`)
  - Caption, muted: "New here? Same buttons."
  - Footer, mono 11: `BY CONTINUING YOU ACCEPT THE TERMS AND PRIVACY POLICY.` (with real links)
- **Loading:** both buttons are disabled. The clicked one reads "Opening Google…". A 2px vermilion *extrusion line* runs along the bottom edge of that button, looping 1.2s, instead of a spinner. The other button fades to 40%.
- **Error** (query `?error` or client error): an inline block above the buttons, `--inset` bg, 2px `--danger` left rule, Geist 13: **"Sign-in didn't go through."** Try again, or use the other provider. Raw provider messages go in a `<details>` labelled `Details`. `role="alert"`, and focus moves to the block.

## 8. Motion
Tokens:
- `--ease-out: cubic-bezier(.2,.7,.1,1)`
- `--ease-draw: cubic-bezier(.65,0,.35,1)`
- `--spring` (Family-style), buttons only: `cubic-bezier(.34,1.56,.64,1)`

Motions:
1. **Layer-print reveal (hero + plates).** The render appears as if printed: `clip-path: inset(100% 0 0 0)` → `inset(0)` with `steps(14)` over 900ms, plus a 1px vermilion "nozzle" line riding the top edge that fades out at the end. This is the signature motion. It runs once per plate, triggered at 30% in view.
2. **Extrusion rules.** Dimension rules draw left→right, `scaleX 0→1`, 700ms `--ease-draw`, with the end ticks popping in at 80%.
3. **Typed prompt.** The §01 pull-quote types at 24ms/char with a vermilion caret. The side caption fades in 300ms after the last character.
4. **Plate hover.** The image moves up 4px and the caption swaps to the italic prompt (opacity/translateY 6px, 220ms `--ease-out`).
5. **Button press.** Arrow +3px (160ms `--spring`), active 1px down. The theme toggle cross-fades colour tokens over 240ms.

**Reduced motion:** every motion becomes a 150ms opacity fade. Typed text appears whole. The extrusion loader becomes a static 2px vermilion bar with the button label, and no loops run.

## 9. Don'ts
- No violet, no gradient glows, no radial "ambient" blobs, no sparkle icons, no ✨, no "AI-powered" pill badges.
- No glassmorphism or backdrop-blur cards. Paper doesn't blur.
- No fake app window with traffic-light dots.
- No centred hero stack (eyebrow, H1, sub, two buttons, screenshot).
- No bento grids, no icon-in-rounded-square feature cards, no three-column "features" row.
- No stock 3D blobs or abstract meshes. Only parts a maker would actually print, with real dimensions.
- No more than one italic word per headline. No serif in buttons. No emoji.
- Never use vermilion for body text or large fills, and never more than one vermilion mark group per viewport.
- No testimonials, logo walls or pricing tables on the landing page.
- No "production-ready", "revolutionize", "unleash" or "seamless".

## 10. Strongest 3 ideas
1. **The prompt is the headline, the part is the plate.** User prompts are set as italic Newsreader pull-quotes over catalogue-style still-life renders with mono spec captions (material · mm · print time). It is editorial, it's specific to makers, and it explains "describe → print" without paragraphs.
2. **The layer-print reveal plus extrusion rules** as the whole motion language: renders build up in `steps()` like a print, a vermilion nozzle line rides the edge, and section rules draw like extruded lines and double as engineering dimension lines. The same "extrusion line" replaces spinners on the OAuth buttons.
3. **Ink / Kraft / Signal Vermilion** palette with strict type rules: ink as primary, kraft as secondary, and one filament-derived accent kept to ≤3% of any screen. Serif is for what humans say, sans for what the UI says, mono for what machines measure. That rule makes the system easy to apply everywhere from the landing page to the studio app.
