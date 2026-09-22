import Studio from "@/components/Studio";
import { isSupabaseConfigured } from "@/lib/supabase/config";
import { getAuthenticatedUser } from "@/lib/supabase/server";
import type { Metadata } from "next";
import { redirect } from "next/navigation";

export const metadata: Metadata = {
  title: "Studio — nfinit",
  description: "Create and refine production-ready 3D parts with AI.",
};
export const dynamic = "force-dynamic";

export default async function StudioPage() {
  const user = await getAuthenticatedUser();
  if (isSupabaseConfigured() && !user) {
    redirect("/login?next=/studio");
  }

  return (
    <Studio
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
