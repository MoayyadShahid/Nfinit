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
  searchParams: Promise<{
    prompt?: string | string[];
    project?: string | string[];
    new?: string | string[];
  }>;
}) {
  const params = await searchParams;
  const rawPrompt = Array.isArray(params.prompt) ? params.prompt[0] : params.prompt;
  const prompt = rawPrompt?.trim().slice(0, 500) || undefined;
  const rawProject = Array.isArray(params.project)
    ? params.project[0]
    : params.project;
  const projectId = rawProject?.trim().slice(0, 100) || undefined;
  const startNew = (Array.isArray(params.new) ? params.new[0] : params.new) === "1";

  const user = await getAuthenticatedUser();
  if (isSupabaseConfigured() && !user) {
    // Keep a prompt typed on the landing page through sign-in.
    const query = new URLSearchParams();
    if (prompt) query.set("prompt", prompt);
    if (projectId) query.set("project", projectId);
    const next = query.size ? `/studio?${query}` : "/studio";
    redirect(`/login?next=${encodeURIComponent(next)}`);
  }

  return (
    <Studio
      initialPrompt={prompt}
      initialProjectId={projectId}
      startNew={startNew}
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
