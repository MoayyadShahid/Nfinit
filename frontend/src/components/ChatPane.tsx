"use client";

import { Button } from "@/components/ui/button";
import {
  type ChatMessage,
  type FaceSelection,
  getTextContent,
  getImageUrls,
} from "@/lib/types";
import {
  ArrowUp,
  Check,
  ChevronDown,
  ImagePlus,
  MapPin,
  MessagesSquare,
  RotateCcw,
  Sparkles,
  X,
} from "lucide-react";
import { useRef, useEffect, useState, useCallback } from "react";

export type { ChatMessage } from "@/lib/types";

const MAX_IMAGE_SIZE = 10 * 1024 * 1024;
const ACCEPTED_TYPES = ["image/jpeg", "image/png", "image/gif", "image/webp"];

function fileToDataUrl(file: File): Promise<string> {
  if (!ACCEPTED_TYPES.includes(file.type)) {
    return Promise.reject(new Error(`Unsupported image type: ${file.type}`));
  }
  if (file.size > MAX_IMAGE_SIZE) {
    return Promise.reject(new Error("Image too large (max 10 MB)"));
  }
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

interface ChatPaneProps {
  messages: ChatMessage[];
  onSend: (text: string, images?: string[]) => void;
  isLoading: boolean;
  lastError?: string | null;
  supportsVision?: boolean;
  selection?: FaceSelection | null;
  variant?: "studio" | "welcome";
}

export function ChatPane({
  messages,
  onSend,
  isLoading,
  lastError,
  supportsVision = false,
  selection,
  variant = "studio",
}: ChatPaneProps) {
  const [input, setInput] = useState("");
  const [images, setImages] = useState<string[]>([]);
  const [historyOpen, setHistoryOpen] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages]);

  const addFiles = useCallback(async (files: FileList | File[]) => {
    const list = Array.from(files).filter((f) =>
      ACCEPTED_TYPES.includes(f.type)
    );
    for (const file of list) {
      try {
        const url = await fileToDataUrl(file);
        setImages((prev) => [...prev, url]);
      } catch {
        /* skip unsupported / too-large files */
      }
    }
  }, []);

  const handleSend = () => {
    const trimmed = input.trim();
    if (!trimmed || isLoading) return;
    onSend(trimmed, images.length > 0 ? images : undefined);
    setInput("");
    setImages([]);
  };

  const handleIncludeError = () => {
    if (lastError) {
      setInput((prev) =>
        prev.trim()
          ? `${prev}\n\nError:\n${lastError}`
          : `Fix this error:\n${lastError}`
      );
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (!supportsVision) return;
    addFiles(e.dataTransfer.files);
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) addFiles(e.target.files);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const latestRequest = [...messages]
    .reverse()
    .find((message) => message.role === "user");
  const latestRequestText = latestRequest
    ? getTextContent(latestRequest.content).trim()
    : "";

  return (
    <div
      className={`flex min-h-0 flex-col ${
        variant === "welcome"
          ? "theme-floating h-full overflow-hidden rounded-2xl border shadow-2xl shadow-black/15 backdrop-blur-xl"
          : "theme-floating overflow-hidden rounded-[22px] border shadow-2xl shadow-black/20 backdrop-blur-2xl"
      }`}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >
      {variant === "studio" && (
        <div className="flex h-11 shrink-0 items-center gap-3 border-b border-[var(--hairline)] px-3.5">
          <button
            type="button"
            onClick={() => setHistoryOpen((open) => !open)}
            aria-expanded={historyOpen}
            className="theme-control flex shrink-0 items-center gap-1.5 rounded-lg px-2 py-1.5 text-[11px] font-medium text-zinc-400 transition-colors hover:text-[var(--page-fg)]"
          >
            <MessagesSquare className="size-3.5 text-violet-400" />
            History
            <span className="text-zinc-600">{messages.length}</span>
            <ChevronDown
              className={`size-3 transition-transform ${historyOpen ? "rotate-180" : ""}`}
            />
          </button>
          {!historyOpen && latestRequestText && (
            <p className="min-w-0 flex-1 truncate text-[11px] text-zinc-600">
              Latest: {latestRequestText}
            </p>
          )}
          {historyOpen && (
            <p className="min-w-0 flex-1 text-right text-[10px] text-zinc-600">
              Conversation behind this design
            </p>
          )}
        </div>
      )}
      <div
        ref={scrollRef}
        className={`min-h-0 space-y-4 overflow-y-auto p-4 ${
          variant === "studio"
            ? historyOpen
              ? "h-[min(48dvh,520px)]"
              : "hidden"
            : "flex-1"
        }`}
      >
        {messages.length === 0 && (
          <div className="flex h-full flex-col justify-end">
            {variant === "studio" ? (
              <div className="flex flex-1 items-center justify-center px-4 text-center text-xs leading-5 text-zinc-600">
                No conversation yet. Your next request will begin this design story.
              </div>
            ) : (
              <div className="mb-1 grid gap-2 sm:grid-cols-3">
                {[
                  "A wall-mount bracket, 80 mm wide",
                  "A desk cable organizer with 4 slots",
                  "A compact enclosure with rounded corners",
                ].map((suggestion) => (
                  <button
                    key={suggestion}
                    type="button"
                    onClick={() => setInput(suggestion)}
                    className="theme-inset rounded-xl border p-3 text-left text-[11px] leading-4 text-zinc-400 transition-colors hover:border-violet-400/30 hover:text-zinc-200"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
        {messages.map((msg, i) => {
          const text = getTextContent(msg.content);
          const imgs = getImageUrls(msg.content);
          const planSummary = msg.agent?.plan
            .split(/\n|(?<=[.!?])\s+/)
            .find((line) => line.trim())
            ?.trim();

          return msg.role === "user" ? (
            <div key={i} className="flex justify-end">
              <div className="max-w-[88%] rounded-2xl rounded-br-md bg-violet-500/15 px-3.5 py-2.5 text-sm leading-5 text-zinc-200">
                {text}
                {imgs.length > 0 && (
                  <div className="mt-2 flex flex-wrap gap-1">
                    {imgs.map((url, j) => (
                      <img
                        key={j}
                        src={url}
                        alt=""
                        className="h-16 w-16 rounded object-cover"
                      />
                    ))}
                  </div>
                )}
              </div>
            </div>
          ) : (
            <div key={i} className="flex justify-start">
              <div className="theme-inset max-w-[94%] rounded-2xl rounded-bl-md border px-3.5 py-3">
                <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-zinc-300">
                  <Sparkles className="size-3 text-violet-400" />
                  Model updated
                </div>
                {msg.agent ? (
                  <>
                    <p className="text-xs leading-5 text-zinc-400">
                      {planSummary || "Your part was generated and validated successfully."}
                    </p>
                    <details className="mt-2 border-t border-[var(--hairline)] pt-2 text-[11px]">
                      <summary className="cursor-pointer text-zinc-500 hover:text-zinc-300">
                        Technical details
                      </summary>
                      <p className="mt-2 whitespace-pre-wrap leading-5 text-zinc-500">
                        {msg.agent.plan}
                      </p>
                      <div className="mt-2 space-y-1.5 border-t border-[var(--hairline)] pt-2">
                        {msg.agent.trace.map((step, traceIndex) => (
                          <div
                            key={`${step.node}-${traceIndex}`}
                            className="flex items-start gap-2 text-zinc-500"
                          >
                            {step.node === "repair" ? (
                              <RotateCcw className="mt-0.5 size-3 shrink-0 text-amber-400" />
                            ) : (
                              <Check className="mt-0.5 size-3 shrink-0 text-emerald-400" />
                            )}
                            <span>
                              <span className="capitalize text-zinc-400">
                                {step.node}
                              </span>
                              {" · "}
                              {step.detail}
                              {typeof step.duration_ms === "number" && (
                                <span className="ml-1 text-zinc-600">
                                  ({step.duration_ms} ms)
                                </span>
                              )}
                            </span>
                          </div>
                        ))}
                      </div>
                      {(msg.agent.runId || msg.agent.usage) && (
                        <div className="mt-2 font-mono text-[9px] text-zinc-600">
                          {msg.agent.runId && `run ${msg.agent.runId.slice(0, 8)}`}
                          {msg.agent.runId && msg.agent.usage && " · "}
                          {msg.agent.usage &&
                            `${msg.agent.usage.total_tokens.toLocaleString()} tokens`}
                        </div>
                      )}
                    </details>
                  </>
                ) : (
                  <pre className="overflow-x-auto whitespace-pre-wrap wrap-break-word text-xs text-zinc-300">
                    {text.slice(0, 200)}
                    {text.length > 200 ? "..." : ""}
                  </pre>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <div
        className={`flex flex-col gap-2 ${
          variant === "welcome" || historyOpen
            ? "border-t border-[var(--hairline)]"
            : ""
        } p-3`}
      >
        {selection && (
          <div className="flex items-center gap-2 rounded-xl border border-violet-400/20 bg-violet-400/8 px-3 py-2 text-[11px] text-violet-200">
            <MapPin className="size-3.5" />
            Prompt will target{" "}
            {selection.entityId
              ? `${selection.surfaceType ?? "B-rep face"} ${selection.entityId.slice(0, 13)}`
              : `the face at (${selection.point.join(", ")} mm)`}
          </div>
        )}
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

        {images.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {images.map((url, i) => (
              <div key={i} className="group relative">
                <img
                  src={url}
                  alt=""
                  className="h-14 w-14 rounded-md border border-zinc-700 object-cover"
                />
                <button
                  type="button"
                  onClick={() =>
                    setImages((prev) => prev.filter((_, j) => j !== i))
                  }
                  className="absolute -right-1 -top-1 hidden h-4 w-4 items-center justify-center rounded-full bg-zinc-700 text-zinc-300 hover:bg-red-600 group-hover:flex"
                >
                  <X className="size-2.5" />
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="theme-inset flex items-end gap-2 rounded-2xl border p-2 shadow-inner focus-within:border-violet-400/40 focus-within:ring-4 focus-within:ring-violet-400/5">
          {supportsVision && (
            <>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/jpeg,image/png,image/gif,image/webp"
                multiple
                className="hidden"
                onChange={handleFileSelect}
              />
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={() => fileInputRef.current?.click()}
                disabled={isLoading}
                className="theme-control size-9 shrink-0 rounded-xl text-zinc-500 hover:text-zinc-200"
                title="Attach image"
              >
                <ImagePlus className="size-4" />
              </Button>
            </>
          )}
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            placeholder={
              variant === "welcome"
                ? "Describe the part you want to make…"
                : selection
                  ? "What should change on this face?"
                  : "Describe your next change…"
            }
            rows={variant === "welcome" ? 3 : 1}
            disabled={isLoading}
            className="min-h-[44px] flex-1 resize-none bg-transparent px-2 py-2 text-sm leading-5 text-zinc-200 outline-none placeholder:text-zinc-600 disabled:opacity-50"
          />

          <Button
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
            size="icon"
            title="Send request"
            className="theme-primary-button size-9 shrink-0 rounded-xl"
          >
            <ArrowUp className="size-4" />
          </Button>
        </div>

        {variant === "welcome" && (
          <p className="px-1 text-center text-[10px] text-zinc-600">
            Include dimensions in millimeters for a more accurate first result.
          </p>
        )}
      </div>
    </div>
  );
}
