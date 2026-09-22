# E — Midnight Luxe

## 1. Concept: "The Hot Dot"
**Thesis:** A dark, gallery-quiet page where a huge Didone serif and one glowing hotend-orange dot carry the whole brand. The prompt bar is the only control that matters, and every part on the page appears by *printing in*, layer by layer.

**Research note:** WebFetch was egress-blocked for suzanne3d.com, lovable.dev, runwayml.com, ssense.com and news.ycombinator.com, and moidshahid.com did not resolve (DNS ENOTFOUND). What I say about Suzanne comes only from search snippets. What I say about the other references comes from prior knowledge and was not checked today. The judge should treat those points as directional.

## 2. What to steal
| Source | Technique to take |
|---|---|
| **Bottega Veneta** | One brand color used everywhere and used rarely ("Bottega green"). Ours is **Hotend orange**, and it only ever appears as light: a dot, a line, a selected face. |
| **SSENSE** | Tiny uppercase sans labels next to a stark catalog grid, with captions as metadata (`BRACKET — PETG — 0.2 MM`). The page should read like a lookbook. |
| **Runway** | An editorial serif headline set over cinematic, full-bleed media. The type sits on top of the image, not beside a card. |
| **Perplexity / Lovable** | The input box is the page's center of gravity. The hero *is* the prompt bar, with rotating example prompts. |
| **Linear** | Warm near-black instead of #000, 1px hairlines doing the work shadows usually do, tight negative tracking, no decorative gradients. |
| **Midjourney** | Near-zero copy. Images carry the argument. |
| **Cursor** | Show the real product surface, cropped and confident, and skip the illustrated "app window" chrome. |

**Suzanne:** search snippets say it now calls itself *"Physical AI for industrial design teams"*: prompt, photo or sketch in, STEP/STL/3MF out. **How we beat it:** it is heading toward enterprise and teams, and we go maker-first. **The printed object is the payoff**, so we show layer lines, millimetres, filament and a real part on a PEI bed, not a render floating in a void. Every visual carries a real dimension.

## 3. Color system
Roles: **Primary = Bone/Ink** (the text and primary-button color). **Secondary = Smoke/Linen** (quiet surfaces and secondary buttons). **Accent = Hotend** (light, never fill).

| Token | Midnight | Porcelain |
|---|---|---|
| `--bg` | `#0C0A09` | `#F4F1EA` |
| `--surface` | `#141210` | `#FBF9F4` |
| `--raised` | `#1C1916` | `#FFFFFF` |
| `--ink` (primary) | `#EFE8DC` | `#191815` |
| `--ink-inverse` | `#0C0A09` | `#F4F1EA` |
| `--secondary` | `#26221E` | `#E8E3D8` |
| `--muted` | `#9A9187` | `#6B655C` |
| `--faint` | `#5E574F` | `#A39C90` |
| `--hairline` | `rgba(239,232,220,.10)` | `rgba(25,24,21,.12)` |
| `--hairline-strong` | `rgba(239,232,220,.22)` | `rgba(25,24,21,.28)` |
| `--accent` (Hotend) | `#FF5B1F` | `#E0541A` |
| `--accent-ink` (text-safe) | `#FF7A45` | `#A83A0B` |
| `--accent-glow` | `rgba(255,91,31,.55)` | `none` (solid only) |
| `--danger` | `#F2685C` | `#B42318` |

**Rules**
- Accent covers **no more than 2% of the pixels on any screen**. It may appear as: the brand dot, the layer-line, a selected CAD face, the prompt submit arrow, and focus rings. It is never used for button fills, section backgrounds or gradients.
- The glow exists **only in Midnight** (`box-shadow: 0 0 12px 2px var(--accent-glow)`). In Porcelain the accent is a flat, matte "sintered" orange, because glows on cream look dirty.
- Midnight gets a 3% monochrome film-grain SVG overlay (`mix-blend-mode: overlay`). Porcelain gets none, just paper.
- Part renders use a single material: warm graphite `#3A3632` in Midnight and a bone-PLA `#E9E2D3` with a soft AO shadow in Porcelain. No rainbow materials.
- Delete `--ambient-glow` violet entirely.

