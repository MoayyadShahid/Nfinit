# B — "Playful Maker"

## 1. Concept: **Hot End**
**Thesis:** nfinit should feel like the moment a print comes off the bed: warm orange plastic, a soft chunky serif, stickers on everything, and hardware buttons that go *clunk* when you press them.

One loud idea per screen, and that idea is always a **part**, never a UI chrome mockup.

---

## 2. What to steal, and what to beat

**Research note:** WebFetch could not reach suzanne3d.com, bambulab.com, gumroad.com or poolsuite.net (the egress proxy blocked them), and moidshahid.com did not resolve (DNS ENOTFOUND). What I say about Suzanne comes from its search listing. What I say about the other sites is general knowledge, not a fresh visit.

| Source | Technique to steal |
|---|---|
| **Gumroad** (2022+ rebrand) | Hard offset shadows (`4px 4px 0 ink`) with 2px ink borders on buttons and cards. Flat, loud, tactile, no blur. We use a *vertical-only* version so it reads as a physical key, not a Gumroad clone. |
| **Bambu Lab** | Product-as-hero: a real printed object, photographed large on a neutral field. Also the filament-spool **spec label** (material · color · temp) as a graphic language. We turn it into our sticker system. |
| **Figma Config** (2023–24) | Oversized display type that runs edge to edge, plus sticker-like shapes slapped at angles *on top of* the type. |
| **Poolsuite** | Commits fully to a personality with a limited, sunny palette. Chrome (window bars, labels) is used as a *joke*, not as a fake app. |
| **Raycast** | Keyboard-key rendering: a light top edge, a darker bottom lip, a press state that sinks. This drives our button physics. |
| **Framer** | Motion that is scroll-linked but short. Each section has one move that finishes fast. |
| **Founder's site (moidshahid.com)** | I could not see it. The brief calls it "clean but too plain". We keep the restraint (lots of air, few words) and add a single hot color and texture. |

**Beat Suzanne:** its search title is *"Physical AI for industrial design teams"*, with a sibling page for *"product design"*. It sells upward to teams and enterprise. We go the other way: **your desk, your printer, tonight**. Suzanne talks about generating models. We show *printed plastic* with layer lines. Nobody wants an "AI 3D model"; they want the shelf bracket that snapped.

---

## 3. Color system

Filament-derived. **One hot color. Everything else is warm neutral.**

| Token | Midnight | Porcelain | Use |
|---|---|---|---|
| `--primary` (**PLA Orange**) | `#FF6A1F` | `#F2540F` | Primary CTA fill, active face highlight, one word per screen max |
| `--primary-ink` (text on primary) | `#1A0D05` | `#1A0D05` | Always dark text on orange (≈6.5:1). Never white on orange |
| `--secondary` (**Spool Ink**) | `#F4F1EA` | `#191815` | Secondary buttons, sticker fills, headline ink |
| `--accent` (**Signal Yellow**) | `#FFD23F` | `#FFC21A` | Stickers and highlighter swipes ONLY. Never on buttons, never on text |
| `--surface` (page) | `#0F0E0C` (warm black, not blue) | `#F4F1EA` | Body background |
| `--surface-raised` | `#191815` | `#FFFDF8` | Cards, build plates |
| `--surface-sunk` | `#0A0908` | `#ECE8DF` | Input wells, print bed |
| `--ink` | `#F4F1EA` | `#191815` | Primary text |
| `--muted` | `#A39E93` | `#6E6960` | Secondary text, captions |
| `--hairline` | `rgba(244,241,234,.10)` | `rgba(25,24,21,.12)` | Dividers, card outlines |
| `--edge` (chunky border) | `#F4F1EA` | `#191815` | 2px borders on buttons and stickers |
| `--bed` (PEI texture tint) | `#1E1B16` | `#E4DCCB` | Build-plate card backgrounds |
| `--danger` | `#FF5A5A` | `#C8341C` | Errors only |

**Rules**
- Orange covers **≤8% of any viewport**. If two orange things are visible, one of them is wrong.
- Yellow appears only as stickers or a single highlighter underline. It never touches orange; they sit at least 24px apart.
- No gradients, except the 1px top-light on buttons. No violet anywhere. Delete `--ambient-glow`.
- Midnight is *warm* black (`#0F0E0C`), so orange looks like hot plastic, not neon.

---

## 4. Type system

