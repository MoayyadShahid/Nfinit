# nfinit design spec: landing and auth

**Status:** proposed · **Scope:** `/` (landing) and `/login` (OAuth) · **Supersedes:** the violet-glow landing from #17 and the centred login from #19

The studio keeps working as it does. It picks up the new tokens, wordmark and
fonts, with no layout changes.

---

## 1. The idea in one line

**"The Workbench."** Every screen shows one real, printable part, captioned
with the sentence that made it and the facts a maker cares about (millimetres,
material, print time). The part *prints itself in*, layer by layer. The words
are few and the object carries the page.

> The audience is a hobbyist with a printer on their desk, not an industrial
> design team. Suzanne pitches itself as "your team's industrial design engine"
> and gates everything behind "Book a demo". We win by being personal, specific and print-first: *your* part, on
> *your* bed, tonight.

### How this spec was made

Five agents each argued for a different direction (full proposals in
[`proposals/`](./proposals)). This spec takes the strongest idea from each:

| Proposal | Direction | What we kept |
|---|---|---|
| A — Editorial Workshop | Serif catalogue on paper | The **serif / sans / mono** rule, the prompt set as an italic pull-quote, parts as numbered **plates**, dimension-line section dividers |
| B — Playful Maker | Filament-orange, chunky, fun | The tactile **key press** on buttons, **spool-label stickers** (capped), "New here? Same buttons." |
| C — Precision Sketch | Friendly technical drawing | **Construct blue** as the secondary colour (sketch lines only), **one part tells the whole story**, the dimension value that counts up (6.0 → 9.0) |
| D — Tactile Objects | The printed object as hero | **Prompt as caption**, the cheap-render performance budget, the **closing prompt field that survives OAuth** |
| E — Midnight Luxe | Dark, Didone, glowing accent | **The Missing Dot** brand mark, **accent as light, never paint**, the prompt bar as the hero control, film grain in midnight only |

What we rejected, and why:
- **Bodoni Moda** (E): it breaks below 26px, and a fashion Didone reads as luxury retail, not maker.
- **Signal yellow** (B): a fourth colour made the palette noisy.
- **The drawing-sheet border with A–D zone labels** (C): it's charming but busy, and it fights "clean".
- **A live r3f scene in the hero** (D): phase 2 at most.

### Reference sites (seen 22 Sep 2026)

**suzanne3d.com, /product, suzanne3d.studio** (the last is a mirror of the home page):
- **Layout:** a near-neutral black page (`#0D0D0D`) with a faint dot grid. The hero is a left-aligned serif H1 with a 40-word Inter paragraph under it and a white pill `Book a demo` (it has a tiny grey dot inside) next to an outlined `Log in`. The right side holds grey pencil sketches of a chair, a robot arm and a speaker, captioned `FIG. 14 - WOMB CHAIR` in spaced mono.
- **Type:** **Newsreader 500** headlines (44–72px), with the emotional words set in *italic and tinted gold*. Inter for body, mono for labels.
- **Copy:** long. Most sections are an H2 plus 30–60 words, the audience is "industrial designers", and "AI" appears in the first sentence.
- **Flow:** told in text. There are four numbered cards (Generate, Refine, Validate, Build), a node diagram and a scripted chat mock. You never see a part go from sentence to object, and the only call to action is a gated demo booking.
- **Strong:** confident serif, restrained colour, the sketch plus figure-label idea, and a clear export story (STEP, STL, 3MF).
- **Weak:** walls of text, no way to try anything, lots of empty scroll between reveals, and a mood that is sober and corporate rather than fun.

**moayyadshahid.com** (the founder):
- **Layout:** a single 620px column on `#F7F7F4` paper, with an 18px Newsreader body and a Newsreader italic 350 name as the H1. Links are underlined in a dark red.
- **Copy:** very short, with generous white space.
- **Strong:** calm, personal and quiet.
- **Weak:** no imagery, colour or motion, so nothing is memorable. It's the "too plain" end of our range.

