/**
 * Facts the Terms of Service and Privacy Policy depend on. Change them here,
 * not in the pages. When a value changes in a way that matters to users,
 * update EFFECTIVE_DATE and tell subscribers by email.
 */
export const LEGAL = {
  serviceName: "Nfinit",
  /** The person or company that runs Nfinit and signs the contract. */
  operator: "[OPERATOR NAME]",
  /** Where users send privacy requests, billing problems and legal notices. */
  contactEmail: "[CONTACT EMAIL]",
  /** The US state whose law governs the Terms, for example "New York". */
  governingState: "[STATE]",
  effectiveDate: "October 13, 2026",
  minimumAge: 13,
  monthlyPrice: "$20",
  appUrl: "https://nfinit.dev",
} as const;

/** Every value is filled in: no "[...]" placeholder remains. */
export const LEGAL_IS_COMPLETE = Object.values(LEGAL).every(
  (value) => typeof value !== "string" || !value.startsWith("[")
);
