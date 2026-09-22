# C — Precision Sketch

## 1. Concept
**"The drawing sheet."** The whole site is one A-size drafting sheet: a pencil-blue construction sketch that gets redlined with dimensions, turns solid, and slices into print layers as you scroll. It ends in a title block you "sign". The drafting table is warm, not a factory: red pencil, blue pencil, a serif, and exact millimetres.

## 2. What to steal / what to beat
**Research note:** the egress proxy blocked every direct fetch (suzanne3d.com, rauno.me, nothing.tech, shapr3d.com, linear.app, HN). moidshahid.com failed DNS resolution. Web search did work. The points below come from search snippets and my own memory of these sites. I did not re-check any of them this session.

| Source | Technique to steal | How nfinit uses it |
|---|---|---|
| **Vercel** | Layout grid drawn on the page, with `+` crosshair marks where lines cross | Becomes a **drawing-sheet border with zone labels** (A–D down the side, 1–6 across the top, in mono). This is the only chrome. |
| **Nothing** | Monochrome page, one red used as a signal, all-caps mono labels | Redline is the only accent. It never fills more than a stroke or a small chip. |
| **Stripe Press** | Serif-led pages where the product sits like a physical object on paper | The part sits on "paper" (porcelain) with a soft contact shadow. No app-window chrome. |
| **Linear** | One short sentence per section; 1px hairlines instead of cards | No cards on the landing page at all. Sections are separated by dimension-style rules. |
| **Rauno Freiberg** | One small, precise delight on each interactive element | Crop marks draw in at a button's corners on hover (§8). |
| **Shapr3D / Onshape** (anti-reference) | Avoid: feature grids, "trusted by" logo bars, navy gradients, UI screenshots, "engineering-grade" copy | None of these appear. |

**Suzanne** (from search results) positions itself as *"Physical AI for industrial design teams"* / *"for product design"*: prompt, photo or sketch → STEP/STL/3MF. They are moving toward teams and industry. **We beat them by being specific and personal.** We show one real part with real millimetres (a hook for a 25 mm pipe, two M4 screws), speak to one maker at one printer, and show the edit loop instead of stating it. They sell "AI for design teams". We show *your* part, drawn in front of you.

## 3. Color system
Roles:
- **Primary = Ink.** Text, primary buttons, solid geometry.
- **Secondary = Construct**, a non-photo-blue pencil colour. Used only for construction lines, grid and sketch strokes, at 1px and 35–60% opacity.
- **Accent = Redline.** Used only for dimensions, the selected face, focus ring, error revision-clouds and the logo's centre mark.

| Token | Porcelain | Midnight |
|---|---|---|
| `--page-bg` (paper) | `#F4F1EA` | `#0D0D0C` (warm carbon, not pure black) |
| `--surface-solid` | `#FBF9F4` | `#151513` |
| `--inset-bg` | `#ECE7DC` | `#090908` |
| `--ink` / primary | `#191815` | `#EEEAE1` |
| `--ink-fg` (on primary) | `#FBF9F4` | `#0D0D0C` |
| `--muted` | `#6B655A` (5.1:1) | `#9A958A` (6.5:1) |
| `--faint` (non-text only) | `#A39C8E` | `#5E5A52` |
| `--hairline` | `rgba(25,24,21,.12)` | `rgba(238,234,225,.10)` |
| `--grid` | `rgba(25,24,21,.055)` | `rgba(238,234,225,.045)` |
| `--construct` (secondary) | `#7FA7C9` | `#6E9CC4` |
| `--redline` (accent stroke) | `#E0452B` | `#FF5B3A` |
| `--redline-text` | `#C23A22` (4.75:1) | `#FF5B3A` (6.3:1) |
| `--redline-wash` | `rgba(224,69,43,.10)` | `rgba(255,91,58,.14)` |

Rules:
1. Redline covers at most about 2% of any viewport. It is never a background fill larger than a face highlight.
2. Construct is never used for text. It is pencil, not UI.
3. Delete `--ambient-glow` and every violet value (including `--accent: #e6e0f0` and the violet `--ring`). Set `--ring: var(--redline)`.
4. Midnight should read as carbon paper: warm neutrals only, no blue-black.

