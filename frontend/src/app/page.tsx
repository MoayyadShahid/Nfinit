import {
  ArrowUp,
  ArrowUpRight,
  Box,
  Download,
  MousePointer2,
  Sparkles,
} from "lucide-react";
import { ThemeToggle } from "@/components/ThemeToggle";
import Link from "next/link";

function Brand() {
  return (
    <Link
      href="/"
      className="flex items-center gap-2.5"
      aria-label="nfinit home"
    >
      <span className="theme-primary-button flex size-8 items-center justify-center rounded-xl shadow-[0_0_30px_rgba(124,58,237,0.12)]">
        <Sparkles className="size-3.5" strokeWidth={2.2} />
      </span>
      <span className="text-[15px] font-semibold tracking-[-0.025em]">
        nfinit
      </span>
    </Link>
  );
}

function ProductShowcase() {
  return (
    <div className="landing-window porcelain-shadow relative mx-auto w-full max-w-4xl overflow-hidden rounded-[22px] border border-[color:var(--hairline)] bg-[#e9eaed] shadow-[0_35px_100px_rgba(0,0,0,0.5)]">
      <div className="flex h-9 items-center justify-between border-b border-black/8 bg-[#111217] px-3">
        <div className="flex items-center gap-1.5">
          <span className="size-1.5 rounded-full bg-white/20" />
          <span className="size-1.5 rounded-full bg-white/12" />
          <span className="size-1.5 rounded-full bg-white/8" />
        </div>
        <span className="text-[8px] font-medium tracking-[0.12em] text-white/35">
          BRACKET / V4
        </span>
        <div className="flex items-center gap-1 text-[8px] text-white/40">
          <Download className="size-2.5" />
          STEP
        </div>
      </div>

      <div className="product-grid relative aspect-[16/7] min-h-[260px] overflow-hidden sm:min-h-[320px]">
        <div className="absolute left-3 top-3 z-10 rounded-xl border border-white/20 bg-[#121319]/90 px-3 py-2.5 text-white shadow-xl backdrop-blur sm:left-5 sm:top-5">
          <p className="text-[7px] font-medium tracking-[0.15em] text-white/35">
            OVERALL SIZE
          </p>
          <p className="mt-1 text-[10px] font-medium sm:text-xs">
            80 × 48 × 6 mm
          </p>
        </div>

        <div className="absolute right-3 top-3 z-10 hidden max-w-[190px] rounded-xl border border-violet-300/20 bg-[#17131f]/92 p-3 text-white shadow-xl backdrop-blur sm:right-5 sm:top-5 sm:block">
          <div className="flex items-start gap-2.5">
            <span className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-violet-400/15 text-violet-300">
              <MousePointer2 className="size-3.5" />
            </span>
            <div>
              <p className="text-[10px] font-semibold text-violet-100">
                Face selected
              </p>
              <p className="mt-1 text-[8px] leading-3.5 text-white/45">
                Extend this face by 12 mm
              </p>
            </div>
          </div>
        </div>

        <svg
          viewBox="0 0 600 360"
          role="img"
          aria-label="AI-generated mounting bracket"
          className="absolute inset-0 m-auto h-[88%] w-[88%]"
        >
          <defs>
            <linearGradient id="landing-top" x1="0" x2="1" y1="0" y2="1">
              <stop offset="0" stopColor="#8b95a6" />
              <stop offset="1" stopColor="#556070" />
            </linearGradient>
            <linearGradient id="landing-side" x1="0" x2="1" y1="0" y2="1">
              <stop offset="0" stopColor="#303846" />
              <stop offset="1" stopColor="#181d27" />
            </linearGradient>
            <linearGradient id="landing-front" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0" stopColor="#596474" />
              <stop offset="1" stopColor="#313947" />
            </linearGradient>
            <filter id="landing-shadow" x="-50%" y="-50%" width="200%" height="200%">
              <feDropShadow dx="0" dy="24" stdDeviation="18" floodOpacity=".25" />
            </filter>
          </defs>
          <ellipse cx="300" cy="306" rx="150" ry="25" fill="#111827" opacity=".12" />
          <g filter="url(#landing-shadow)">
            <path
              d="M170 235 L352 152 L441 201 L260 286 Z"
              fill="url(#landing-top)"
            />
            <path
              d="M260 286 L441 201 L441 236 L260 321 Z"
              fill="url(#landing-side)"
            />
            <path
              d="M170 235 L260 286 L260 321 L170 269 Z"
              fill="url(#landing-front)"
            />
            <path
              d="M170 235 L170 112 L260 162 L260 286 Z"
              fill="url(#landing-front)"
            />
            <path
              d="M170 112 L352 29 L441 79 L260 162 Z"
              fill="url(#landing-top)"
            />
            <path
              d="M260 162 L441 79 L441 201 L260 286 Z"
              fill="url(#landing-side)"
            />
            <ellipse
              cx="344"
              cy="127"
              rx="41"
              ry="22"
              transform="rotate(-25 344 127)"
              fill="#e9eaed"
              opacity=".96"
            />
            <ellipse
              cx="344"
              cy="127"
              rx="28"
              ry="14"
              transform="rotate(-25 344 127)"
              fill="#202631"
            />
            <ellipse
              cx="220"
              cy="211"
              rx="22"
              ry="13"
              transform="rotate(29 220 211)"
              fill="#1e2530"
            />
          </g>
          <path
            d="M449 196 L490 177"
            stroke="#7c3aed"
            strokeWidth="1.5"
            strokeDasharray="4 4"
          />
          <circle cx="449" cy="196" r="4" fill="#8b5cf6" />
          <text x="497" y="178" fill="#6d28d9" fontSize="9" fontWeight="600">
            +12 mm
          </text>
        </svg>

        <div className="absolute inset-x-3 bottom-3 z-10 mx-auto max-w-xl sm:bottom-5">
          <div className="mb-2 flex justify-center">
            <div className="flex items-center gap-1 rounded-full border border-white/12 bg-[#111217]/90 p-1 text-[8px] text-white/35 shadow-xl backdrop-blur">
              <span className="px-2">v1</span>
              <span className="px-2">v2</span>
              <span className="rounded-full bg-white px-2.5 py-1 text-[#111217]">
                v3
              </span>
              <span className="px-2">v4</span>
            </div>
          </div>
          <div className="flex items-center gap-2 rounded-2xl border border-white/12 bg-[#0e0f13]/94 p-2 pl-4 text-white shadow-2xl backdrop-blur-xl">
            <Sparkles className="size-3 shrink-0 text-violet-400" />
            <span className="min-w-0 flex-1 truncate text-[9px] text-white/55 sm:text-[11px]">
              Add two countersunk mounting holes to the base
            </span>
            <span className="flex size-7 shrink-0 items-center justify-center rounded-xl bg-white text-[#111217]">
              <ArrowUp className="size-3" />
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function LandingPage() {
  return (
    <div className="theme-page relative min-h-dvh overflow-x-hidden selection:bg-violet-400/30 lg:h-dvh lg:overflow-hidden">
      <div className="pointer-events-none absolute inset-0">
        <div
          className="absolute left-1/2 top-[-24rem] h-[42rem] w-[62rem] -translate-x-1/2 rounded-full"
          style={{
            background:
              "radial-gradient(circle, var(--ambient-glow), rgba(37,99,235,0.04) 38%, transparent 70%)",
          }}
        />
        <div className="absolute inset-0 opacity-[0.018] [background-image:url('data:image/svg+xml,%3Csvg_viewBox=%220_0_180_180%22_xmlns=%22http://www.w3.org/2000/svg%22%3E%3Cfilter_id=%22n%22%3E%3CfeTurbulence_type=%22fractalNoise%22_baseFrequency=%22.9%22_numOctaves=%224%22_stitchTiles=%22stitch%22/%3E%3C/filter%3E%3Crect_width=%22100%25%22_height=%22100%25%22_filter=%22url(%23n)%22_opacity=%22.5%22/%3E%3C/svg%3E')]" />
      </div>

      <header className="relative z-20 mx-auto flex h-16 max-w-6xl items-center justify-between px-5 sm:px-8">
        <Brand />
        <div className="flex items-center gap-2">
          <ThemeToggle />
          <Link
            href="/studio"
            className="theme-muted rounded-full px-3 py-2 text-xs font-medium transition-colors hover:text-[var(--page-fg)] sm:px-4"
          >
            Log in
          </Link>
          <Link
            href="/studio"
            className="theme-primary-button flex items-center gap-1.5 rounded-full px-4 py-2 text-xs font-semibold transition-transform hover:scale-[1.02]"
          >
            Open studio
            <ArrowUpRight className="size-3.5" />
          </Link>
        </div>
      </header>

      <main className="relative z-10 mx-auto flex min-h-[calc(100dvh-4rem)] max-w-6xl flex-col items-center px-5 pb-5 pt-[clamp(1.75rem,4.5vh,3rem)] sm:px-8 lg:h-[calc(100dvh-4rem)] lg:min-h-0">
        <div className="mx-auto max-w-3xl text-center">
          <div className="theme-floating theme-muted mb-5 inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-[10px] font-medium tracking-[0.12em]">
            <Box className="size-3 text-violet-400" />
            AI CAD
          </div>
          <h1 className="text-balance text-[clamp(2.8rem,6vw,5.2rem)] font-semibold leading-[0.94] tracking-[-0.065em]">
            Ideas become objects.
          </h1>
          <p className="theme-muted mx-auto mt-5 max-w-xl text-balance text-sm tracking-[-0.01em] sm:text-base">
            Describe it. Refine it. Export real CAD.
          </p>
          <Link
            href="/studio"
            className="theme-primary-button group mx-auto mt-7 inline-flex h-11 items-center gap-2 rounded-full px-5 text-sm font-semibold shadow-[0_12px_40px_rgba(124,58,237,0.08)] transition-transform hover:scale-[1.02]"
          >
            Start designing
            <ArrowUpRight className="size-4 transition-transform group-hover:translate-x-0.5 group-hover:-translate-y-0.5" />
          </Link>
        </div>

        <div className="mt-[clamp(2rem,4vh,2.75rem)] w-full">
          <ProductShowcase />
        </div>
      </main>
    </div>
  );
}
