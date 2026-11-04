"use client";

import { priceLabel, startCheckout } from "@/lib/billing";
import { cn } from "@/lib/utils";
import { Sparkles } from "lucide-react";
import { useState } from "react";

/**
 * The one way to start the subscription, used by the paywall, the toolbars,
 * the account menu and the Account page, so it reads and behaves the same
 * everywhere. It opens Stripe Checkout and comes back to this page.
 */
export function SubscribeButton({
  size = "md",
  taxAtCheckout = false,
  className,
  onError,
}: {
  /** "sm" fits a toolbar; "md" a menu or a page; "lg" the paywall. */
  size?: "sm" | "md" | "lg";
  taxAtCheckout?: boolean;
  className?: string;
  /** Without it, the error shows under the button. */
  onError?: (message: string) => void;
}) {
  const [isStarting, setIsStarting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const subscribe = async () => {
    setIsStarting(true);
    setError(null);
    try {
      await startCheckout();
    } catch (e) {
      const message = e instanceof Error ? e.message : "Could not open checkout.";
      if (onError) onError(message);
      else setError(message);
      setIsStarting(false);
    }
  };

  const price = priceLabel(taxAtCheckout);
  return (
    // In a toolbar it hides on phones (the account menu has it) and drops its
    // label until there is room, like the toolbar's other buttons.
    <span
      className={cn(size === "sm" ? "hidden sm:flex" : "flex w-full", "flex-col", className)}
    >
      <button
        type="button"
        onClick={subscribe}
        disabled={isStarting}
        aria-busy={isStarting}
        title={size === "sm" ? `Start building · ${price}` : undefined}
        aria-label={size === "sm" ? `Start building, ${price}` : undefined}
        className={cn(
          "flex items-center justify-center gap-1.5 font-semibold transition-transform hover:scale-[1.02] disabled:cursor-wait disabled:opacity-70 disabled:hover:scale-100",
          // In a toolbar it sits next to the toolbar's own primary button
          // (Export, New part), so it uses the accent instead of competing.
          size === "sm"
            ? "h-9 whitespace-nowrap rounded-lg border border-[var(--accent)]/35 bg-[var(--accent)]/10 px-2.5 text-xs text-[var(--accent)] hover:bg-[var(--accent)]/15 xl:px-3.5"
            : "theme-primary-button shadow-sm",
          size === "md" && "h-10 w-full rounded-lg px-4 text-sm",
          size === "lg" && "h-12 w-full rounded-xl px-5 text-[15px]"
        )}
      >
        <Sparkles className={size === "lg" ? "size-4" : "size-3.5"} />
        {isStarting ? (
          "Opening checkout…"
        ) : size === "sm" ? (
          <span className="hidden xl:inline">Start building</span>
        ) : (
          <>
            Start building
            <span className="font-normal opacity-70">· {price}</span>
          </>
        )}
      </button>
      {error && (
        <span role="alert" className="mt-2 text-center text-xs text-[var(--danger)]">
          {error}
        </span>
      )}
    </span>
  );
}
