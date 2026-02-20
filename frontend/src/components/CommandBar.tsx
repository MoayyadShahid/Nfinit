"use client";

import type { LayoutMode } from "@/app/page";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { MODELS } from "@/lib/constants";
import { Box, ChevronDown, Code2, Download, LayoutGrid } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

const EXPORT_FORMATS = [
  { id: "step", label: "STEP", ext: ".step", desc: "CAD (Fusion, SolidWorks, Onshape)" },
  { id: "brep", label: "BREP", ext: ".brep", desc: "OpenCASCADE tools" },
  { id: "stl", label: "STL", ext: ".stl", desc: "3D printing" },
] as const;

export type ExportFormat = (typeof EXPORT_FORMATS)[number]["id"];

interface CommandBarProps {
  modelId: string;
  onModelChange: (modelId: string) => void;
  layoutMode: LayoutMode;
  onLayoutChange: (mode: LayoutMode) => void;
  code: string;
  onExport: (format: ExportFormat) => void;
}

const LAYOUT_OPTIONS: { mode: LayoutMode; label: string; icon: typeof LayoutGrid }[] = [
  { mode: "default", label: "Default", icon: LayoutGrid },
  { mode: "code", label: "Code", icon: Code2 },
  { mode: "mesh", label: "Mesh", icon: Box },
];

export function CommandBar({
  modelId,
  onModelChange,
  layoutMode,
  onLayoutChange,
  code,
  onExport,
}: CommandBarProps) {
  const [exportOpen, setExportOpen] = useState(false);
  const exportRef = useRef<HTMLDivElement>(null);

  const handleExportClick = useCallback(
    (format: ExportFormat) => {
      onExport(format);
      setExportOpen(false);
    },
    [onExport]
  );

  useEffect(() => {
    if (!exportOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (exportRef.current && !exportRef.current.contains(e.target as Node)) {
        setExportOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [exportOpen]);

  return (
    <header className="flex h-12 shrink-0 items-center border-b border-[#1f1f1f] bg-[#0a0a0a] px-4">
      <div className="flex flex-1 items-center gap-3">
        <span className="text-sm font-medium text-zinc-400">nfinit</span>
        <Select value={modelId} onValueChange={onModelChange}>
          <SelectTrigger className="h-8 w-[200px] border-[#1f1f1f] bg-transparent text-sm text-zinc-200">
            <SelectValue placeholder="Select model" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={MODELS.DEEPSEEK_V3_2}>DeepSeek V3.2</SelectItem>
            <SelectItem value={MODELS.CLAUDE_OPUS_4_6}>Claude Opus 4.6</SelectItem>
            <SelectItem value={MODELS.MINIMAX_M2_5}>Minimax 2.5</SelectItem>
          </SelectContent>
        </Select>
      </div>
      <div className="flex flex-1 items-center justify-center">
        <div className="flex rounded-lg border border-zinc-700 bg-[#0a0a0a] p-0.5">
          {LAYOUT_OPTIONS.map(({ mode, label, icon: Icon }) => (
            <button
              key={mode}
              type="button"
              onClick={() => onLayoutChange(mode)}
              title={label}
              className={cn(
                "flex h-7 items-center gap-1.5 rounded-md px-3 text-xs font-medium transition-colors",
                layoutMode === mode
                  ? "border border-zinc-600 bg-zinc-800 text-zinc-100"
                  : "border border-transparent text-zinc-500 hover:border-zinc-700 hover:bg-zinc-800/50 hover:text-zinc-300"
              )}
            >
              <Icon className="size-3.5" />
              <span>{label}</span>
            </button>
          ))}
        </div>
      </div>
      <div className="flex flex-1 items-center justify-end">
        <div className="relative" ref={exportRef}>
          <button
            type="button"
            onClick={() => setExportOpen((o) => !o)}
            className="flex h-8 items-center gap-1.5 rounded-md border border-zinc-700 bg-transparent px-3 text-xs font-medium text-zinc-300 hover:border-zinc-600 hover:bg-zinc-800/50 hover:text-zinc-100"
          >
            <Download className="size-3.5" />
            Export
            <ChevronDown
              className={cn("size-3.5 transition-transform", exportOpen && "rotate-180")}
            />
          </button>
          {exportOpen && (
            <div className="absolute right-0 top-full z-50 mt-1 min-w-[220px] rounded-md border border-zinc-700 bg-[#141414] py-1 shadow-lg">
              {EXPORT_FORMATS.map(({ id, label, ext, desc }) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => handleExportClick(id)}
                  className="flex w-full flex-col items-start gap-0.5 px-3 py-2 text-left text-xs hover:bg-zinc-800"
                >
                  <span className="font-medium text-zinc-100">
                    {label} {ext}
                  </span>
                  <span className="text-[10px] text-zinc-500">{desc}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
