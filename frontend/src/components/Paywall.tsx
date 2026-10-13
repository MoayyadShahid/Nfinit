"use client";

import { startCheckout } from "@/lib/billing";
import { X } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

export type PaywallReason = "build" | "export";

const COPY: Record<PaywallReason, { title: ReactNode; body: string }> = {
  build: {
    title: (
      <>
        Your <em>turn.</em>
      </>
    ),
    body: "You've seen how it's built. Now describe yours.",
  },
  export: {
    title: (
      <>
        Take it into the <em>real world.</em>
      </>
    ),
    body: "Export any part you build as STL or STEP — ready for printing or your CAD tool.",
  },
};

/**
 * The subscription offer, shown only when someone tries to build or export.
 * The caller saves what they were doing first, so Checkout can resume it.
 */
export function Paywall({
  reason,
  onClose,
}: {
  reason: PaywallReason | null;
  onClose: () => void;
}) {
  // Remounted on every opening, so a past checkout error never lingers.
  return reason ? <PaywallPanel reason={reason} onClose={onClose} /> : null;
}

function PaywallPanel({
  reason,
  onClose,
}: {
  reason: PaywallReason;
  onClose: () => void;
}) {
  const [isStarting, setIsStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const copy = COPY[reason];

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  const subscribe = async () => {
    setIsStarting(true);
    setError(null);
    try {
      await startCheckout();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not open checkout.");
      setIsStarting(false);
    }
  };

  return (
    <div className="pointer-events-none fixed inset-x-0 bottom-0 z-[60] flex justify-center p-3 sm:p-5">
      <section
        role="dialog"
        aria-labelledby="paywall-title"
        className="wb-paywall theme-floating pointer-events-auto relative w-full max-w-md rounded-2xl border p-6 shadow-2xl shadow-black/25 backdrop-blur-xl"
      >
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="theme-control absolute right-3 top-3 rounded-lg p-2 text-[var(--muted)] hover:text-[var(--ink)]"
        >
          <X className="size-4" />
        </button>
        <h2 id="paywall-title" className="type-h3 pr-8">
          {copy.title}
        </h2>
        <p className="mt-2 text-[15px] leading-6 text-[var(--ink-2)]">{copy.body}</p>
        <button
          type="button"
          onClick={subscribe}
          disabled={isStarting}
          className="wb-btn wb-btn-primary mt-6 w-full justify-center"
        >
          {isStarting ? "Opening checkout…" : "Start building — $20/mo + tax"}
        </button>
        {/* Auto-renewal laws require these terms next to the subscribe button. */}
        <p className="mt-3 text-center text-xs leading-5 text-[var(--muted)]">
          Renews every month until you cancel. Cancel anytime with the Billing button.
          By subscribing, you agree to the{" "}
          <a href="/terms" target="_blank" rel="noopener" className="underline underline-offset-2">
            Terms of Service
          </a>{" "}
          and{" "}
          <a href="/privacy" target="_blank" rel="noopener" className="underline underline-offset-2">
            Privacy Policy
          </a>
          .
        </p>
        {error && (
          <p role="alert" className="mt-2 text-center text-xs text-[var(--danger)]">
            {error}
          </p>
        )}
      </section>
    </div>
  );
}
