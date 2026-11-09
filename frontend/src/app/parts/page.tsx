import { PartsGallery } from "@/components/PartsGallery";
import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Your parts — nfinit",
  description: "Every part you have made, ready to open, refine or export.",
};
export const dynamic = "force-dynamic";

export default function PartsPage() {
  return <PartsGallery />;
}