- **Display serif: Fraunces** (Google Fonts, variable). Load with `axes: ["SOFT","WONK","opsz"]`. Headlines use `SOFT 100, WONK 1`: soft wedge terminals and the wonky leaning *n*. It is friendly, chunky and never "legal-firm".
- **Sans: Geist** (keep it; the studio already uses it). UI, body, buttons.
- **Mono: Geist Mono** for stickers, labels, dimensions, and filenames.

| Role | Font | Desktop / Mobile | Wt | LH | Tracking |
|---|---|---|---|---|---|
| Display (hero) | Fraunces opsz 144, SOFT 100, WONK 1 | 128 / 60px | 600 | 0.92 | -0.035em |
| H1 | Fraunces opsz 96, SOFT 100 | 80 / 44px | 600 | 0.95 | -0.03em |
| H2 | Fraunces opsz 72, SOFT 100 | 52 / 34px | 560 | 1.0 | -0.02em |
| H3 | Fraunces opsz 36, SOFT 50 | 28 / 24px | 560 | 1.1 | -0.01em |
| H4 | Geist | 18 / 17px | 600 | 1.3 | -0.01em |
| Body | Geist | 17 / 16px | 400 | 1.55 | -0.005em |
| Body-sm | Geist | 15 / 15px | 400 | 1.5 | 0 |
| Caption | Geist | 13 / 13px | 500 | 1.4 | 0 |
| Label / sticker | Geist Mono | 12 / 11px | 500 | 1.0 | +0.06em, UPPERCASE |
| Dimension | Geist Mono | 13 / 12px | 400 | 1.0 | 0, tabular-nums |
| Button | Geist | 16 / 16px | 650 | 1.0 | -0.01em |

**Serif vs sans rules**
- Serif is for **nouns and promises**: headlines, the wordmark, and big numbers (`01 02 03`). It is never used below 24px and never for UI controls.
- Sans is for **anything you act on**: buttons, inputs, nav, body text.
- Mono is for **anything a machine would print**: dimensions, file types, layer heights, sticker text.
- One italic moment per page, at most: *Fraunces italic* on the single word you want remembered (for example *print*).

---

## 5. Spacing, radius, borders, shadows, buttons

- **Spacing:** 4px base. Scale: 4, 8, 12, 16, 24, 32, 48, 72, 112, 160. Sections are 160px apart on desktop and 96px on mobile. Content max width is 1200px, hero type is 1320px. Gutter is 16px on mobile, 32px on desktop.
- **Radius:** `--r-sm 8px` (inputs, chips) · `--r-md 14px` (buttons) · `--r-lg 24px` (cards, build plates) · `--r-pill 999px` (stickers only). Buttons are **not pills**: 14px reads as a hardware key.
- **Borders:** hairline 1px `--hairline` for structure. **Chunky 2px `--edge`** only on buttons and stickers.
- **Shadows:** there are none, except the key-lip. `--lip: 0 4px 0 0 var(--edge)`. Cards float on color contrast, not blur. The single exception is the hero part render, which gets a real contact shadow (`ellipse, blur 24px, 30% ink`) under the object.

**Buttons (48px tall, 20px horizontal padding, 16px text)**
- **Primary ("Key"):** `bg primary`, `color primary-ink`, `border 2px edge`, `box-shadow: var(--lip)`, inset top highlight `inset 0 1px 0 rgba(255,255,255,.35)`. Hover: `translateY(-1px)`, lip becomes 5px. Active: `translateY(4px)`, lip becomes 0 (it *clunks down*). Focus: 3px `--accent` outline with 3px offset.
- **Secondary:** the same mechanics, with `bg surface-raised` and `color ink`.
- **Ghost:** no border and no lip. Ink text with a lucide `ArrowDown` or `ArrowRight`. Hover draws a 2px orange underline from left to right.
- **Link style:** ink text, 1px underline at 3px offset in `--hairline`. Hover turns the underline orange and 2px thick.

**Sticker component:** a Geist Mono UPPERCASE 11px pill, `bg accent` or `bg secondary`, 2px edge border, 6px × 10px padding, rotated −4° to 6° (seeded per sticker, never random per render). Example: `PETG · 0.2MM · 14 MIN`.

**Build-plate texture:** a CSS `radial-gradient` dot grid (1px dots every 10px at 18% ink) on `--bed`. Plates are 24px-radius cards. Layer-line texture is `repeating-linear-gradient(0deg, ink 0 1px, transparent 1px 3px)` at 6% opacity, used **only** on printed-part imagery.

