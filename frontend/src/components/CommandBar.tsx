"use client";

import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { DEFAULT_MODEL, MODELS } from "@/lib/constants";
import { Loader2 } from "lucide-react";

interface CommandBarProps {
  modelId: string;
  onModelChange: (modelId: string) => void;
  onGenerate: () => void;
  isLoading: boolean;
}

export function CommandBar({
  modelId,
  onModelChange,
  onGenerate,
  isLoading,
}: CommandBarProps) {
  return (
    <header className="flex h-12 shrink-0 items-center justify-between border-b border-[#1f1f1f] bg-[#0a0a0a] px-4">
      <div className="flex items-center gap-3">
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
      <div className="flex items-center gap-2">
        <span className="text-xs text-zinc-500">⌘↵</span>
        <Button
          size="sm"
          onClick={onGenerate}
          disabled={isLoading}
          className="border-[#1f1f1f] bg-[#0a0a0a] text-zinc-200 hover:bg-[#1a1a1a] hover:text-white focus-visible:ring-blue-500/50"
        >
          {isLoading ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            "Generate"
          )}
        </Button>
      </div>
    </header>
  );
}