## 4. Type system
- **Display serif:** **Newsreader** (Google, variable `opsz` 6–72, has italics). Set it at `opsz 72`, where it is sharp and high-contrast. I chose it over Instrument Serif because Instrument has become the default "AI startup serif".
- **Sans:** keep **Geist** (already loaded) for UI and body text.
- **Mono:** **IBM Plex Mono** (Google) for dimensions, labels and file names, with `font-variant-numeric: tabular-nums slashed-zero`. Its slab serifs look like a drafting stencil. Geist Mono is the fallback if we want one fewer font.

| Role | Font | Desktop / Mobile | Wt | LH | Tracking |
|---|---|---|---|---|---|
| Display (hero) | Newsreader opsz72 | 88 / 48 px | 400 | 0.95 | −0.035em |
| H1 | Newsreader | 64 / 40 | 400 | 1.0 | −0.03em |
| H2 | Newsreader | 44 / 32 | 400 | 1.05 | −0.025em |
| H3 | Geist | 22 / 19 | 500 | 1.25 | −0.015em |
| H4 | Geist | 16 / 16 | 600 | 1.35 | −0.01em |
| Body L | Geist | 18 / 17 | 400 | 1.55 | −0.005em |
| Body | Geist | 15 / 15 | 400 | 1.55 | 0 |
| Caption | Geist | 13 / 13 | 400 | 1.45 | 0 |
| Label | Plex Mono | 11 / 11 | 500 | 1.2 | +0.08em, UPPERCASE |
| Dimension | Plex Mono | 13 / 12 | 500 | 1 | 0, tabular |

Rules:
- Serif is for **headlines only** (Display, H1, H2). Never set buttons, nav or anything under 28px in the serif.
- **Serif italic is the "hand" voice.** It marks one emphasised phrase per headline and the handwritten-style margin notes on the drawing ("this face").
- Mono is only for values the machine owns: millimetres, file names, zone labels, revision letters.
- Sans is everything else.

## 5. Spacing, shape, controls
- **Spacing:** 4px base. Scale: 4, 8, 12, 16, 24, 32, 48, 64, 96, 160. Section rhythm is 160 on desktop and 96 on mobile. Side gutter is 16 on mobile, 32 on desktop. Max width is 1200, with an 8-column grid kept invisible except for the sheet border.
- **Radius:** 0 for the sheet and drawings, 6px for buttons and inputs, 10px for popovers, full for chips. No 22px "app window" rounding.
- **Borders:** 1px `--hairline` everywhere. Section dividers are drawn as a dimension line: a hairline with tick ends and a mono label in a gap in the middle (`— 02 REFINE —`).
- **Shadows:** none on UI. The part gets one contact shadow: porcelain `0 30px 40px -28px rgba(70,50,30,.28)`, midnight `0 30px 40px -28px rgba(0,0,0,.7)`.
- **Buttons** (height 44, padding-x 18, Geist 14/500):
  - *Primary:* `--ink` background, `--ink-fg` text, trailing mono `→`. On hover, four 6px L-shaped crop marks in redline draw in 3px outside the corners, and the arrow moves 2px right.
  - *Secondary:* transparent background, 1px `--hairline` border, ink text. On hover the border becomes `--ink` at 40%.
  - *Ghost:* no box; mono label plus `↓` or `→`, muted colour, ink on hover.
  - *Focus* (all buttons): 1.5px redline outline, offset 3px.
- **Links:** ink text with a 1px hairline underline at offset 4px. On hover a redline underline draws left to right (scaleX, 220ms).
- **Logo:** remove the sparkle. The wordmark is **nfinit** in Newsreader 500, followed by a 10px redline **centre mark** (⌖, the drafting symbol for a hole centre).

## 6. Landing page
The page is one sticky SVG drawing: the pipe hook, which is the same part in every section. It sits in the right 60% of the viewport, and each step changes its state.