---

## 6. Landing page (≈82 visible words)

```
┌──────────────────────────────────────────────────────────────┐
│ [▤] nfinit                                   Log in  [Start ▸]│  nav, 72px, no bg until scroll
├──────────────────────────────────────────────────────────────┤
│                                                              │
│   Say the part.                           ╭─[PLA · 22 MIN]─╮ │  sticker, rotated 5°
│   Print the *part.*                      ▟██ orange bracket │  real photo of a printed
│                                          ██▙ on PEI bed     │  bracket, layer lines visible
│   Chat → editable CAD → STL.               ◠ contact shadow │
│                                                              │
│   [ Start making ]   See how ↓                               │
└──────────────────────────────────────────────────────────────┘
```
**Hero.** Display: "Say the part. Print the *part.*" The second "part" is Fraunces italic in orange. Sub (mono label): "CHAT → EDITABLE CAD → STL". CTAs: **Start making** / ghost **See how**. *Visual:* a big photo of one orange printed bracket on a textured bed, taking 45% of the width, with one yellow sticker. Mobile: the photo goes above the headline and the headline drops to 60px.

```
┌──────────────────────────────────────────────────────────────┐
│  01              ─▶     02              ─▶     03             │  serif numerals, 72px
│ ┌────────────┐        ┌────────────┐        ┌────────────┐   │
│ │ "hook for  │        │  ▟▙ face   │        │ ≡≡≡ layers │   │  three build-plate cards
│ │  a 25mm    │        │  glowing   │        │ ≡≡≡ rising │   │  on a moving belt
│ │  rod"  ▸   │        │  "+2mm"    │        │  [.STL]    │   │
│ └────────────┘        └────────────┘        └────────────┘   │
│  Describe              Refine                 Print           │  H3 serif
└──────────────────────────────────────────────────────────────┘
```
**Conveyor.** Three cards: **Describe**, **Refine**, **Print**. Each card has one prop and no body copy:
1. A chat bubble reading "hook for a 25mm rod", with a key-style send button.
2. The part with one face in orange and a sticker reading "+2 MM".
3. The same part in layer-line texture with a `.STL` sticker.

The cards sit on a thin belt (a dashed hairline with ticks) that scrolls sideways under them.

```
┌──────────────────────────────────────────────────────────────┐
│   Click a face.                    ┌───────────────────────┐ │
│   Ask for a change.                │  [part, 1 face orange]│ │
│                                    │   ↕ 4.0 → 6.0 mm      │ │  dimension callout (mono)
│                                    └───────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```
**Refine close-up.** H2: "Click a face. Ask for a change." *Visual:* a large render in which a cursor clicks, the face turns orange, and a mono dimension ticks from 4.0 to 6.0 mm. This is the one "product" moment.

```
┌──────────────────────────────────────────────────────────────┐
│  Brackets. Mounts. Hinges. Whatever broke.                   │  H2 serif
│  ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐ ┌────┐                    │
│  │part│ │part│ │part│ │part│ │part│ │part│   ← each wears a    │
│  └────┘ └────┘ └────┘ └────┘ └────┘ └────┘     spool sticker   │
└──────────────────────────────────────────────────────────────┘
```
**Parts wall.** H2: "Brackets. Mounts. Hinges. Whatever broke." There are six photographed or rendered parts on bed tiles. Their stickers read "SHELF BRACKET · 18 MIN", "GOPRO MOUNT · 26 MIN", "PI CASE · 1H 04", "PIPE ADAPTER · 9 MIN", "BOX HINGE · 12 MIN" and "CABLE CLIP · 4 MIN". One part in six is orange; the rest are ink or bone filament.

```
┌──────────────────────────────────────────────────────────────┐
│                    Make the thing.                           │  Display, centered
│                    [ Start making ]                          │
│  nfinit · STL · STEP                    © 2026  Log in       │  footer, mono
└──────────────────────────────────────────────────────────────┘
```
**Final CTA:** "Make the thing." Footer (mono): "NFINIT · STL · STEP".

**Logo:** drop the sparkle. The mark is an orange 14px-radius square with three stacked horizontal bars that step inward, like layer lines forming an "n" silhouette. The wordmark is lowercase "nfinit" in Fraunces 600 SOFT 100.

---

## 7. Auth page

