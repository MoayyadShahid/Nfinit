"use client";

import { getBillingStatus, type BillingStatus } from "@/lib/billing";
import { useEffect, useState } from "react";

/** The signed-in user's plan, or null while it loads or if it cannot load. */
export function useBillingStatus(): BillingStatus | null {
  const [status, setStatus] = useState<BillingStatus | null>(null);
  useEffect(() => {
    let active = true;
    getBillingStatus()
      .then((value) => {
        if (active) setStatus(value);
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);
  return status;
}