## 4. Type system
- **Display serif:** **Bodoni Moda** (Google, variable `opsz` 6–96, wt 400–900). Load it with `axes:['opsz']` and pin `font-variation-settings:"opsz" 96` for display sizes. Use the italic for the emotional word in a line.
  *Fallback if the judge finds Didone too fashion:* **Instrument Serif** (400 + italic only).
- **Sans:** keep **Geist** (already wired, neutral, crisp).
- **Mono / labels:** **Geist Mono**.

| Role | Font | Desktop / Mobile | Wt | LH | Tracking |
|---|---|---|---|---|---|
| Display | Bodoni Moda | 144 / 64 px | 400 | 0.88 | -0.035em |
| H1 | Bodoni Moda | 96 / 48 | 400 | 0.92 | -0.03em |
| H2 | Bodoni Moda | 60 / 36 | 400 | 1.0 | -0.02em |
| H3 | Bodoni Moda | 32 / 26 | 500 | 1.1 | -0.01em |
| H4 | Geist | 18 / 17 | 550 | 1.3 | -0.01em |
| Body | Geist | 16 / 16 | 400 | 1.55 | -0.005em |
| Body-sm | Geist | 14 / 14 | 400 | 1.5 | 0 |
| Caption | Geist | 12 / 12 | 400 | 1.4 | 0 (muted) |
| Label | Geist Mono | 11 / 10 | 500 | 1.2 | +0.14em, UPPERCASE |
| Data | Geist Mono | 13 / 12 | 400 | 1.4 | 0, tabular-nums |

**Rules**
- Serif is for **statements only**: H1–H3 and the index list. It is never used below 26px, because hairline serifs break at small sizes, and never in buttons, inputs or the app UI.
- Each serif headline gets **at most one italic word**, and that word is the emotional one ("*hold* it").
- Sans handles every interactive element. Mono handles every number, unit, filename and label (`80 × 48 × 6 MM`, `V4`, `.STL`).
- Units are always mono and uppercase, with a thin space before `MM`.

## 5. Spacing, radii, borders, shadows, buttons
- **Spacing:** 4px base, scale `4 8 12 16 24 32 48 72 112 160`. Sections are separated by 160px on desktop and 96px on mobile. The page gutter is 24px, or 16px at ≤400px. Max content width is 1280px, and the prompt bar is 720px.
- **Radii: "sharp frames, soft controls."** Media frames and plates get **2px** (lookbook). Buttons get **10px**. The prompt bar gets **20px**. Chips get 999px. Nothing else is rounded.
- **Borders:** 1px `--hairline` everywhere. Sections are divided by full-bleed hairlines with a mono label sitting *on* the line (`— 02 REFINE`).
- **Shadows:** there is essentially one. The prompt bar floats with `0 30px 80px -20px rgba(0,0,0,.6)` in Midnight and `0 24px 60px -24px rgba(60,40,20,.18)` in Porcelain. Everything else is flat.
- **Buttons** are 44px tall, 20px horizontal padding, Geist 14/500:
  - *Primary:* `--ink` background with `--ink-inverse` text. Hover: 2% brighter and a 1px `--hairline-strong` outer ring. Active: `scale(.98)`.
  - *Secondary:* `--secondary` background with `--ink` text. Hover: background moves toward `--raised`.
  - *Ghost:* transparent with `--muted` text. Hover: text becomes `--ink` and a hairline underline appears.
  - *Focus (all):* a 2px `--accent` ring at 2px offset. This is one of the accent's few legitimate uses.
- **Links:** `--ink` with a 1px underline at `--hairline-strong`, offset 4px. On hover the underline turns `--accent` and gets a trailing `↗` (lucide `ArrowUpRight` 12px).

## 6. Landing page (visible copy is about 95 words)

**Brand mark (replaces the sparkle).**
- **The Missing Dot:** the name is "i**nfinit**e" with the i taken off. Our symbol is **that i's missing dot**, a filled 8px circle in Hotend that glows in Midnight. It sits before the wordmark: `● nfinit`. The dot *is* the nozzle tip: the thing that turns a sentence into an object.
- **Wordmark:** lowercase `nfinit` in Bodoni Moda Italic 500, tracking -0.02em. The dot sits at x-height, one em-sixth left of the "n", optically aligned with where an i's tittle would be.
- **Favicon:** the orange dot on a `#0C0A09` square, and nothing else.
- **Loader:** the dot breathing. **Cursor in the prompt:** the dot.

