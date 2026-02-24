"use client";

import { Button } from "@/components/ui/button";
import {
  type ChatMessage,
  getTextContent,
  getImageUrls,
} from "@/lib/types";
import { ImagePlus, X } from "lucide-react";
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
}

export function ChatPane({
  messages,
  onSend,
  isLoading,
  lastError,
  supportsVision = false,
}: ChatPaneProps) {
  const [input, setInput] = useState("");
  const [images, setImages] = useState<string[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages]);

  useEffect(() => {
    if (!supportsVision) setImages([]);
  }, [supportsVision]);

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

  return (
    <div
      className="flex h-full min-h-0 flex-col border-l border-[#1f1f1f] bg-[#0a0a0a]"
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >
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
        {messages.map((msg, i) => {
          const text = getTextContent(msg.content);
          const imgs = getImageUrls(msg.content);

          return msg.role === "user" ? (
            <div key={i} className="flex justify-end">
              <div className="max-w-[85%] rounded-lg bg-blue-600/30 px-3 py-2 text-sm text-zinc-200">
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
              <div className="max-w-[85%] rounded-lg border border-[#1f1f1f] bg-[#141414] px-3 py-2">
                <div className="mb-1 text-xs text-zinc-500">Generated code</div>
                <pre className="overflow-x-auto whitespace-pre-wrap wrap-break-word text-xs text-zinc-300">
                  {text.slice(0, 200)}
                  {text.length > 200 ? "..." : ""}
                </pre>
              </div>
            </div>
          );
        })}
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
                className="shrink-0 text-zinc-400 hover:text-zinc-200"
                title="Attach image"
              >
                <ImagePlus className="size-4" />
              </Button>
            </>
          )}

          <Button
            onClick={handleSend}
            disabled={!input.trim() || isLoading}
            className="shrink-0 border border-zinc-600 bg-zinc-800 text-zinc-100 hover:border-zinc-500 hover:bg-zinc-700"
          >
            Send
          </Button>
        </div>

        <p className="px-1 text-[10px] text-zinc-600">
          Tip: Add dimensions in mm (e.g. width 80, thickness 6) for better
          accuracy.
        </p>
      </div>
    </div>
  );
}
