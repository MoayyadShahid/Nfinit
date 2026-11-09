/**
 * The public website is a read-only demo: it replays the demo parts and has
 * no backend. A build on Vercel (or with NFNIT_DEMO_ONLY=true) is that demo;
 * `npm run local` builds the full studio. Set in next.config.ts.
 */
export const DEMO_ONLY = process.env.NEXT_PUBLIC_NFNIT_DEMO_ONLY === "true";

export const SOURCE_URL = "https://github.com/MoayyadShahid/Nfinit";
export const RUN_LOCALLY_URL = `${SOURCE_URL}#quick-start`;
