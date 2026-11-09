"use client";

import { useRef, useState } from "react";
import { FileUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectGroup, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { jsonRequest, requestJson } from "@/lib/projects";
import type { MeshReference, ModelInspection } from "@/lib/types";

export type ImportedReference = {
  reference: MeshReference;
  code: string;
  views: string[];
  inspection: ModelInspection | null;
};

export function ReferenceImport({ disabled, onImport }: {
  disabled: boolean;
  onImport: (source: ImportedReference) => Promise<void>;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [units, setUnits] = useState<"mm" | "in">("mm");
  const [mode, setMode] = useState<"preserve" | "reconstruct">("preserve");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function importFile(file: File) {
    setError(null);
    if (!file.name.toLowerCase().endsWith(".stl") || file.size > 10 * 1024 * 1024) {
      setError("Choose an STL file up to 10 MB.");
      return;
    }
    setBusy(true);
    try {
      const data = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result).split(",", 2)[1]);
        reader.onerror = () => reject(new Error("Could not read this STL."));
        reader.readAsDataURL(file);
      });
      const result = await requestJson<Omit<ImportedReference, "reference"> & { facts: MeshReference["facts"] }>(
        "/cad/import-stl", jsonRequest("POST", { data, units, mode })
      );
      await onImport({ ...result, reference: { name: file.name, data, units, mode, facts: result.facts } });
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not import this STL.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <input ref={input} type="file" accept=".stl" className="hidden" aria-label="Import STL file"
          onChange={(event) => {
            const file = event.target.files?.[0];
            event.target.value = "";
            if (file) void importFile(file);
          }} />
        <Select value={units} onValueChange={(value) => setUnits(value as "mm" | "in")} disabled={busy || disabled}>
          <SelectTrigger aria-label="STL source units" className="w-24"><SelectValue /></SelectTrigger>
          <SelectContent><SelectGroup><SelectItem value="mm">mm</SelectItem><SelectItem value="in">inches</SelectItem></SelectGroup></SelectContent>
        </Select>
        <Select value={mode} onValueChange={(value) => setMode(value as "preserve" | "reconstruct")} disabled={busy || disabled}>
          <SelectTrigger aria-label="STL import method" className="w-48"><SelectValue /></SelectTrigger>
          <SelectContent><SelectGroup><SelectItem value="preserve">Preserve mesh</SelectItem><SelectItem value="reconstruct">Reconstruct from reference</SelectItem></SelectGroup></SelectContent>
        </Select>
        <Button variant="outline" size="sm" disabled={busy || disabled} onClick={() => input.current?.click()}>
          <FileUp data-icon="inline-start" />{busy ? "Importing…" : "Import STL"}
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        {mode === "preserve" ? "Closed meshes up to 2,000 triangles become faceted solids you can build on."
          : "Up to 100,000 triangles. AI creates an approximate editable model from measured bounds and three views."}
        {" "}Confirm the units: STL files do not store them. The original is kept in a new project.
      </p>
      {error ? <p role="alert" className="text-xs text-destructive">{error}</p> : null}
    </div>
  );
}
