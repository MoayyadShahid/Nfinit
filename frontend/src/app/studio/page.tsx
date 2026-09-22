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

export default async function StudioPage({
  searchParams,
}: {
  searchParams: Promise<{ prompt?: string | string[] }>;
}) {
  const params = await searchParams;
  const rawPrompt = Array.isArray(params.prompt) ? params.prompt[0] : params.prompt;
  const prompt = rawPrompt?.trim().slice(0, 500) || undefined;

  const user = await getAuthenticatedUser();
  if (isSupabaseConfigured() && !user) {
    // Keep a prompt typed on the landing page through sign-in.
    const next = prompt ? `/studio?prompt=${encodeURIComponent(prompt)}` : "/studio";
    redirect(`/login?next=${encodeURIComponent(next)}`);
  }

  return (
    <Studio
      initialPrompt={prompt}
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
