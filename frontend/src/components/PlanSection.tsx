"use client";

import { SubscribeButton } from "@/components/SubscribeButton";
import {
  canManageBilling,
  canSubscribe,
  openBillingPortal,
  planDetail,
} from "@/lib/billing";
import { useBillingStatus } from "@/lib/useBillingStatus";
import { CreditCard } from "lucide-react";
import { useState } from "react";

/** The Account page's plan: what the user has, and the one button to change it. */
export function PlanSection() {
  const billing = useBillingStatus();
  const [error, setError] = useState<string | null>(null);
  if (!billing?.enabled) return null;

  const subscribed = billing.active;
  const manage = () => {
    setError(null);
    openBillingPortal().catch((e) =>
      setError(e instanceof Error ? e.message : "Could not open billing.")
    );
  };

  return (
    <section aria-labelledby="plan-title" className="theme-floating mt-10 rounded-2xl border p-6">
      <div className="flex flex-wrap items-center gap-3">
        <h2 id="plan-title" className="text-lg font-semibold text-[var(--ink)]">
          Plan
        </h2>
        <span
          className={`rounded-full px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.12em] ${
            subscribed
              ? "bg-[var(--accent)]/15 text-[var(--accent)]"
              : "bg-[var(--clay)] text-[var(--ink-2)]"
          }`}
        >
          {subscribed ? "Subscribed" : "Free"}
        </span>
      </div>
      <p className="mt-2 text-[15px] leading-6 text-[var(--ink-2)]">
        {subscribed
          ? `${planDetail(billing)}. Manage billing opens Stripe, where you can change your card, see invoices or cancel.`
          : "Build, edit and export your own parts with the subscription. Renews every month until you cancel."}
      </p>
      <div className="mt-5 max-w-xs">
        {canSubscribe(billing) && <SubscribeButton size="md" taxAtCheckout={billing.taxAtCheckout} />}
        {canManageBilling(billing) && (
          <button
            type="button"
            onClick={manage}
            className="theme-control flex h-10 w-full items-center justify-center gap-1.5 rounded-lg border border-[var(--hairline-strong)] px-4 text-sm font-medium text-[var(--ink)]"
          >
            <CreditCard className="size-4" />
            Manage billing
          </button>
        )}
        {error && (
          <p role="alert" className="mt-2 text-xs text-[var(--danger)]">
            {error}
          </p>
        )}
      </div>
    </section>
  );
}
