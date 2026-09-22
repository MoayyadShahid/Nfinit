# D: Tactile Objects

## 1. Concept + thesis
**"Specimen"**: every screen is a studio photograph of one printed part. It sits on a matte surface under soft light, labelled like a museum specimen, with the prompt that made it as the caption. *The object is the product shot. The prompt is the caption.* No app chrome, no fake windows, no glow.

## 2. What to steal, and what to beat
**Research note:** my sandbox's egress proxy blocked every fetch: suzanne3d.com, bambulab.com, teenage.engineering, apple.com and spline.design. moidshahid.com did not resolve (DNS ENOTFOUND). Web search worked. It showed that Suzanne's current titles are "Physical AI for industrial design teams" and "Physical AI for product design". Its pitch is "start from a prompt, a photo, or a sketch… export STEP, STL, 3MF", with an OpenSCAD pipeline running in-browser via WASM. I could not see its visuals. The technique notes below come from my prior knowledge of these sites, not from fresh screenshots, so check them before relying on them.

| Source | Technique to steal |
|---|---|
| Apple product pages (AirPods Pro, iPhone) | **One-line headline over one object, then a sticky scroll sequence** where the object stays pinned and changes state as copy swaps beside it. Use the headline-then-product-reveal rhythm. |
| Teenage Engineering | **Mono spec labels as ornament**: tiny uppercase part codes, dimensions and hairline leader lines pointing at features. Objects on flat off-white with almost nothing else. |
| Bambu Lab product pages | **Macro close-ups of layer lines** and "print time" figures shown as hero numbers. Makers love seeing the texture. |
| Spline | **Soft clay/matcap 3D that feels touchable**, with the pointer gently tilting the object (small parallax, not free orbit). |
| Rabbit r1 / Humane launch pages | **A single saturated brand object** (Rabbit's orange) as the whole colour story. The object *is* the accent colour. |
| moidshahid.com (per the brief: clean but plain) | Keep the calm and the whitespace. Add the missing *thing*: an object, a serif, and one colour. |

**Beat Suzanne:** it now pitches itself to industrial design teams, which is our opening. Be warm, hobbyist and print-first. Show **actual print time, material and a layer-line finish** where they would show abstract renders. Every visual ends as a physical PLA object, never a floating gray mesh.

## 3. Colour system
The accent is a filament colour, **"Hot PLA" orange**. It appears on the object and on one button, and nowhere else.

| Token | Midnight | Porcelain | Rule |
|---|---|---|---|
| `--surface` (page) | `#0E0D0B` (warm black, not #000) | `#F4F1EA` | Page background. Shaded to look like the "table" the object sits on. |
| `--surface-raised` | `#171613` | `#FBF9F4` | Inputs, auth card, menus |
| `--surface-sunk` | `#080807` | `#EAE5DA` | Specimen plates, code/mono wells |
| `--ink` (primary) | `#F2EEE6` | `#191815` | Headlines, primary button fill |
| `--ink-2` (secondary) | `#B8B2A6` | `#4A463E` | Body copy |
| `--muted` | `#7A7468` | `#8A8478` | Captions, mono labels |
| `--hairline` | `rgba(242,238,230,0.10)` | `rgba(25,24,21,0.12)` | 1px rules, leader lines |
| `--accent` (Hot PLA) | `#FF5B1F` | `#EE4A0E` | The hero object, primary CTA hover, focus ring, the "print" step. **Max one accent element per viewport.** |
| `--accent-ink` | `#1A0A03` | `#FFFFFF` | Text on accent |
| `--secondary` (Clay) | `#C9BFAE` | `#D8CFBF` | Un-printed / "solid" state of the object, and the neutral clay matcap |
| `--signal` (success) | `#7FD48A` | `#2E8B44` | "Exported", saved states only |
| `--danger` | `#FF6B5E` | `#C8321F` | Auth error text |

Rules: the primary button is ink (never accent). Accent goes on the object first and on UI second. No gradients except the radial "light pool" under an object: `radial-gradient(ellipse at 50% 40%, rgba(255,255,255,.06), transparent 60%)` in midnight, and `rgba(255,255,255,.7)` in porcelain. Delete `--ambient-glow` violet.

## 4. Type system
- **Display serif: Fraunces** (variable, Google). Use axes `opsz` 144, `SOFT` 100, `WONK` 0. The soft axis rounds the terminals so it reads like clay: tactile, not editorial-stiff.
- **Sans: Geist** (keep it). Body text and UI.
- **Mono: Geist Mono**. Specimen labels, dimensions, prompts.

| Role | Font | Desktop / Mobile | Wt | LH | Tracking |
|---|---|---|---|---|---|
| Display (hero) | Fraunces | 112 / 56px | 380 | 0.95 | -0.035em |
| H1 | Fraunces | 72 / 44px | 400 | 1.0 | -0.03em |
| H2 | Fraunces | 48 / 34px | 400 | 1.05 | -0.02em |
| H3 | Geist | 22 / 20px | 550 | 1.25 | -0.015em |
| H4 | Geist | 16 / 16px | 600 | 1.35 | -0.01em |
| Body | Geist | 17 / 16px | 400 | 1.55 | -0.005em |
| Small | Geist | 14 / 14px | 400 | 1.5 | 0 |
| Caption | Geist | 13 / 12px | 450 | 1.4 | 0 |
| Label (mono) | Geist Mono | 11 / 11px | 500 | 1.2 | +0.08em, UPPERCASE |
| Prompt (mono) | Geist Mono | 14 / 13px | 400 | 1.5 | 0, sentence case, in “curly quotes” |

Rules: **serif = what you'd say out loud** (headlines, one italic word max per headline, e.g. *print*). **Sans = what you'd click.** **Mono = what the machine knows** (dimensions, print time, prompts, file types). Never use serif on buttons, and never go below 34px with it.

## 5. Spacing, shape, buttons
- **Spacing:** 4px base. Scale 4, 8, 12, 16, 24, 32, 48, 64, 96, 160, 240. Sections are separated by 160 desktop / 96 mobile. Max text measure 560px. Page gutter 24 / 16.
- **Radii:** `--r-xs 6` (chips), `--r-sm 10` (inputs), `--r-md 16` (cards/plates), `--r-pill 999` (buttons). Nothing larger than 16 except pills.
- **Borders:** 1px `--hairline` only. There are no card borders on the landing page: plates separate from the page by tone (`--surface-sunk`).
- **Shadows:** UI gets none. Objects get two layered contact shadows: `0 1px 0 hairline` for the lip, and a blurred ellipse at 18% opacity that is **baked into the render**, not CSS.
- **Primary button:** pill, 48px tall, 22px padding, `--ink` fill, `--surface` text, Geist 15/550. Hover: fill shifts to `--accent` over 180ms, and a trailing `→` slides 2px. Active: `scale(.98)`.
- **Secondary button:** pill, 1px `--hairline` border, transparent fill, `--ink` text. Hover: bg `color-mix(--ink 6%)`.
- **Ghost button:** text only, `--ink-2`, underline on hover.
- **Links:** `--ink`. Underline is 1px, offset 4px, colour `--hairline`. On hover the underline turns `--accent`, with no colour shift on the text.
- **Focus:** 2px `--accent` ring, 2px offset.

## 6. Landing page (visible words ≈ 95)
```
┌────────────────────────────────────────────────────────────┐
│ nfinit                                   Log in  [Start →] │  wordmark in Fraunces italic, lowercase
├────────────────────────────────────────────────────────────┤
│                                                            │
│            Describe it. Print it tonight.                  │  Display serif, centered, "Print" italic
│                                                            │
│                     ╭────────────╮                         │
│                     │  ORANGE    │  ← phone stand, PLA,    │
│                     │  PHONE     │    resting on surface,  │
│                     │  STAND     │    0.1 rpm turn,        │
│                     ╰────────────╯    pointer tilt ±4°     │
│   ─ ─ 78 mm ─ ─         (soft contact shadow)              │  mono leader-line dims (TE)
│                                                            │
│   “phone stand, 65° tilt, cable slot”   ·   38 MIN · PLA   │  prompt as caption (mono)
│                                                            │
│                 [ Start a part → ]   Log in                │
└────────────────────────────────────────────────────────────┘
 SECTION 2: the flow (sticky, 300vh; object pinned right)
┌────────────────────────────────────────────────────────────┐
│ 01  Describe.                          │                   │
│     Say what it holds.                 │   [object state]  │  prompt types in, letter by letter
│ 02  Refine.                            │                   │  wireframe edges, then click a face (accent highlight)
│     Click a face. Ask for a change.    │                   │  "+4 mm" mono tag flies to that face
│ 03  Print.                             │                   │  clay solid, then layer lines rise bottom-up in orange
│     STL out. On the bed tonight.       │   ▁▁▁▁▁▁ progress │  mono: 38 MIN · 0.2 MM · PLA
└────────────────────────────────────────────────────────────┘
 SECTION 3: the specimen drawer (3×2 grid of plates, 2×3 mobile)
┌──────────┬──────────┬──────────┐   each plate: --surface-sunk, one part,
│ cable    │ hinge    │ 2020     │   mono label top-left  "NO. 004 — HINGE"
│ clip     │          │ bracket  │   prompt as caption under it
├──────────┼──────────┼──────────┤   hover: part turns 25°, colour fills from
│ SD case  │ hose     │ knob     │   clay to a filament colour
│          │ adapter  │          │
└──────────┴──────────┴──────────┘
  H2 above grid: "Things people actually print."
 SECTION 4: formats
┌────────────────────────────────────────────────────────────┐
│   STL for tonight. STEP for later.          [.stl] [.step] │  H2 serif; two chips sit like
│                                                            │  file-tabs on a clay block
└────────────────────────────────────────────────────────────┘
 SECTION 5: closing prompt
┌────────────────────────────────────────────────────────────┐
│               What are you making?                         │  H1 serif
│   ┌──────────────────────────────────────────────┐  [→]    │  real input, placeholder cycles through
│   │ a wall mount for my router, two screw holes… │         │  prompts; submit → /login?next=/studio?prompt=…
│   └──────────────────────────────────────────────┘         │
├────────────────────────────────────────────────────────────┤
│ nfinit · © 2026 · Terms · Privacy        ◐ theme           │
└────────────────────────────────────────────────────────────┘
```
**How to render it cheaply (performance budget)**
- **Hero = pre-rendered, not live.** Make a 96-frame Blender turntable of the stand: AgX view transform, one large softbox and a shadow catcher. Render twice, once per theme background. Ship it as an AV1 plus H.264 `<video muted loop playsinline>`, 1200×900, **≤ 450 KB**, with an AVIF poster of ≤ 60 KB as the LCP element. Handle pointer tilt with CSS `rotateX/Y` on the video wrapper (±4°), so no WebGL is needed above the fold. Swap the source on theme change.
- **Flow section = one lazy r3f scene** (`dynamic(..., {ssr:false})`, mounted by an IntersectionObserver 400px before the section). Build the part procedurally (an extruded shape) so there is no GLB download. Use **one 256px matcap** per theme, so there are no lights, no env map and no shadows to compute. Draw the wireframe with `EdgesGeometry` + `LineSegments`. For layer lines, patch the normal in `onBeforeCompile` (`sin(worldPos.y * 2π / 0.2mm)` bump) and move a clipping-plane height `uPrint` from 0 to 1 as you scroll. Use `dpr={[1,1.5]}` and `frameloop="demand"`, calling `invalidate()` only on scroll or pointer. Pause when the tab is hidden.
- **Specimen plates:** 6 AVIF stills, ~40 KB each, with hover done as a 2-frame crossfade (clay to colour, 0° to 25°). No WebGL.
- **Budget:** LCP < 1.8 s on 4G, initial JS for the landing page < 90 KB gz, three.js chunk (~160 KB gz) only after idle, 60 fps on an M1 and ≥ 45 fps on a Pixel 6a. If `saveData`, `hardwareConcurrency < 4` or `prefers-reduced-motion` is set, the flow section becomes 4 stacked stills.

## 7. Auth page
Split layout at 50/50 on desktop. On mobile it stacks, with the object at 40vh on top.
```
┌──────────────────────────────┬─────────────────────────────┐
│ nfinit                       │                          ◐  │
│                              │                             │
│      [clay hinge, looping    │   Welcome back              │  H1 serif
│       open 0°→110°→0°,       │   to the workbench.         │
│       on surface-sunk]       │                             │
│                              │   [ G  Continue with Google]│  primary (ink)
│   NO. 012 — PRINT-IN-PLACE   │   [ ⌥  Continue with GitHub]│  secondary
│   HINGE · 22 MIN             │                             │
│                              │   New here? Same buttons.   │  caption, muted
└──────────────────────────────┴─────────────────────────────┘
```
- **Copy:** H1 "Welcome back to the workbench." Caption "New here? Same buttons." Footer caption "By continuing you accept the Terms." (link).
- **Loading:** the clicked button keeps its width. The label becomes "Opening Google…" and a 12px orange **print-head dot** moves along the bottom edge of the button (1.2s, linear, infinite). The other button goes to 40% opacity and disabled. The hinge on the left speeds up to 2×.
- **Error:** an inline row above the buttons with a 1px `--danger` left border and the text "That didn't go through. Try again." The raw message goes in `title`/console, never shown to the user. The hinge stops half-open (a small joke, and no red flash). Focus moves to the failed button.
- **Visual:** the hinge is a 48-frame WebM (~200 KB), or a still under reduced motion. There is no violet glow and no Sparkles icon.

## 8. Motion
Base easing `--ease-out: cubic-bezier(.2,.8,.2,1)` and `--ease-io: cubic-bezier(.65,0,.35,1)`.
1. **Turntable idle**: the hero object rotates 360° in 40s, linear. Pointer tilt eases toward target at 0.08 lerp per frame. It stops on hover-hold.
2. **Headline settle**: display lines rise 12px and fade in over 700ms `--ease-out`, staggered by 80ms per line. The object fades in at +200ms with a 1.02 to 1 scale, as if "set down" on the table.
3. **Scroll-scrubbed build** (flow section): prompt typing (0–25%), edges draw in by dash-offset (25–45%), face highlight plus the "+4 mm" tag (45–65%), clay solid (65–75%), orange layers rise under the clipping plane (75–100%). It is scrubbed, never autoplayed, and CSS `animation-timeline: view()` drives the text.
4. **Specimen hover**: a 240ms `--ease-out` crossfade from clay to colour plus 25° rotation.
5. **Button hover**: fill goes to accent over 180ms, and the arrow moves 2px.

**Reduced motion:** no turntable (show the poster still), headline shows instantly, the flow becomes 4 static frames with numbered captions, and hovers use opacity only.

## 9. Don'ts
- No violet, no gradients-as-decoration, no glow blobs, no `backdrop-blur` cards.
- No Sparkles, wand or "AI" pill anywhere. The word "AI" appears 0 times above the fold.
- No fake app window or dashboard screenshot in the hero. The object is the hero.
- No floating gray untextured meshes. Every render is clay or a real filament colour, sitting on a surface with a contact shadow.
- No feature grid of icon + title + 2 lines. No testimonials carousel, no logo wall, no "Trusted by".
- No serif below 34px and no mixing of two serif weights on one line.
- No more than one accent-orange element per viewport.
- No exclamation marks, no "unleash", "supercharge" or "seamless".

## 10. Three strongest ideas
1. **Prompt-as-caption specimen labels**: every object is shown with the exact prompt that made it (mono, in quotes) plus Teenage Engineering-style mono specs (`38 MIN · PLA · 78 MM`). The copy *is* the product demo, and it keeps word count tiny.
2. **One scroll-scrubbed part: prompt → wireframe → face edit → clay → orange layer lines rising.** A matcap r3f scene with a clipping plane and a layer-line normal bump makes this cheap (no GLB, no lights), with a pre-rendered video for the hero and stills as fallback.
3. **"Hot PLA" as the only colour, living on the object**: warm-black and porcelain surfaces, an ink primary button and a filament-orange accent reserved for the part itself. Fraunces SOFT-axis gives a serif that feels moulded. The closing CTA is a real prompt field that carries the prompt through OAuth into the studio.
