import Studio from "@/components/Studio";
import type { Metadata } from "next";

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
    demo?: string | string[];
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
  const rawDemo = Array.isArray(params.demo) ? params.demo[0] : params.demo;
  const demo = rawDemo && /^[a-z0-9-]{1,40}$/.test(rawDemo) ? rawDemo : undefined;

  return (
    <Studio
      initialPrompt={prompt}
      initialProjectId={projectId}
      initialDemo={demo}
      startNew={startNew}
    />
  );
}