```
┌──────────────────────────────────────────────────────────────┐
│ ● nfinit                                  Log in   [Start]  ◐ │  nav: transparent, 64px
├──────────────────────────────────────────────────────────────┤
│  TEXT → PARAMETRIC CAD → STL                  (label, muted)  │
│                                                              │
│      Say it.                                                 │  Display serif, left-aligned
│      *Hold it.*                                              │  (not centered: editorial)
│                                                              │
│   ╭──────────────────────────────────────────────────────╮   │
│   │ a wall mount for a 40 mm fan, M3 screws●         [↑] │   │  PROMPT BAR = hero object
│   ╰──────────────────────────────────────────────────────╯   │  placeholder types & cycles
│       [ fan mount ] [ cable clip ] [ pi case ]  (chips)      │
│                                                              │
│   ┌──────────────── full-bleed plate ───────────────────┐    │
│   │        part prints in from the bed, orange          │    │  LAYER-LINE REVEAL
│   │ ═════════ glowing layer line ═════════              │    │
│   │ 40 × 40 × 12 MM            PETG · 0.2 MM · V1       │    │  mono corner captions
│   └──────────────────────────────────────────────────────┘   │
├── — 01 DESCRIBE ─── — 02 REFINE ─── — 03 PRINT ──────────────┤
│  I.                  II.                 III.                │  serif roman numerals, H3
│  [prompt still]      [face lit orange    [photo: printed     │  three 4:5 frames, 2px radius
│                       + chip "+12 mm"]    part on PEI bed]   │
│  Describe.           Refine.             Print.              │  H4 sans, one word each
├── — REVISIONS ───────────────────────────────────────────────┤
│  [v1][v2][v3][v4]  contact-sheet strip, film-negative frames │  SSENSE lookbook
│  V1 · V2 · V3 · V4 — 12:04 · 12:06 · 12:11 · 12:15           │  mono captions
├── — INDEX ───────────────────────────────────────────────────┤
│  Brackets                                              014   │  H2 serif list;
│  Mounts                                                022   │  hover = thumbnail
│  Enclosures                                            009   │  follows cursor
│  Adapters                                              017   │  (fashion index)
│  Hinges                                                006   │
├──────────────────────────────────────────────────────────────┤
│           .STL            .STEP                              │  H1 serif, two words
│           Print it.       Keep editing it.                   │  caption muted
├──────────────────────────────────────────────────────────────┤
│   Your next part is  *one sentence*  away.                   │  H2
│   ╭─────────────── prompt bar (repeat) ──────────────╮       │
│   ● nfinit    © 2026                           Log in · X    │  footer, labels
└──────────────────────────────────────────────────────────────┘
```

**Exact copy**
- Label: `TEXT → PARAMETRIC CAD → STL`
- H1: **Say it.** / ***Hold it.***
- Placeholders cycle through: "a wall mount for a 40 mm fan, M3 screws" / "a snap-fit lid for a Raspberry Pi 5 case" / "a 2 mm-offset hinge for a cabinet door".
- Chips: `fan mount`, `cable clip`, `pi case`. Submitting routes to `/login?next=/studio?prompt=…`.
- Flow: **Describe.** / **Refine.** / **Print.** The Refine frame carries an in-image chip reading "Extend this face +12 mm".
- Exports: `.STL`: "Print it." `.STEP`: "Keep editing it."
- CTA: "Your next part is *one sentence* away." Nav: "Log in", "Start".

**Visual rules:** each section has exactly one visual. Nothing is illustrated. Use real renders from the product plus **one real photograph** of a printed part (it earns more trust than any render). There are no feature cards and no icon grids.

## 7. Auth page
Desktop is a 50/50 split. On mobile the plate collapses into a 200px band on top.

