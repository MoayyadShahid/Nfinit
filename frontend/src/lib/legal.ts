/**
 * Facts the Terms of Service and Privacy Policy depend on. Change them here,
 * not in the pages. When a value changes in a way that matters to users,
 * update effectiveDate and tell subscribers by email.
 */
export const LEGAL = {
  serviceName: "Nfinit",
  /** The person or company that runs Nfinit and signs the contract. */
  operator: "Moayyad Shahid",
  /** Where the operator is based. */
  location: "Toronto, Ontario, Canada",
  /** Where users send privacy requests, billing problems and legal notices. */
  contactEmail: "muayyad.shahid1@gmail.com",
  /** The person accountable for personal information (PIPEDA, Quebec Law 25). */
  privacyOfficer: "Moayyad Shahid",
  /** The law that governs the Terms, and the courts for disputes. */
  governingLaw: "the Province of Ontario and the federal laws of Canada that apply there",
  courts: "Toronto, Ontario",
  effectiveDate: "October 28, 2026",
  minimumAge: 13,
  monthlyPrice: "US$20",
  appUrl: "https://nfinit.dev",
} as const;

/** Every value is filled in: no "[...]" placeholder remains. */
export const LEGAL_IS_COMPLETE = Object.values(LEGAL).every(
  (value) => typeof value !== "string" || !value.startsWith("[")
);
