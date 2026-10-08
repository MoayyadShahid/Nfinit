"use client";

import type { RunEvent } from "@/lib/types";
import { useCallback, useEffect, useRef, useState } from "react";

/** How long each preview stays on screen, so the part visibly grows. */
const MIN_SHOW_MS = 500;

export type BuildPreview = { url: string; name: string };

type Queued = { runId: string; seq: number; name: string };

/**
 * Plays a run's build previews (the part after each feature) one at a time.
 * The sandbox makes them all within a second, so each is held on screen for
 * at least MIN_SHOW_MS. A preview that cannot be fetched is skipped.
 */
export function useBuildPreview() {
  const [preview, setPreview] = useState<BuildPreview | null>(null);
  const queue = useRef<Queued[]>([]);
  const playing = useRef(false);
  const lastShownAt = useRef(0);
  // Bumped by clear(), so a playback in flight stops showing anything.
  const generation = useRef(0);
  const idle = useRef<(() => void)[]>([]);

  const show = useCallback((next: BuildPreview | null) => {
    setPreview((previous) => {
      if (previous) URL.revokeObjectURL(previous.url);
      return next;
    });
  }, []);

  const play = useCallback(async () => {
    if (playing.current) return;
    playing.current = true;
    const current = generation.current;
    while (queue.current.length > 0 && current === generation.current) {
      const item = queue.current.shift()!;
      try {
        const response = await fetch(
          `/api/cad/runs/${item.runId}/snapshots/${item.seq}`,
          { cache: "no-store" }
        );
        if (!response.ok) continue;
        const blob = await response.blob();
        const wait = MIN_SHOW_MS - (Date.now() - lastShownAt.current);
        if (wait > 0) await new Promise((resolve) => setTimeout(resolve, wait));
        if (current !== generation.current) break;
        show({ url: URL.createObjectURL(blob), name: item.name });
        lastShownAt.current = Date.now();
      } catch {
        /* skip this preview */
      }
    }
    playing.current = false;
    if (queue.current.length === 0) {
      for (const resolve of idle.current.splice(0)) resolve();
    }
  }, [show]);

  /** Queue the previews among a batch of run events. */
  const enqueue = useCallback(
    (runId: string, events: RunEvent[]) => {
      const previews = events.filter((event) => event.stage === "snapshot");
      if (previews.length === 0) return;
      queue.current.push(
        ...previews.map((event) => ({ runId, seq: event.seq, name: event.message }))
      );
      void play();
    },
    [play]
  );

  /** Resolves when the queue is played, or after `timeoutMs`. */
  const settle = useCallback((timeoutMs: number) => {
    if (!playing.current && queue.current.length === 0) return Promise.resolve();
    return new Promise<void>((resolve) => {
      idle.current.push(resolve);
      setTimeout(resolve, timeoutMs);
    });
  }, []);

  const clear = useCallback(() => {
    generation.current += 1;
    queue.current = [];
    for (const resolve of idle.current.splice(0)) resolve();
    show(null);
  }, [show]);

  useEffect(() => () => clear(), [clear]);

  return { preview, enqueue, settle, clear };
}