```
┌A──────────────1──────────2──────────3──────────4─────────────┐  ← sheet border + zone labels (mono, --faint)
│ nfinit⌖                                   Log in  [Start a part →] │
│                                                                    │
│  Parts, from               ┆ ╌╌╌ construct-blue sketch of hook ╌╌╌ │
│  *a sentence.*             ┆      ├──── 42.0 ────┤   (redline dims) │
│                            ┆   ⌀25 ◯      ┌─┐                      │
│  Describe it. Edit it.     ┆              │ │ ← 6.0                │
│  Print it.                 ┆  ╭ "a hook for a 25 mm pipe,           │
│  [Start a part →] See it drawn ↓           two M4 screws" (callout) │
B──────────────────── — 01 DESCRIBE — ───────────────────────────────┤
│  Say what it holds.        │  prompt callout types in; the sketch   │
│                            │  resolves into clean geometry         │
├──────────────────── — 02 REFINE — ─────────────────────────────────┤
│  Click a face.             │  one face washes redline; margin note │
│  *Change your mind.*       │  *"thicker here"* → dim 6.0 → 9.0     │
│                            │  REV A → REV B stamp                  │
├──────────────────── — 03 PRINT — ──────────────────────────────────┤
│  Print it tonight.         │  solid slices into 0.2 mm layer lines  │
│  STL · STEP                │  hook_revB.stl   184 KB                │
├──────────────────── — SHEET 2: OTHER PARTS — ──────────────────────┤
│  4 line-drawings in a row, each 1 mono label only:                 │
│  GOPRO MOUNT · PEGBOARD HOOK · 40→60 FAN DUCT · 2-PC HINGE          │
├────────────────────────────────────────────────────────────────────┤
│                        ┌──────────── TITLE BLOCK ─────────────┐    │
│  Your next part,       │ PART   ______________  REV A         │    │
│  *rev A.*              │ DRAWN  you             SCALE 1:1     │    │
│                        │ UNITS  mm              SHEET 1/1     │    │
│                        │ [Start a part — free →]              │    │
│                        └──────────────────────────────────────┘    │
D  © 2026 nfinit · Terms · Privacy                                    │
└────────────────────────────────────────────────────────────────────┘
```

**Exact copy** (about 75 words): Nav: "Log in", "Start a part". Hero: "Parts, from *a sentence.*" / "Describe it. Edit it. Print it." / "Start a part", "See it drawn". Callout: "a hook for a 25 mm pipe, two M4 screws". Section labels: "01 Describe", "02 Refine", "03 Print". Section headlines: "Say what it holds." / "Click a face. *Change your mind.*" plus the note *"thicker here"* / "Print it tonight." plus "STL · STEP", "hook_revB.stl 184 KB". Gallery labels: "GoPro mount", "Pegboard hook", "40→60 fan duct", "2-pc hinge". Closing: "Your next part, *rev A.*", with title-block fields PART / DRAWN / you / UNITS / mm / SCALE 1:1 / SHEET 1/1 / REV A, and the button "Start a part — free". Footer: "Terms", "Privacy".

**Mobile:** the drawing stops being sticky. Each section stacks as headline, then a 4:3 drawing, then its label. The sheet border shrinks to the zone ticks only.

## 7. Auth page
A two-column sheet. The left 55% shows the finished hook drawing with its title block. The right 45% holds the form, centred, max 360px wide. On mobile the drawing becomes a 140px strip at the top.

```
│  [hook drawing, dims]          │  nfinit⌖                         │
│                                │  Sign the drawing.               │
│  ┌ TITLE BLOCK ────────────┐   │  Your parts and revisions, saved.│
│  │ DRAWN  ____________ ◄───┼── blank line waits for the user      │
│  └─────────────────────────┘   │  [G  Continue with Google     ]  │
│                                │  [⌥  Continue with GitHub     ]  │
│                                │  By continuing you accept Terms. │
```

