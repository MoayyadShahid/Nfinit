"use client";

import { Button } from "@/components/ui/button";
import dynamic from "next/dynamic";
import { useEffect, useState } from "react";

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
  const [editorTheme, setEditorTheme] = useState<"vs" | "vs-dark">("vs-dark");

  useEffect(() => {
    const syncTheme = () => {
      setEditorTheme(
        document.documentElement.dataset.theme === "porcelain" ? "vs" : "vs-dark"
      );
    };
    syncTheme();
    window.addEventListener("nfinit-theme-change", syncTheme);
    return () => window.removeEventListener("nfinit-theme-change", syncTheme);
  }, []);

  return (
    <div className="theme-floating flex h-full min-h-0 flex-col">
      <div className="min-h-0 flex-1 overflow-hidden">
        <MonacoEditor
          height="100%"
          language="python"
          theme={editorTheme}
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
            <div className="theme-inset flex h-full items-center justify-center text-zinc-500">
              Loading editor...
            </div>
          }
        />
      </div>
      <div className="flex items-center justify-between border-t border-[var(--hairline)] px-4 py-3">
        <p className="text-[10px] text-zinc-600">
          Preview changes before saving a revision.
        </p>
        <Button
          onClick={onGenerate}
          className="theme-primary-button rounded-lg"
        >
          <span className="mr-1.5 text-xs text-zinc-400">⌥↵</span>
          Generate
        </Button>
      </div>
    </div>
  );
}
