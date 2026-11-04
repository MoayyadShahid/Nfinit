"use client";

import { Wordmark } from "@/components/brand/Wordmark";
import type { Viewer } from "@/components/CommandBar";
import { Paywall } from "@/components/Paywall";
import { ThemeToggle } from "@/components/ThemeToggle";
import { demoThumbnail, listDemos, type DemoSummary } from "@/lib/demos";
import {
  deleteProject,
  getProject,
  listProjects,
  renameProject,
  SubscriptionRequiredError,
  thumbnailUrl,
  type ProjectSummary,
} from "@/lib/projects";
import { sandboxRequest } from "@/lib/sandbox";
import { Box, Check, LogOut, Pencil, Play, Plus, Search, Trash2, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

const DOWNLOADS = [
  { format: "step", label: "STEP", ext: ".step" },
  { format: "stl", label: "STL", ext: ".stl" },
] as const;

function relativeTime(iso: string): string {
  const seconds = Math.round((Date.now() - Date.parse(iso)) / 1000);
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ["year", 31_536_000],
    ["month", 2_592_000],
    ["week", 604_800],
    ["day", 86_400],
    ["hour", 3_600],
    ["minute", 60],
  ];
  const format = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  for (const [unit, size] of units) {
    if (seconds >= size) return format.format(-Math.floor(seconds / size), unit);
  }
  return "just now";
}

function fileName(name: string, ext: string): string {
  const slug = name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 60);
  return `${slug || "part"}${ext}`;
}

function PartCard({
  part,
  onRenamed,
  onDeleted,
  onError,
  onSubscriptionRequired,
}: {
  part: ProjectSummary;
  onRenamed: (part: ProjectSummary) => void;
  onDeleted: (id: string) => void;
  onError: (message: string) => void;
  onSubscriptionRequired: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(part.name);
  const [busy, setBusy] = useState<string | null>(null);
  const preview = thumbnailUrl(part);

  const saveName = async () => {
    const trimmed = name.trim();
    if (!trimmed || trimmed === part.name) {
      setName(part.name);
      setEditing(false);
      return;
    }
    setBusy("rename");
    try {
      const updated = await renameProject(part.id, trimmed);
      onRenamed(updated);
      setEditing(false);
    } catch (e) {
      onError(e instanceof Error ? e.message : "Rename failed");
    } finally {
      setBusy(null);
    }
  };

  const remove = async () => {
    if (!window.confirm(`Delete “${part.name}” and all of its revisions?`)) return;
    setBusy("delete");
    try {
      await deleteProject(part.id);
      onDeleted(part.id);
    } catch (e) {
      onError(e instanceof Error ? e.message : "Delete failed");
      setBusy(null);
    }
  };

  const download = async (format: "step" | "stl", ext: string) => {
    setBusy(format);
    try {
      const project = await getProject(part.id);
      const code = project.latestRevision?.state.code;
      if (!code) throw new Error("This part has no saved geometry yet.");
      const response = await sandboxRequest("export-model", { code, format });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(payload?.detail || "Export failed");
      }
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = fileName(part.name, ext);
      link.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      if (e instanceof SubscriptionRequiredError) {
        onSubscriptionRequired();
      } else {
        onError(e instanceof Error ? e.message : "Export failed");
      }
    } finally {
      setBusy(null);
    }
  };

  return (
    <article className="theme-floating group flex flex-col overflow-hidden rounded-2xl border shadow-sm transition-shadow hover:shadow-xl hover:shadow-black/10">
      <Link
        href={`/studio?project=${encodeURIComponent(part.id)}`}
        className="relative block aspect-[4/3] overflow-hidden bg-[var(--clay)]"
        aria-label={`Open ${part.name}`}
      >
        {preview ? (
          // eslint-disable-next-line @next/next/no-img-element -- authenticated, per-user image behind the API proxy
          <img
            src={preview}
            alt=""
            loading="lazy"
            className="size-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
          />
        ) : (
          <span className="flex size-full items-center justify-center text-[var(--ink-2)]">
            <Box className="size-10 opacity-40" strokeWidth={1.25} />
          </span>
        )}
      </Link>

      <div className="flex flex-1 flex-col gap-3 p-4">
        {editing ? (
          <form
            className="flex items-center gap-1.5"
            onSubmit={(event) => {
              event.preventDefault();
              void saveName();
            }}
          >
            <input
              autoFocus
              value={name}
              maxLength={120}
              onChange={(event) => setName(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Escape") {
                  setName(part.name);
                  setEditing(false);
                }
              }}
              aria-label="Part name"
              className="theme-inset min-w-0 flex-1 rounded-lg border px-2.5 py-1.5 text-[15px] text-[var(--ink)] outline-none focus:border-[var(--hairline-strong)]"
            />
            <button
              type="submit"
              disabled={busy === "rename"}
              aria-label="Save name"
              className="theme-control rounded-lg p-2 text-[var(--ink-2)] hover:text-[var(--ink)]"
            >
              <Check className="size-4" />
            </button>
          </form>
        ) : (
          <div className="flex items-start gap-2">
            <Link
              href={`/studio?project=${encodeURIComponent(part.id)}`}
              className="min-w-0 flex-1 text-[15px] font-medium leading-snug text-[var(--ink)] hover:underline hover:underline-offset-2"
            >
              <span className="line-clamp-2">{part.name}</span>
            </Link>
            <button
              type="button"
              onClick={() => setEditing(true)}
              aria-label={`Rename ${part.name}`}
              title="Rename"
              className="theme-control rounded-lg p-1.5 text-[var(--ink-2)] hover:text-[var(--ink)]"
            >
              <Pencil className="size-3.5" />
            </button>
          </div>
        )}

        <p className="type-spec text-[var(--ink-2)]">
          V{part.revisionCount} · {relativeTime(part.updatedAt).toUpperCase()}
        </p>

        <div className="mt-auto flex items-center gap-1.5 border-t border-[var(--hairline)] pt-3">
          {DOWNLOADS.map(({ format, label, ext }) => (
            <button
              key={format}
              type="button"
              disabled={busy !== null}
              onClick={() => void download(format, ext)}
              title={`Download ${label}`}
              className="theme-control rounded-lg px-2.5 py-1.5 font-mono text-[11px] font-medium tracking-wide text-[var(--ink-2)] hover:text-[var(--ink)] disabled:opacity-50"
            >
              {busy === format ? "…" : label}
            </button>
          ))}
          <button
            type="button"
            disabled={busy !== null}
            onClick={() => void remove()}
            aria-label={`Delete ${part.name}`}
            title="Delete"
            className="theme-control ml-auto rounded-lg p-2 text-[var(--ink-2)] hover:text-[var(--danger)] disabled:opacity-50"
          >
            <Trash2 className="size-3.5" />
          </button>
        </div>
      </div>
    </article>
  );
}

