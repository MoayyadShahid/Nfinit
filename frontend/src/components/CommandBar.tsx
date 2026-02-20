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
import { Box, Code2, LayoutGrid } from "lucide-react";

interface CommandBarProps {
  modelId: string;
  onModelChange: (modelId: string) => void;
  layoutMode: LayoutMode;
  onLayoutChange: (mode: LayoutMode) => void;
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
}: CommandBarProps) {
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
      <div className="flex flex-1" />
    </header>
  );
}
