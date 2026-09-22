import Studio from "@/components/Studio";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Studio — nfinit",
  description: "Create and refine production-ready 3D parts with AI.",
};

export default function StudioPage() {
  return <Studio />;
}