```
┌────────────────────────────┬─────────────────────────────┐
│  PLATE 04                  │ ● nfinit                  ◐ │
│  (fan shroud printing in,  │                             │
│   layer line glowing,      │   Come make                 │  H1 serif 64/40
│   slow 20s turntable)      │   *something.*              │
│                            │                             │
│                            │   [G  Continue with Google ]│  primary
│                            │   [⌥  Continue with GitHub ]│  secondary
│  FAN SHROUD · V3 · 38 MIN  │                             │
│  PETG · 0.2 MM             │   Terms · Privacy           │  caption, faint
└────────────────────────────┴─────────────────────────────┘
```

- **Copy:** H1 "Come make *something.*" Buttons "Continue with Google" and "Continue with GitHub". Footer "Terms · Privacy". Drop the current subhead and the "keep building interesting things" line.
- **Google glyph:** use the real multicolor G SVG in a 16px box, not a text "G".
- **Loading:** the pressed button keeps its size. The label changes to "Opening Google…" and the icon is replaced by **the brand dot breathing**, not a spinning `Loader2`. The other button drops to 40% opacity and becomes `aria-disabled`.
- **Error** (URL `?error` or Supabase error): an inline row directly under the buttons with a 1px `--danger` left rule, 13px sans, `--danger` text: "That didn't go through. Try again." Buttons re-enable, focus returns to the button that was last used, and the region is `role="alert"`. Raw provider messages go only into a `<details>` labeled "Details" (mono, faint).

## 8. Motion
1. **Layer-line reveal (signature):** the part's `clip-path: inset(100% 0 0 0)` animates to `inset(0)` over **2400ms, `cubic-bezier(.65,0,.35,1)`**. A 1px `--accent` line rides the clip edge with the glow and a 6px horizontal jitter at 60ms steps (the nozzle). The line fades out over 300ms at the end. It triggers once when 40% of the element is in view.
2. **Headline mask rise:** each line rises from `translateY(105%)` inside `overflow:hidden` over **900ms, `cubic-bezier(.16,1,.3,1)`**, with an 80ms stagger. The italic word lands last.
3. **Prompt typewriter:** 38ms per character, a 2200ms hold, then deletion at 16ms per character. The caret is the orange dot blinking at 1s steps. It pauses on focus or hover.
4. **Dot breath:** opacity .75→1 and glow blur 8→14px over **2800ms ease-in-out, infinite**. It runs only in the logo, the loader and the caret.
5. **Index hover follow:** the thumbnail follows the cursor with a lerp factor of 0.14, fades in over 180ms `ease-out`, and moves 2° of rotation per 100px of velocity.

**Reduced motion:** every part renders fully printed, and the layer line is hidden. Headlines appear instantly. The placeholder shows only the first prompt, statically. The dot stays solid with no breath. The index thumbnail opens as a fixed preview on the right. No parallax anywhere.

## 9. Don'ts
- No purple, no gradients as decoration, no blob glows, no sparkle, wand or star icons, no "AI-powered" pills.
- No glassmorphism or `backdrop-blur` cards. The only blur on the site is the dot's glow.
- No centered hero text with a centered subhead and two pills (the 2023 SaaS template).
- No fake macOS traffic-light windows.
- No 3-column feature cards with lucide icons in tinted squares.
- No serif under 26px, and no serif inside a control.
- No accent-filled buttons. The accent is light, not paint.
- No stock renders without dimensions: every part carries a mono caption with real millimetres.
- No sentences longer than 8 words anywhere on the landing page.
- No emoji, no "Unleash", "Supercharge" or "Revolutionize".

## 10. My strongest 3 ideas
1. **The Missing Dot brand mark.** "i**nfinit**e" minus the i, and the symbol is that i's missing dot, rendered as a glowing hotend-orange nozzle tip. It works as the logo, favicon, loader, prompt caret and focus accent, so the whole brand runs on a single 8px element.
2. **Layer-line reveal as the universal entrance.** Every part on the site, including the hero, the flow frames and the auth plate, *prints itself in* from the bed, with a glowing orange nozzle line riding the clip edge. The motion sells "3D printing" without any words. Reduced motion shows it fully printed.
3. **Lookbook grammar applied to CAD.** Huge Bodoni Moda statements ("Say it. *Hold it.*"), tiny tracked mono metadata on every image (`40 × 40 × 12 MM · PETG · V3`), a contact-sheet revision strip, and a fashion-style hover-image **index** of part categories. Together they make functional brackets feel desirable and read nothing like generic AI SaaS.