**What this changed in the spec:**
1. **Serif: Newsreader → Fraunces** (§3). It was already our named fallback. Suzanne uses Newsreader with italic accent words, so the same face and the same device would read as a clone. Fraunces (`SOFT 50`, `WONK 0`) is warmer and friendlier, which suits hobbyists. Our italic word stays **ink**, never tinted.
2. **Midnight warmed** (§2). `#0E0D0B` was indistinguishable from Suzanne's `#0D0D0D`, so paper, sheet and inset move a step warmer and lighter.
3. **New don'ts** (§10): no dot-grid background, no grey pencil sketches (ours are construct blue), no `FIG.` label without a print spec next to it, no tinted italics.

**What we take:** the serif-plus-mono pairing, restraint in colour, and captions on drawings. From the founder's site we take short copy and the always-underlined link.

**What we beat:**
- A prompt you can type into, above the fold, against their "Book a demo".
- One part shown going through the flow, against four text cards.
- Specs a maker cares about (material, layer height, minutes) instead of "physical intelligence".
- About 95 words on the page against their 700+.

---

## 2. Colour system

Three roles, strictly separated:

- **Primary = Ink.** Text, primary buttons, solid geometry.
- **Secondary = Construct blue.** Pencil-thin sketch and wireframe lines only, never text or fills. This second hue stops the palette from reading as the generic "cream plus one orange pop".
- **Accent = Hot PLA.** The nozzle: light, never paint.

**Clay** is the neutral material the parts are rendered in, before they turn into filament colour.