/** A demo part every account has: opens its version-by-version replay. */
function DemoCard({ demo }: { demo: DemoSummary }) {
  const [imageFailed, setImageFailed] = useState(false);
  return (
    <Link
      href={`/studio?demo=${encodeURIComponent(demo.slug)}`}
      aria-label={`Replay the ${demo.title} demo`}
      className="theme-floating group flex flex-col overflow-hidden rounded-2xl border shadow-sm transition-shadow hover:shadow-xl hover:shadow-black/10"
    >
      <span className="relative block aspect-[4/3] overflow-hidden bg-[var(--clay)]">
        {imageFailed ? (
          <span className="flex size-full items-center justify-center text-[var(--ink-2)]">
            <Box className="size-10 opacity-40" strokeWidth={1.25} />
          </span>
        ) : (
          // eslint-disable-next-line @next/next/no-img-element -- small static file in public/
          <img
            src={demoThumbnail(demo.slug)}
            alt=""
            loading="lazy"
            onError={() => setImageFailed(true)}
            className="size-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
          />
        )}
        <span className="absolute left-3 top-3 rounded-full bg-[var(--sheet)] px-2 py-0.5 text-[10px] font-medium uppercase tracking-[0.12em] text-[var(--ink-2)]">
          Demo part
        </span>
      </span>
      <span className="flex flex-1 flex-col gap-1.5 p-4">
        <span className="text-[15px] font-semibold text-[var(--ink)]">{demo.title}</span>
        <span className="text-[13px] leading-5 text-[var(--ink-2)]">{demo.summary}</span>
        <span className="mt-auto flex items-center gap-1.5 pt-2 text-xs text-[var(--ink-2)]">
          <Play className="size-3.5" />
          {demo.steps} versions · Replay how it is built
        </span>
      </span>
    </Link>
  );
}

