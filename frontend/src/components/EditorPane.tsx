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
    <div className="flex h-full min-h-0 flex-col border-r border-[#1f1f1f] bg-[#0a0a0a]">
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
      <div className="flex justify-end border-t border-[#1f1f1f] p-3">
        <Button
          onClick={onGenerate}
          className="border-[#1f1f1f] bg-[#0a0a0a] text-zinc-200 hover:bg-[#1a1a1a]"
        >
          <span className="mr-1.5 text-xs text-zinc-500">⌘↵</span>
          Generate
        </Button>
      </div>
    </div>
  );
}