| Token | Porcelain | Midnight | Role |
|---|---|---|---|
| `--paper` | `#F4F1EA` | `#13110E` | Page background (midnight is a *warm* black, visibly apart from Suzanne's neutral `#0D0D0D`) |
| `--sheet` | `#FBF9F4` | `#1C1915` | Raised surface: auth panel, popovers, prompt bar |
| `--inset` | `#ECE7DC` | `#0C0A08` | Input wells, plate backdrops |
| `--clay` | `#DDD3C2` | `#2A2621` | Part material in its "solid" state, plate floor, stickers |
| `--ink` **(primary)** | `#191815` | `#EEE9DF` | Text, primary button fill, solid geometry |
| `--ink-2` | `#4A463E` | `#B6B0A4` | Body copy, secondary text |
| `--muted` | `#6B655A` | `#948E83` | Captions, mono labels (AA on paper) |
| `--hairline` | `rgba(25,24,21,.12)` | `rgba(238,233,223,.10)` | Every border and rule |
| `--hairline-strong` | `rgba(25,24,21,.28)` | `rgba(238,233,223,.22)` | Secondary-button border, active rule |
| `--construct` **(secondary)** | `#6F9BC4` | `#7FA7C9` | Sketch strokes, wireframe edges, 1px, 40–70% opacity |
| `--accent` **(Hot PLA)** | `#EE4A0E` | `#FF5B1F` | Brand dot, nozzle line, selected face, focus ring, prompt-submit |
| `--accent-text` | `#B23A0A` | `#FF7A45` | Accent used *as text* (≥4.5:1) |
| `--on-accent` | `#1A0A03` | `#1A0A03` | Text on an accent fill: always dark, never white |
| `--danger` | `#B42318` | `#F2685C` | Errors only |
| `--success` | `#2E7D43` | `#7FD48A` | "Saved" and "Exported" only |

### Theme

**Porcelain (light) is the default everywhere.** The landing and auth pages are
always porcelain and have no theme toggle (founder decision). Visitors choose
midnight inside the studio, and that choice is kept for the studio only.

### Colour rules

1. **The accent covers ≤2% of any viewport.** It may appear only as:
   - the brand dot
   - the nozzle line
   - a selected CAD face
   - the prompt-submit button
   - focus rings
   - a link underline on hover

   It is never a button fill, section background, gradient or body text.
2. **Glow is midnight-only.** In midnight, the dot and the nozzle line get `box-shadow: 0 0 12px 2px rgb(255 91 31 / .5)`. In porcelain the accent stays flat and matte, because glows on cream look dirty.
3. **Construct blue is pencil only:** 1px strokes, never text, never a fill, never a full blueprint background. Blueprint blue is the industrial cliché we are avoiding.
4. **Delete violet everywhere:**
   - `--ambient-glow`
   - the violet `--accent` and `--ring` in porcelain
   - the `violet-*` utility classes on the landing and login pages

   Set `--ring: var(--accent)`.
5. **Render palette.** This applies to part images only, never UI:
   - clay `#DDD3C2` / `#2A2621` (unprinted)
   - Hot PLA `#EE4A0E`
   - graphite `#2B2A28`
   - bone `#E6DECF`

   One filament colour per plate, and at most one orange part per screen.
6. **Midnight grain.** A 3% monochrome SVG noise overlay (`mix-blend-mode: overlay`) is used in midnight only. Porcelain is clean paper. (The landing and auth pages are always porcelain, so this applies to future midnight surfaces only.)

---

## 3. Typography

| Family | Source | Role |
|---|---|---|
| **Fraunces** (variable `opsz` 9–144, wght 100–900, `SOFT` 50, `WONK` 0, true italics) | `next/font/google`, `--font-serif` | Display, H1–H3, the prompt pull-quote, the wordmark |
| **Geist** (already loaded) | `--font-sans` | UI, body, buttons, H4 |
| **Geist Mono** (already loaded) | `--font-mono` | Labels, specs, dimensions, file names |

**Why Fraunces:** proposals B and D chose it, and A and C chose Newsreader. The spec first picked Newsreader, but Suzanne (the direct competitor) sets every headline in Newsreader with italic accent words, so we move to Fraunces. At `SOFT 50` it keeps the precision at display sizes and adds warmth that suits hobbyists, and its italics are true italics. Instrument Serif stays ruled out because it has become the default AI-startup serif.

### Type scale

| Role | Font | Desktop / Mobile | Weight | Line height | Tracking |
|---|---|---|---|---|---|
| Display | Fraunces, `opsz 144` | 112 / 56px | 380 | 0.92 | −0.035em |
| H1 | Fraunces | 72 / 42px | 400 | 0.98 | −0.03em |
| H2 | Fraunces | 48 / 34px | 400 | 1.04 | −0.02em |
| H3 | Fraunces | 30 / 24px | 450 | 1.12 | −0.01em |
| Prompt (pull-quote) | Fraunces *italic* | 32 / 24px | 300 | 1.15 | −0.015em |
| H4 | Geist | 18 / 17px | 600 | 1.3 | −0.01em |
| Body L | Geist | 18 / 17px | 400 | 1.55 | −0.005em |
| Body | Geist | 15 / 15px | 400 | 1.55 | 0 |
| Button | Geist | 15 / 15px | 550 | 1 | −0.01em |
| Caption | Geist | 13 / 12px | 400 | 1.45 | 0 |
| Label | Geist Mono | 11 / 11px | 500 | 1.2 | +0.08em, UPPERCASE |
| Spec | Geist Mono | 12 / 11px | 400 | 1.4 | 0, `tabular-nums` |

### Type rules

- **Serif is for what people say:** headlines and prompts.
- **Sans is for what the interface says:** buttons, body, navigation, forms.
- **Mono is for what the machine measures:** mm, grams, minutes, `.STL`, `V3`.
- **Exactly one italic word per headline,** and it is the emotional one ("Say it. *Hold it.*"). The italic stays `--ink`. It is never tinted gold or accent (that is Suzanne's device).
- The serif is **never below 24px**, never in a button, input or the studio chrome.
- Headlines are **left-aligned.** Centred text is only allowed in the closing CTA.
- Units are uppercase mono with a thin space before them: `80 × 48 × 6 MM`, `38 MIN`, `0.2 MM`.
- No landing-page sentence is longer than **8 words**.

---

## 4. Brand mark: the Missing Dot

"nfinit" is "i**nfinit**e" without its first *i*. The symbol is that *i*'s
missing dot: an **8px Hot PLA circle**, which is also the nozzle tip that
turns a sentence into an object.

- **Lockup:** `● nfinit`. The dot comes first, followed by `nfinit` in Fraunces *italic* 500, lowercase, tracking −0.02em. The dot sits at x-height, a sixth of an em before the `n`.
- **Favicon:** the dot on a `--paper` (midnight) square, and nothing else.
- **The dot also works as:**
  - the loader (breathing)
  - the prompt caret
  - the idle state of the prompt-submit button
- **Remove** the `Sparkles` icon-in-a-tile everywhere: landing header, login page, and the studio header on the next pass.

---

## 5. Spacing, shape, elevation

- **Spacing** is on a 4px base: `4 8 12 16 24 32 48 72 112 160`.
  - Section rhythm is **160 / 96** (desktop / mobile).
  - Max content width is 1200, and the prompt bar is 720.
  - Page gutters are 32 / 16.
- **Radius: "sharp paper, soft controls."**
  - `2px` for plates, images and media (paper doesn't round)
  - `10px` for buttons and inputs
  - `20px` for the prompt bar
  - `999px` for chips, stickers and the dot
  - Drop the 22px "app window" radius.
- **Borders:** 1px `--hairline` does all structural work. Cards don't get borders; plates separate from the page by tone (`--inset` / `--clay`).
- **Shadows:** there are exactly two.
  1. **The prompt bar:** porcelain `0 24px 60px -24px rgb(60 40 20 / .18)`, midnight `0 30px 80px -20px rgb(0 0 0 / .6)`.
  2. **The part's contact shadow,** baked into the render, not CSS.

  Everything else is flat.
- **Section dividers are dimension rules:** a hairline with 5px end ticks and a mono label sitting in a gap (`— 02 REFINE —`). The rule draws in on scroll.

---

## 6. Components

### Buttons (height 48, or 40 for small; padding-x 20; radius 10; Geist 15/550)

| Variant | Rest | Hover | Press ("key") |
|---|---|---|---|
| **Primary** | `--ink` fill, `--paper` text, trailing `→` | Arrow moves 3px right; fill lightens 4% | Sinks `translateY(2px)` in 60ms; springs back in 180ms `--spring` |
| **Secondary** | Transparent, 1px `--hairline-strong`, `--ink` text | Background `--inset` | Same key press |
| **Ghost** | `--ink-2` text only | `--ink` plus a hairline underline | None |
| **Prompt submit** | 36px circle, `--accent` fill, `--on-accent` arrow `↑` | Glows (midnight) | Key press |

- **Focus** is the same everywhere: `outline: 2px solid var(--accent); outline-offset: 3px`.
- **Disabled** is 40% opacity with `cursor: not-allowed`.
- **Links:** `--ink` with a 1px `--hairline-strong` underline at offset 4px. On hover the underline turns `--accent`.

### Prompt bar (landing hero, landing close, and the studio's command bar later)

- **Size:** 720 max width, 56 high, radius 20, `--sheet` background, 1px `--hairline`, prompt-bar shadow.
- **Placeholder:** a Geist 16 placeholder that *types and cycles* through three real prompts. The caret is the orange dot.
- **Chips below:** `fan mount` · `cable clip` · `pi case`. Clicking one fills the bar.
- **Submit:** routes to `/studio?prompt=…`. If the user is signed out, it goes to `/login?next=/studio%3Fprompt%3D…` and the prompt is shown on the auth page (§8).

### Plate (a part image)

- **Frame:** radius 2, `--clay` or `--inset` background, aspect 4:5 or 1:1.
- **Content:** one part, shot the same way every time (35° three-quarter view, one soft key light from the top left, matte, with a baked contact shadow).
- **Corner labels** in mono: top left `PLATE 04 · LID HINGE`, bottom right `PLA · 0.2 MM · 38 MIN`.
- **Hover:** the caption swaps to the prompt that made the part, in Fraunces italic (220ms).

### Spec sticker

- A mono uppercase 11px pill (`PETG · 22 MIN`), with a `--clay` fill, `--ink` text, a 1px `--hairline-strong` border and 6×10 padding.
- Rotated −3° to +4°, seeded per sticker so the tilt stays stable between renders.
- **At most three stickers per viewport.** Beyond that it turns childish.

---

## 7. Landing page (`/`): about 95 visible words

```
┌────────────────────────────────────────────────────────────────────┐
│ ● nfinit                                     Log in  [Start a part →]   │  64px nav, no theme toggle
├────────────────────────────────────────────────────────────────────┤
│ DESCRIBE → REFINE → PRINT                                          │  label, muted
│                                              ┌──────────────────┐  │
│ Say it.                                      │  PLATE 01        │  │  Display serif, left, cols 1–7
│ *Hold it.*                                   │  [bracket prints │  │  plate cols 8–12, prints in
│                                              │   in, layer by   │  │
│                                              │   layer ══●══]   │  │
│                                              │ PETG·0.2MM·1H12M │  │
│ ╭──────────────────────────────────────────╮ └──────────────────┘  │
│ │ a wall mount for a 40 mm fan, M3 screws● (↑)│                     │  PROMPT BAR = hero control
│ ╰──────────────────────────────────────────╯                        │
│   fan mount   cable clip   pi case                                  │  chips
├──|─────────────────────── — 01 DESCRIBE — ───────────────────────|──┤  dimension rule
│                                   │                                │
│  “A hook for a 25 mm pipe.        │   construct-blue sketch of     │  STICKY: one part,
│   Two M4 screws.”                 │   the hook draws on            │  object pinned right
│                                   │                                │
├──|─────────────────────── — 02 REFINE — ─────────────────────────|──┤
│  Click a face.                    │   one face lights Hot PLA      │
│  *Change your mind.*              │   ├── 6.0 → 9.0 MM ──┤          │  value counts up
│  v1  v2  [v3]                     │   REV B stamp                  │  revision chips
├──|─────────────────────── — 03 PRINT — ──────────────────────────|──┤
│  Print it tonight.                │   clay solid, then layer lines │
│  .STL  .STEP                      │   rise with the nozzle ══●══   │
│                                   │   hook_v3.stl · 184 KB · 38 MIN│
├────────────────────────────────────────────────────────────────────┤
│ Things people actually print.                                      │  H2
│ ┌──────┐ ┌──────┐ ┌──────┐                                          │  3×2 plates (2×3 mobile)
│ │clip  │ │hinge │ │Pi 5  │   hover → italic prompt                  │  ≤3 spec stickers visible
│ └──────┘ └──────┘ └──────┘                                          │
│ ┌──────┐ ┌──────┐ ┌──────┐                                          │
│ │fan   │ │hook  │ │knob  │                                          │
│ └──────┘ └──────┘ └──────┘                                          │
├────────────────────────────────────────────────────────────────────┤
│ Your next part, *rev A.*                                           │  H1, centred (only centred block)
│ ╭────────────── prompt bar (repeat) ──────────────╮                 │
├────────────────────────────────────────────────────────────────────┤
│ ● nfinit   TERMS · PRIVACY                                © 2026   │  mono footer
└────────────────────────────────────────────────────────────────────┘
```

### Exact copy

- **Nav:** `Log in`, `Start a part`
- **Hero:**
  - Label: `DESCRIBE → REFINE → PRINT`
  - Display: **Say it.** / ***Hold it.***
  - Rotating placeholders:
    - "a wall mount for a 40 mm fan, M3 screws"
    - "a snap-fit lid for a Raspberry Pi 5 case"
    - "a cable clip for a 6 mm desk edge"
  - Chips: `fan mount`, `cable clip`, `pi case`
  - Plate captions: `PLATE 01 · 5-INCH QUAD FRAME` / `PETG · 220 MM · 2H 40M`, plus `DRAG TO SPIN` bottom left
- **01 Describe:** the pull-quote "A hook for a 25 mm pipe. Two M4 screws."
- **02 Refine:** "Click a face. *Change your mind.*" with the tag `FACE 7 · 6.0 → 9.0 MM` and chips `v1 v2 v3`
- **03 Print:** "Print it tonight." with chips `.STL` `.STEP` and `hook_v3.stl · 184 KB · 38 MIN`
- **Gallery:**
  - H2 "Things people actually print."
  - Plate labels:
    - `CABLE CLIP · 4 MIN`
    - `LID HINGE · 22 MIN`
    - `PI 5 CASE · 1H 04`
    - `40 MM FAN MOUNT · 26 MIN`
    - `PIPE HOOK · 38 MIN`
    - `M6 KNOB · 9 MIN`
- **Close:** "Your next part, *rev A.*" and the prompt bar
- **Footer:** `TERMS · PRIVACY · © 2026`

The word "AI" appears **zero times above the fold.**

### Mobile (≤640px)

- **Hero order:** label, headline (56px), plate, prompt bar, chips.
- **Flow:** the sticky part stops being sticky. Each step stacks as headline, then a 4:3 frame, then its label.
- **Gallery:** becomes 2 columns.

### Visual assets

**Phase 1 (ship now): one real 3D part, placeholders for the rest.**

- **Hero and auth plates: an interactive drone.** A simple 5-inch quad frame
  built from primitives in r3f (`DroneScene.tsx`). It's graphite, with a
  single Hot PLA part (the printed camera mount) and bone props. It hovers
  gently, auto-rotates and spins when dragged. Zoom and pan are off, and on
  touch only a sideways drag spins it, so the page still scrolls. The founder
  chose this over an empty demo slot: it makes the product feel tangible.
- **Gallery plates stay demo slots:**
  - `--inset` fill, 1px dashed `--hairline-strong` border, radius 2
  - one centred mono label with the part name and time (`CABLE CLIP · 4 MIN`)
  - the corner spec labels stay, so the layout reads as finished
- **Never:** drawn product UI, a fake app window, or a flat SVG part pretending to be a render. The old `ProductShowcase` is deleted, not restyled.

The layer-print reveal runs on every plate, the drone included: the nozzle
line sweeps it once and the part prints in.

The **flow section** stays a simple SVG diagram of the pipe hook (sketch,
face selected, layered). It explains the flow, and isn't pretending to be a
product screenshot.

**Phase 2 (when real renders exist):**
- **Six renders** exported from the real nfinit viewer for the gallery slots (or small r3f meshes like the drone). They're AVIF, about 40KB each.
- **One real photograph** of a printed part on a PEI bed, for the Print step. It earns more trust than any render.
- **A lazy r3f scene** for the flow (proposal D's matcap plus clipping-plane approach). It uses `frameloop="demand"` and loads only when within 400px of the viewport.

**Performance budget:**
- LCP under 1.8s on 4G. The headline is the LCP element.
- Initial JS under 90KB gzipped. three.js is **not** in the initial bundle: the drone is a `next/dynamic` import with `ssr: false`, so it loads after the headline paints.
- WebGL above the fold is allowed for the drone only (founder decision). It renders only while on screen (`frameloop` switches to `never` offscreen), and under reduced motion it stays still but can still be dragged.

---

## 8. Auth page (`/login`)

```
┌─────────────────────────────────────┬──────────────────────────────┐
│                                     │ ● nfinit                     │
│   PLATE 04                          │                              │
│                                     │ Come make                    │  H1 serif 56/40, left
│   [the drone prints in on clay,     │ *something.*                 │
│    nozzle line ══●══]               │                              │
│                                     │ “a wall mount for a 40 mm    │  only if ?next carries a
│                                     │  fan, M3 screws”             │  prompt: italic pull-quote
│                                     │                              │
│                                     │ [ G  Continue with Google  → ]│  primary (ink)
│   LID HINGE · PLA · 22 MIN          │ [ ⌥  Continue with GitHub  → ]│  secondary
│                                     │                              │
│                                     │ New here? Same buttons.      │  caption, muted
│                                     │ TERMS · PRIVACY              │  mono, faint
└─────────────────────────────────────┴──────────────────────────────┘
```

- **Layout:**
  - **Desktop** splits 7/5. The left side is a full-height plate on `--clay` with the same interactive drone as the hero printing in.
  - **The right side** is `--paper`, with content left-aligned, vertically centred and max 360 wide.
  - **Mobile:** the plate becomes a 180px band on top.
- **Copy:**
  - H1 "Come make *something.*"
  - Caption "New here? Same buttons."
  - Footer `TERMS · PRIVACY` (with real links)
  - Remove "Your designs, revisions, and exports in one place." and "keep building interesting things."
- **Carried prompt:** when `next` contains `prompt=`, show it above the buttons as a Fraunces italic pull-quote (24px, `--ink-2`, clamped to two lines). It gives sign-in a reason.
- **Buttons:**
  - **Google** is primary and **GitHub** is secondary, both full width.
  - The Google button uses the **real multicolour G SVG** (16px), not the letter "G". GitHub uses lucide `Github`.
- **Loading:**
  - The pressed button **stays sunk** (translateY 2px) and its label becomes "Opening Google…".
  - The icon is replaced by the **breathing dot**, and a 1px accent **nozzle line** runs along the button's bottom edge on a 1.2s loop.
  - The other button goes to 40% with `aria-disabled`, and the whole group gets `aria-busy="true"`.
  - Drop `Loader2`.
- **Error** (`?error` or a client error):
  - An inline block appears above the buttons: `--inset` background, 2px `--danger` left rule, Geist 13.
  - It reads **"That didn't go through."** followed by "Try again, or use the other button."
  - The raw provider message goes in a `<details>` labelled `Details` (mono, muted).
  - Use `role="alert"` and move focus to the block.
  - On the left, the part **stops half-printed**: a quiet failed-print joke, with no red flash.
- **Theme toggle:** none. The auth page is always porcelain (see §2, Theme).

---

## 9. Motion

### Tokens

| Token | Value |
|---|---|
| `--ease-out` | `cubic-bezier(.2,.7,.1,1)` |
| `--ease-draw` | `cubic-bezier(.65,0,.35,1)` |
| `--spring` | `cubic-bezier(.34,1.56,.64,1)` (buttons only) |

### Motions

1. **Layer-print reveal (the signature).**
   - **What it does:** each part image goes from `clip-path: inset(100% 0 0 0)` to `inset(0)` in `steps(16)` over 1400ms.
   - **The nozzle line:** a 1px `--accent` line rides the clip edge (glowing in midnight) with a 6px horizontal jitter every 60ms, then fades out over 300ms.
   - **When it runs:** once per plate, at 35% in view.
   - **Where it's used:** the hero, the Print step, gallery plates and the auth plate.
2. **Headline rise.** Each line rises from `translateY(105%)` inside an `overflow: hidden` wrapper over 900ms `--ease-out`, with an 80ms stagger. The italic word lands last.
3. **Draw-on.**
   - Construct-blue sketch strokes animate `stroke-dashoffset` over 700ms `--ease-draw`, 35ms apart.
   - Dimension rules scale `scaleX 0→1` over 700ms, with the end ticks appearing at 80%.
   - In Refine, the value counts 6.0 → 9.0 over 520ms (tabular figures), then a `REV B` stamp settles from −8° to −4° over 240ms.
4. **Prompt typewriter.** It types at 38ms per character, holds 2200ms, then deletes at 16ms per character. The dot caret blinks in 1s steps. It pauses on focus or hover.
5. **Key press.** 60ms down, then 180ms `--spring` up. The arrow nudges 3px on hover (160ms).

**The dot breath:** opacity .75→1 over 2800ms ease-in-out. It runs only in the loader and the caret, never in the static logo.

**`prefers-reduced-motion: reduce`:**
- Parts render fully printed, and the nozzle line is hidden.
- Headlines appear instantly.
- Sketches render in their final dimensioned state.
- The placeholder shows the first prompt, static.
- The key press keeps its colour change and drops the transform.
- The flow becomes a static strip of four frames.

No loop runs while offscreen (IntersectionObserver).

---

## 10. Don'ts

**Visual effects:**
- No violet, purple-to-blue gradients, radial glow blobs, or `backdrop-blur` / glass cards.
- No `Sparkles`, wands, stars, emoji or "AI-powered" pills.
- No dot-grid or graph-paper page background (Suzanne's), and no grey pencil sketches. Our sketch lines are construct blue.

**Layouts to avoid:**
- No fake app window with traffic-light dots. The part is the product shot.
- No centred hero stack (eyebrow, H1, sub, two pills, screenshot).
- No three-column icon-in-a-rounded-square feature grid, bento grid, logo wall, testimonial carousel, stat counter or pricing table on the landing page.

**Visual content:**
- No untextured grey meshes or abstract blobs. Every object is a plausible functional part with real millimetres.

**Accent:**
- No accent fills on buttons (except the round prompt submit).
- No more than one orange part per screen.

**Type:**
- No serif under 24px or inside a control.
- No more than one italic word per headline, and never a tinted italic.
- No `FIG. 00 - NAME` style caption without a print spec (material, layer height or minutes) beside it.
- No landing sentence over 8 words.

**Words:** never use "unleash", "supercharge", "revolutionize", "seamless" or "production-ready".

### The cliché guardrail

Warm cream, a serif and one orange accent is on its way to becoming a
common AI-startup look. We keep it from reading that way because the
distinctiveness lives in things a template can't fake:

- a real part on every screen
- the layer-print motion
- mono print specs
- construct-blue sketch lines
- the Missing Dot

If a screen still looks generic with its image removed, the image is doing too
little. Make it bigger.

---

## 11. Implementation map

| File | Change |
|---|---|
| `frontend/src/app/layout.tsx` | Add `Fraunces` (`style: ['normal','italic']`, `axes: ['opsz','SOFT','WONK']`, variable `--font-serif`). Metadata title "nfinit". Theme-init script unchanged. |
| `frontend/src/app/globals.css` | Add the §2 tokens under both `html[data-theme]` blocks. Map the existing `--page-*`, `--primary-button`, `--ring`, `--accent` to them. Delete `--ambient-glow`. Add `--font-serif` to `@theme`. Add `.type-display … .type-spec` utilities from §3. Add motion tokens and the `@media (prefers-reduced-motion)` block. |
| `frontend/src/components/brand/Wordmark.tsx` | New. The Missing Dot lockup (§4). Replaces `Brand()` in `page.tsx` and the inline logo in `login/page.tsx`. |
| `frontend/src/components/landing/Plate.tsx` | New. Image, corner spec labels, prompt-on-hover, and the `LayerReveal` wrapper. |
| `frontend/src/components/landing/LayerReveal.tsx` | New, client component. clip-path `steps(16)`, nozzle line, IntersectionObserver, reduced-motion aware. |
| `frontend/src/components/landing/PromptBar.tsx` | New, client component. Typewriter placeholder, chips, submit that routes to `/studio?prompt=` or `/login?next=`. |
| `frontend/src/components/landing/DimensionRule.tsx` | New. Section divider with ticks and a mono label. |
| `frontend/src/components/landing/FlowHook.tsx` | New. Sticky SVG pipe hook in four states (§7). |
| `frontend/src/app/page.tsx` | Rebuild to §7. Delete `ProductShowcase`, the glow and the noise div. |
| `frontend/src/app/login/page.tsx` | Rebuild to §8, parsing `prompt` out of `next` for the pull-quote. |
| `frontend/src/components/LoginButtons.tsx` | Buttons per §6 and states per §8. Google G SVG. Replace `Loader2` with the dot. The error block gets a `<details>`. |
| `frontend/src/app/studio/page.tsx` | Read the `?prompt=` param, keep it through the sign-in redirect, and prefill the welcome chat input (not auto-sent). |
| `frontend/src/components/landing/DroneScene.tsx` | New, client only. The interactive quad frame for the hero and auth plates (§7). |

**Build order:**
1. Tokens and fonts, plus the wordmark
2. Auth page (small and self-contained)
3. Landing hero and prompt bar
4. Flow section
5. Gallery and close
6. Motion polish and the reduced-motion pass

**Assets owed by the founder:** six to seven part renders from the viewer (the §6 plate recipe), and later one real photo of a print on a PEI bed.