export function PartsGallery({ viewer }: { viewer: Viewer | null }) {
  const [parts, setParts] = useState<ProjectSummary[] | null>(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [showPaywall, setShowPaywall] = useState(false);
  const [demos, setDemos] = useState<DemoSummary[]>([]);

  useEffect(() => {
    let active = true;
    listDemos()
      .then((items) => {
        if (active) setDemos(items);
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    listProjects()
      .then((items) => {
        if (active) setParts(items);
      })
      .catch((e) => {
        if (!active) return;
        setParts([]);
        setError(e instanceof Error ? e.message : "Could not load your parts");
      });
    return () => {
      active = false;
    };
  }, []);

  const needle = query.trim().toLowerCase();
  const visible = useMemo(() => {
    if (!parts || !needle) return parts;
    return parts.filter((part) => part.name.toLowerCase().includes(needle));
  }, [parts, needle]);
  // The demo parts are in every account's library, after the user's own parts.
  const visibleDemos = useMemo(
    () =>
      needle
        ? demos.filter((demo) =>
            `${demo.title} ${demo.summary}`.toLowerCase().includes(needle)
          )
        : demos,
    [demos, needle]
  );

  return (
    <div className="theme-page min-h-dvh">
      <header className="theme-chrome sticky top-0 z-20 flex h-16 items-center gap-3 border-b px-4 backdrop-blur-xl md:px-5">
        <Wordmark href="/" size={20} />
        <div className="ml-auto flex items-center gap-2">
          <ThemeToggle />
          {viewer && (
            <form action="/auth/signout" method="post">
              <button
                type="submit"
                aria-label={`Sign out${viewer.email ? ` ${viewer.email}` : ""}`}
                title={viewer.email ? `Sign out ${viewer.email}` : "Sign out"}
                className="theme-control theme-muted flex h-9 items-center gap-2 rounded-full px-2 text-xs hover:text-[var(--page-fg)]"
              >
                <span className="flex size-6 items-center justify-center rounded-full bg-[var(--clay)] text-[10px] font-semibold text-[var(--ink)]">
                  {(viewer.name ?? viewer.email ?? "U").charAt(0).toUpperCase()}
                </span>
                <LogOut className="size-3.5" />
              </button>
            </form>
          )}
          <Link
            href="/studio?new=1"
            className="theme-primary-button flex h-9 items-center gap-1.5 rounded-lg px-3.5 text-xs font-semibold shadow-sm transition-transform hover:scale-[1.02]"
          >
            <Plus className="size-3.5" />
            New part
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-10 md:px-8">
        <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="type-label mb-3">Library</p>
            <h1 className="type-h2">
              Your <em>parts</em>
            </h1>
          </div>
          {(parts?.length || demos.length) > 0 && (
            <label className="theme-inset flex w-full items-center gap-2 rounded-xl border px-3 py-2 sm:w-72">
              <Search className="size-4 text-[var(--ink-2)]" />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search parts"
                aria-label="Search parts"
                className="min-w-0 flex-1 bg-transparent text-[15px] text-[var(--ink)] outline-none placeholder:text-[var(--ink-2)]"
              />
            </label>
          )}
        </div>

        {error && (
          <div className="mb-6 flex items-start gap-3 rounded-xl border border-[var(--danger)]/30 bg-[var(--sheet)] px-4 py-3 text-sm text-[var(--danger)]">
            <span className="min-w-0 flex-1">{error}</span>
            <button
              type="button"
              onClick={() => setError(null)}
              aria-label="Dismiss error"
              className="rounded-md p-1 hover:bg-[var(--control-hover)]"
            >
              <X className="size-4" />
            </button>
          </div>
        )}

        {parts === null ? (
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {Array.from({ length: 6 }, (_, index) => (
              <div
                key={index}
                className="theme-floating aspect-[4/4.2] animate-pulse rounded-2xl border"
              />
            ))}
          </div>
        ) : visible?.length === 0 && visibleDemos.length === 0 && needle ? (
          <p className="text-[15px] text-[var(--ink-2)]">
            No parts match “{query.trim()}”.
          </p>
        ) : (
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {parts.length === 0 && !needle && (
              <Link
                href="/studio?new=1"
                className="theme-floating flex flex-col items-start justify-end gap-4 rounded-2xl border border-dashed p-6 transition-shadow hover:shadow-xl hover:shadow-black/10"
              >
                <Box className="size-8 text-[var(--ink-2)]" strokeWidth={1.25} />
                <span>
                  <span className="block text-[15px] font-semibold text-[var(--ink)]">
                    Make your first part
                  </span>
                  <span className="mt-1 block text-[13px] leading-5 text-[var(--ink-2)]">
                    Describe something in the studio, and every valid model is saved
                    here. The demo parts show how a part is built, version by version.
                  </span>
                </span>
                <span className="theme-primary-button flex h-9 items-center gap-1.5 rounded-lg px-3.5 text-xs font-semibold">
                  <Plus className="size-3.5" />
                  New part
                </span>
              </Link>
            )}
            {visible?.map((part) => (
              <PartCard
                key={part.id}
                part={part}
                onError={setError}
                onSubscriptionRequired={() => setShowPaywall(true)}
                onRenamed={(updated) =>
                  setParts((previous) =>
                    previous?.map((item) =>
                      item.id === updated.id ? { ...item, ...updated } : item
                    ) ?? null
                  )
                }
                onDeleted={(id) =>
                  setParts((previous) =>
                    previous?.filter((item) => item.id !== id) ?? null
                  )
                }
              />
            ))}
            {visibleDemos.map((demo) => (
              <DemoCard key={demo.slug} demo={demo} />
            ))}
          </div>
        )}
      </main>
      <Paywall
        reason={showPaywall ? "export" : null}
        onClose={() => setShowPaywall(false)}
      />
    </div>
  );
}
