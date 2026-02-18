"use client";

import { ChatPane, type ChatMessage } from "@/components/ChatPane";
import { CommandBar } from "@/components/CommandBar";
import { EditorPane } from "@/components/EditorPane";
import { ViewportPane } from "@/components/ViewportPane";
import { DEFAULT_MODEL } from "@/lib/constants";
import { useCallback, useEffect, useState } from "react";

const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

export default function Home() {
  const [code, setCode] = useState(
    '# Example: type a prompt in chat and press Send, or edit and press Generate\nfrom build123d import *\n\nwith BuildPart() as part:\n    Box(10, 10, 10)\n\nresult = part.part'
  );
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [modelId, setModelId] = useState<string>(DEFAULT_MODEL);
  const [glbUrl, setGlbUrl] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const generateMesh = useCallback(async (codeToExecute: string) => {
    setError(null);
    try {
      const res = await fetch(`${BACKEND_URL}/generate-mesh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: codeToExecute }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || "Failed to generate mesh");
      }

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      setGlbUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return url;
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Mesh generation failed");
    } finally {
      setIsLoading(false);
    }
  }, []);

  const handleChatSend = useCallback(
    async (content: string) => {
      if (!content.trim()) return;

      setIsLoading(true);
      setError(null);

      const newMessages: ChatMessage[] = [
        ...messages,
        { role: "user", content: content.trim() },
      ];
      setMessages(newMessages);

      try {
        const res = await fetch("/api/generate-code", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            messages: newMessages,
            code,
            modelId,
          }),
        });

        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "Failed to generate code");

        const generatedCode = data.code;
        setCode(generatedCode);
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: generatedCode },
        ]);
        await generateMesh(generatedCode);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Generation failed");
        setMessages((prev) => prev.slice(0, -1));
      } finally {
        setIsLoading(false);
      }
    },
    [messages, code, modelId, generateMesh]
  );

  const handleGenerate = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    await generateMesh(code);
  }, [code, generateMesh]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
        e.preventDefault();
        handleGenerate();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [handleGenerate]);

  useEffect(() => {
    return () => {
      if (glbUrl) URL.revokeObjectURL(glbUrl);
    };
  }, [glbUrl]);

  return (
    <div className="flex h-screen flex-col bg-[#000000] text-zinc-200">
      <CommandBar
        modelId={modelId}
        onModelChange={setModelId}
        onGenerate={handleGenerate}
        isLoading={isLoading}
      />
      <div className="grid min-h-0 flex-1 grid-cols-1 overflow-hidden md:grid-cols-[1fr_1.2fr_1fr]">
        <div className="flex min-h-[200px] flex-col overflow-hidden md:min-h-0">
          <EditorPane
            code={code}
            onCodeChange={setCode}
            onGenerate={handleGenerate}
          />
        </div>
        <div className="relative min-h-[200px] overflow-hidden md:min-h-0">
          {error && (
            <div className="absolute left-4 right-4 top-4 z-20 flex items-start justify-between gap-3 rounded border border-red-500/50 bg-red-950/80 px-3 py-2 text-sm text-red-200">
              <span className="flex-1">{error}</span>
              <button
                type="button"
                onClick={() => {
                  navigator.clipboard.writeText(error);
                }}
                className="shrink-0 rounded px-2 py-1 text-xs hover:bg-red-900/50"
              >
                Copy
              </button>
            </div>
          )}
          <ViewportPane glbUrl={glbUrl} isLoading={isLoading} />
        </div>
        <div className="flex min-h-[200px] flex-col overflow-hidden md:min-h-0">
          <ChatPane
            messages={messages}
            onSend={handleChatSend}
            isLoading={isLoading}
            lastError={error}
          />
        </div>
      </div>
    </div>
  );
}
