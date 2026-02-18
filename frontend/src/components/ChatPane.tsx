"use client";

import { Button } from "@/components/ui/button";
import { useRef, useEffect, useState } from "react";

export type ChatMessage = { role: "user" | "assistant"; content: string };

interface ChatPaneProps {
  messages: ChatMessage[];
  onSend: (content: string) => void;
  isLoading: boolean;
  lastError?: string | null;
}

export function ChatPane({
  messages,
  onSend,
  isLoading,
  lastError,
}: ChatPaneProps) {
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages]);

  const handleSend = () => {
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;
    onSend(trimmed);
    setInput("");
  };

  const handleIncludeError = () => {
    if (lastError) {
      setInput((prev) =>
        prev.trim() ? `${prev}\n\nError:\n${lastError}` : `Fix this error:\n${lastError}`
      );
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col border-l border-[#1f1f1f] bg-[#0a0a0a]">
      <div
        ref={scrollRef}
        className="min-h-0 flex-1 overflow-y-auto p-3 space-y-3"
      >
        {messages.length === 0 && (
          <div className="flex h-full items-center justify-center text-sm text-zinc-500">
            Describe your 3D part or request changes. The conversation history
            will guide the model.
          </div>
        )}
        {messages.map((msg, i) =>
          msg.role === "user" ? (
            <div key={i} className="flex justify-end">
              <div className="max-w-[85%] rounded-lg bg-blue-600/30 px-3 py-2 text-sm text-zinc-200">
                {msg.content}
              </div>
            </div>
          ) : (
            <div key={i} className="flex justify-start">
              <div className="max-w-[85%] rounded-lg border border-[#1f1f1f] bg-[#141414] px-3 py-2">
                <div className="mb-1 text-xs text-zinc-500">Generated code</div>
                <pre className="overflow-x-auto whitespace-pre-wrap break-words text-xs text-zinc-300">
                  {msg.content.slice(0, 200)}
                  {msg.content.length > 200 ? "..." : ""}
                </pre>
              </div>
            </div>
          )
        )}
      </div>
      <div className="flex flex-col gap-2 border-t border-[#1f1f1f] p-3">
        {lastError && (
          <Button
            variant="outline"
            size="sm"
            onClick={handleIncludeError}
            className="w-full border-red-500/50 bg-red-950/20 text-red-200 hover:bg-red-950/40"
          >
            Include last error in message
          </Button>
        )}
        <div className="flex gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            placeholder="Describe changes or paste errors..."
            rows={2}
            disabled={isLoading}
            className="min-h-[60px] flex-1 resize-none rounded-md border border-[#1f1f1f] bg-[#000000] px-3 py-2 text-sm text-zinc-200 placeholder:text-zinc-500 focus:outline-none focus:ring-2 focus:ring-blue-500/50 disabled:opacity-50"
          />
          <Button
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
            className="shrink-0 border-[#1f1f1f] bg-[#0a0a0a] text-zinc-200 hover:bg-[#1a1a1a]"
          >
            Send
          </Button>
        </div>
      </div>
    </div>
  );
}
