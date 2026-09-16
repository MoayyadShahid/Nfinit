"use client";

import { Button } from "@/components/ui/button";
import dynamic from "next/dynamic";

const MonacoEditor = dynamic(
  () => import("@monaco-editor/react").then((mod) => mod.Editor),
  { ssr: false }
);

interface EditorPaneProps {
  code: string;
  onCodeChange: (value: string) => void;
  onGenerate: () => void;
}

export function EditorPane({
  code,
  onCodeChange,
  onGenerate,
}: EditorPaneProps) {
  return (
    <div className="flex h-full min-h-0 flex-col bg-[#0d0e12]">
      <div className="min-h-0 flex-1 overflow-hidden">
        <MonacoEditor
          height="100%"
          language="python"
          theme="vs-dark"
          value={code}
          onChange={(value) => onCodeChange(value ?? "")}
          options={{
            minimap: { enabled: false },
            fontSize: 13,
            padding: { top: 16 },
            scrollBeyondLastLine: false,
            lineNumbers: "on",
          }}
          loading={
            <div className="flex h-full items-center justify-center bg-[#0a0a0a] text-zinc-500">
              Loading editor...
            </div>
          }
        />
      </div>
      <div className="flex items-center justify-between border-t border-white/8 px-4 py-3">
        <p className="text-[10px] text-zinc-600">
          Preview changes before saving a revision.
        </p>
        <Button
          onClick={onGenerate}
          className="rounded-lg bg-white text-zinc-950 hover:bg-zinc-200"
        >
          <span className="mr-1.5 text-xs text-zinc-400">⌥↵</span>
          Generate
        </Button>
      </div>
    </div>
  );
}