- **Copy:** H1 (Newsreader, 44px) "Sign the drawing." Subline "Your parts and revisions, saved." Buttons "Continue with Google" / "Continue with GitHub", both secondary style at full width with brand glyphs in monochrome. Fine print "By continuing you accept the Terms."
- **Loading:** only the pressed button changes. Its label becomes "Opening Google…" (or "Opening GitHub…") in muted text. A redline dimension line (tick, line, tick) grows across the button's bottom edge on a 1.2s loop. The other button drops to 40% opacity with `aria-busy`. On the left, the pencil cursor starts writing on the DRAWN line.
- **Error:** a redline **revision cloud** (scalloped outline, drawn over 400ms) surrounds both buttons. Above them a mono line reads `ERR · Sign-in didn't finish. Try again.` (`role="alert"`). The title block's REV letter changes to "A′". The error clears on the next click.
- **Success** (if a frame renders before redirect): the user's first name is set in Newsreader italic on the DRAWN line.

## 8. Motion
All motion uses one easing curve, `--ease-draft: cubic-bezier(.2,.7,.2,1)`.

1. **Draw-on.** Construction strokes animate `stroke-dashoffset` over 700ms, staggered 35ms apart. Redline dimensions follow 200ms later. Arrowheads scale from 0 to 1 over 120ms. This plays on hero load and on each section's first entry.
2. **Dimension scrub** (Refine). The face wash fades in over 180ms. The value counts 6.0 → 9.0 over 520ms with tabular figures while the extension lines slide. After that, a REV stamp rotates from −8° to −4° and scales from 1.15 to 1 over 240ms (spring feel, no overshoot above 1.02).
3. **Sketch → solid → layers.** This is scroll-linked with CSS `animation-timeline: view()`, with an IntersectionObserver fallback. The hatch fills in (45° section hatching), then shading, then 0.2 mm layer lines sweep bottom to top as a thin nozzle dot moves across.
4. **Crop-mark hover.** On primary buttons, four corners draw in over 160ms and retract over 120ms.
5. **Zone tracker.** The sheet-border zone label for the current section (A–D) turns ink, then redline, over 200ms. This doubles as the scroll-progress indicator.

**Reduced motion:** every drawing renders in its final, fully dimensioned state. Nothing is pinned or scroll-linked. The three steps become a static three-panel strip. Value changes appear as "6.0 → 9.0" text. Crop marks appear without animation. Loading uses a static dashed underline plus the "Opening…" label.

## 9. Don'ts
- No violet, no gradients, no glow blobs, no sparkles, no glassmorphism, no `backdrop-blur` cards.
- No "AI-powered" pill, no "✨ Introducing", no emoji.
- No fake app-window chrome with traffic lights. The drawing is the product shot.
- No feature-card grids, logo walls, testimonial carousels, or stat counters ("10x faster").
- No blueprint-blue full backgrounds. That is the industrial cliché; construct blue stays pencil-thin.
- No serif under 28px, no mono in paragraphs, no more than one italic phrase per headline.
- No realistic 3D render in the hero. Line art first; the solid is earned by scrolling.
- Never round the sheet. Never put redline on more than about 2% of the screen.

## 10. Strongest 3 ideas (harvest these)
1. **The page is a drawing sheet.** A sheet border with A–D / 1–6 zone labels serves as the only chrome and as the scroll-progress indicator. The final CTA is a real **title block** ("Your next part, *rev A.*", DRAWN: you), and the auth page asks you to "**Sign the drawing**".
2. **A three-pencil colour system:** ink (primary), non-photo "construct" blue (secondary, sketch strokes only) and **redline** (the single accent, only for dimensions, selection, focus and errors), all on warm paper and carbon backgrounds. This uses real drafting tradition, so it feels warm and handmade, not industrial or generic-AI.
3. **One part tells the whole story:** the same 25 mm pipe hook is sketched, dimensioned, redlined ("thicker here", 6.0 → 9.0, REV A → B) and sliced into 0.2 mm layers as you scroll. It uses real millimetres in IBM Plex Mono, serif-italic margin notes, and error states drawn as **revision clouds**.
