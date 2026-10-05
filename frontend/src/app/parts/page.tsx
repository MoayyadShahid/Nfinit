import { PartsGallery } from "@/components/PartsGallery";
import { isSupabaseConfigured } from "@/lib/supabase/config";
import { getAuthenticatedUser } from "@/lib/supabase/server";
import type { Metadata } from "next";
import { redirect } from "next/navigation";

export const metadata: Metadata = {
  title: "Your parts — nfinit",
  description: "Every part you have made, ready to open, refine or export.",
};
export const dynamic = "force-dynamic";

export default async function PartsPage() {
  const user = await getAuthenticatedUser();
  if (isSupabaseConfigured() && !user) {
    redirect(`/login?next=${encodeURIComponent("/parts")}`);
  }

  return (
    <PartsGallery
      viewer={
        user
          ? {
              email: user.email ?? null,
              name:
                user.user_metadata.full_name ??
                user.user_metadata.name ??
                user.email ??
                null,
              avatarUrl: user.user_metadata.avatar_url ?? null,
            }
          : null
      }
    />
  );
}
