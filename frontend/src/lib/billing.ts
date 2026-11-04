import { jsonRequest, requestJson } from "@/lib/projects";

export { SubscriptionRequiredError } from "@/lib/projects";

export type BillingStatus = {
  /** False when the backend has no Stripe keys: everyone has access. */
  enabled: boolean;
  active: boolean;
  status: string;
  currentPeriodEnd: string | null;
  cancelAtPeriodEnd: boolean;
  /** Stripe adds tax at checkout, so the price is shown "+ tax". */
  taxAtCheckout: boolean;
};

export function getBillingStatus(): Promise<BillingStatus> {
  return requestJson("/billing/status");
}

/** Where Stripe should send the user back to: here, minus checkout flags. */
export function currentReturnPath(): string {
  const url = new URL(window.location.href);
  url.searchParams.delete("checkout");
  return `${url.pathname}${url.search}`;
}

export async function startCheckout(returnPath = currentReturnPath()) {
  const { url } = await requestJson<{ url: string }>(
    "/billing/checkout",
    jsonRequest("POST", { returnPath })
  );
  window.location.assign(url);
}

export async function openBillingPortal(returnPath = currentReturnPath()) {
  const { url } = await requestJson<{ url: string }>(
    "/billing/portal",
    jsonRequest("POST", { returnPath })
  );
  window.location.assign(url);
}

// What the user tried to do when the paywall stopped them, replayed once
// Checkout brings them back.
export type PendingAction =
  | { kind: "send"; text: string; images?: string[] }
  | { kind: "export"; format: "step" | "brep" | "stl" };

const PENDING_ACTION_KEY = "nfinit:paywall-pending";

export function savePendingAction(action: PendingAction) {
  try {
    window.sessionStorage.setItem(PENDING_ACTION_KEY, JSON.stringify(action));
  } catch {
    // Attached images can exceed the storage quota; keep the words at least.
    if (action.kind === "send" && action.images) {
      savePendingAction({ kind: "send", text: action.text });
    }
  }
}

export function takePendingAction(): PendingAction | null {
  try {
    const raw = window.sessionStorage.getItem(PENDING_ACTION_KEY);
    window.sessionStorage.removeItem(PENDING_ACTION_KEY);
    return raw ? (JSON.parse(raw) as PendingAction) : null;
  } catch {
    return null;
  }
}

/** Checkout returns before Stripe's webhook lands; wait for it briefly. */
export async function waitForActiveSubscription(
  timeoutMs = 30_000
): Promise<BillingStatus | null> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const status = await getBillingStatus();
      if (status.active) return status;
    } catch {
      // Transient; keep waiting.
    }
    await new Promise((resolve) => setTimeout(resolve, 1_500));
  }
  return null;
}

/** The price as every subscribe button shows it, e.g. "$20/mo + tax". */
export function priceLabel(taxAtCheckout: boolean): string {
  return `$20/mo${taxAtCheckout ? " + tax" : ""}`;
}

/** Billing is on and this user has no plan: offer the subscription. */
export function canSubscribe(status: BillingStatus | null): boolean {
  return Boolean(status?.enabled && !status.active);
}

/** Billing is on and this user has (or had) a plan: Stripe's portal applies. */
export function canManageBilling(status: BillingStatus | null): boolean {
  return Boolean(status?.enabled && status.status !== "none");
}

/** One line about the plan, e.g. "Renews on 30 Nov 2026". */
export function planDetail(status: BillingStatus): string | null {
  if (!status.enabled) return null;
  if (!status.active) return "Demo parts only";
  if (!status.currentPeriodEnd) return "Active";
  const date = new Date(status.currentPeriodEnd).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
  return status.cancelAtPeriodEnd ? `Ends on ${date}` : `Renews on ${date}`;
}
