function normalizeSupabaseUrl(value: string | undefined): string | undefined {
  const trimmed = value?.trim();
  if (!trimmed) return undefined;
  return trimmed.replace(/\/rest\/v1\/?$/i, "").replace(/\/$/, "");
}

const supabaseUrl = normalizeSupabaseUrl(process.env.NEXT_PUBLIC_SUPABASE_URL);
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY?.trim();
const previewCanUseData =
  process.env.NEXT_PUBLIC_NFNIT_PREVIEW_ISOLATED?.trim().toLowerCase() === "true";

function previewDataIsBlocked(): boolean {
  return (
    process.env.NEXT_PUBLIC_NFNIT_VERCEL_ENV === "preview" && !previewCanUseData
  );
}

export function isSupabaseConfigured(): boolean {
  return !previewDataIsBlocked() && Boolean(supabaseUrl && supabaseAnonKey);
}

export function getSupabaseConfig() {
  if (previewDataIsBlocked() || !supabaseUrl || !supabaseAnonKey) {
    throw new Error("Supabase authentication is not configured.");
  }

  return {
    url: supabaseUrl,
    anonKey: supabaseAnonKey,
  };
}