```
┌─────────────────────────────┬────────────────────────────────┐
│ [▤] nfinit          ☾       │                                │
│                             │   build plate, full bleed      │
│  Welcome back               │   one orange part, sticker:    │
│  to the workbench.          │   "YOUR NEXT PART · ?? MIN"    │
│                             │                                │
│  [G  Continue with Google ] │                                │
│  [⌥  Continue with GitHub ] │                                │
│                             │                                │
│  New here? Same buttons.    │                                │
└─────────────────────────────┴────────────────────────────────┘
```
- The page splits 5/7 on desktop. On mobile the plate becomes a 180px banner on top.
- H1 (Fraunces 52px): "Welcome back to the workbench."
- Buttons: Google is the **Primary Key** and GitHub is the **Secondary Key**. Both are full width, 52px tall and 12px apart. The Google button uses the real multicolor G SVG, not the letter "G".
- Caption (muted, 13px): "New here? Same buttons." Remove the current "keep building interesting things" line.
- **Loading:** the pressed button stays *sunk* (translateY 4px, lip 0). The label becomes "Heating up…" and a 3-bar layer icon fills bottom to top, looping at 600ms steps. The other button dims to 40%. `aria-busy="true"`.
- **Error:** a red-bordered sticker (not rotated) appears above the buttons: "COULDN'T SIGN IN — TRY AGAIN". The plate part on the right does a 2-frame "wobble" (±2°, 240ms), a failed-print joke. Set `role="alert"` and move focus back to the button that was pressed.

---

## 8. Motion

| Motion | Spec | Reduced-motion |
|---|---|---|
| **Key clunk** (all buttons) | Press: 60ms `cubic-bezier(.3,0,.5,1)` down. Release: 180ms `cubic-bezier(.34,1.56,.64,1)` (a slight overshoot) | Keep the color change, drop the transform |
| **Layer-print reveal** (hero headline, once on load) | `clip-path: inset(100% 0 0 0)` → `inset(0)` over 900ms with `steps(14)`, so it builds up in visible layers, with a 2px orange "nozzle" line riding the edge | Plain 200ms opacity fade |
| **Sticker slap** (stickers entering view) | Scale 1.15 → 1, rotate from +12° to the final angle, over 260ms `cubic-bezier(.2,1.4,.4,1)`, staggered 70ms | Appear instantly |
| **Conveyor** | The belt's dashes translate 0 → −40px, looping every 1.6s linear, only while in view (IntersectionObserver). Cards enter from the right in sequence, 400ms `ease-out`, 120ms stagger | Static belt, cards visible |
| **Face select** (refine section) | The face fills orange over 200ms, then the dimension counts 4.0 → 6.0 over 500ms `ease-out`, triggered at 40% scroll-in | Show the final state |

All five motions respect `prefers-reduced-motion: reduce`. No loop runs offscreen.

---

## 9. Don'ts

- No violet, no sparkles (✨/`Sparkles` icon), no "AI-powered" pill, no "✦ New" badge.
- No glassmorphism, no `backdrop-blur` cards, no radial glows behind headlines.
- No fake macOS window with three dots as the hero. Show the **part**, not the app.
- Never white text on orange. Never orange + yellow touching. Never more than one orange CTA visible.
- No three-column "feature grid with icons in rounded squares".
- No stock gradient mesh or 3D blob. Every 3D object must be a plausible functional part with real mm dimensions.
- Rotated stickers are capped at 3 per viewport. Past that it gets childish.
- The serif never appears on buttons, inputs or anything under 24px.
- No paragraph copy longer than 8 words on the landing page.

---

## 10. Strongest 3 ideas (harvest these)

1. **"Key" buttons with a physical lip.** A 2px ink border, a hard 4px bottom shadow, and a press that sinks 4px with an overshoot on release. It is the tactile signature across the landing page, auth and studio, and the loading state ("Heating up…") keeps the button visibly pressed.
2. **Filament-spool sticker system.** Geist Mono UPPERCASE spec labels (`PETG · 0.2MM · 14 MIN`) in signal yellow or ink, slightly rotated and slapped onto parts. They replace feature copy by stating facts a maker cares about, and they make a whole grid of parts read as a real shelf of prints.
3. **Layer-print headline reveal plus warm PLA-orange-on-bone palette.** The hero headline builds up in stepped "layers" with an orange nozzle line (`steps(14)` clip-path). It is paired with a single hot filament orange (`#FF6A1F` / `#F2540F`, always dark text on it) against warm black or porcelain, and Fraunces SOFT/WONK for a friendly, unmistakably non-SaaS serif.
