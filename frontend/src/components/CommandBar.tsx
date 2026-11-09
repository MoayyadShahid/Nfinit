"use client";

import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import type { ProjectSummary } from "@/lib/projects";
import { Wordmark } from "@/components/brand/Wordmark";
import Link from "next/link";
import { ThemeToggle } from "@/components/ThemeToggle";
import SmoothDrawer from "@/components/kokonutui/smooth-drawer";
import { Button } from "@/components/ui/button";
import { EXPORT_FORMATS, type ExportFormat } from "@/lib/exports";
import { RUN_LOCALLY_URL } from "@/lib/site";
import {
  ChevronDown,
  Code2,
  Download,
  FilePlus2,
  LayoutGrid,
  Save,
  Search,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

const UNSAVED_PROJECT = "__unsaved__";

export type { ExportFormat } from "@/lib/exports";

interface CommandBarProps {
  onExport: (format: ExportFormat) => void;
  projects: ProjectSummary[];
  projectId: string | null;
  isDirty: boolean;
  isSaving: boolean;
  advancedOpen: boolean;
  onAdvancedChange: (open: boolean) => void;
  onProjectChange: (projectId: string) => void;
  onNewProject: () => void;
  onSave: () => void;
  onOpenCommands: () => void;
  busy: boolean;
  /** The public demo: no parts, saving, code or export, only a way to run locally. */
  demoOnly?: boolean;
}

export function CommandBar({
  onExport,
  projects,
  projectId,
  isDirty,
  isSaving,
  advancedOpen,
  onAdvancedChange,
  onProjectChange,
  onNewProject,
  onSave,
  onOpenCommands,
  busy,
  demoOnly = false,
}: CommandBarProps) {
  const [exportOpen, setExportOpen] = useState(false);
  const exportRef = useRef<HTMLDivElement>(null);

  const handleExportClick = useCallback(
    (format: ExportFormat) => {
      onExport(format);
      setExportOpen(false);
    },
    [onExport]
  );

  useEffect(() => {
    if (!exportOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (exportRef.current && !exportRef.current.contains(e.target as Node)) {
        setExportOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [exportOpen]);

  if (demoOnly) {
    return (
      <header className="theme-chrome relative z-[55] flex h-16 shrink-0 items-center gap-2 border-b px-3 backdrop-blur-xl sm:gap-3 sm:px-4 md:px-5">
        <div className="flex min-w-0 flex-1 items-center gap-2 sm:gap-3">
          <Wordmark href="/" size={20} />
          <span className="hidden h-5 w-px bg-[var(--hairline)] sm:block" />
          <Link
            href="/parts"
            title="All demo parts"
            aria-label="All demo parts"
            className="theme-control theme-muted flex h-9 shrink-0 items-center gap-1.5 rounded-lg px-2.5 text-xs transition-colors hover:text-[var(--page-fg)]"
          >
            <LayoutGrid className="size-3.5" />
            <span className="hidden sm:inline">Demo parts</span>
          </Link>
        </div>
        <div className="flex shrink-0 items-center justify-end gap-2">
          <ThemeToggle />
          <Link
            href={RUN_LOCALLY_URL}
            className="theme-primary-button flex h-9 items-center gap-1.5 rounded-lg px-3.5 text-xs font-semibold shadow-sm transition-transform hover:scale-[1.02]"
          >
            Run locally
          </Link>
        </div>
      </header>
    );
  }

  return (
    // backdrop-blur makes the header its own stacking context, so its z-50
    // export menu only clears the viewport if the header itself sits above it.
    <header className="theme-chrome relative z-[55] flex h-16 shrink-0 items-center gap-2 border-b px-3 backdrop-blur-xl sm:gap-3 sm:px-4 md:px-5">
      <div className="flex min-w-0 flex-1 items-center gap-2 sm:gap-3">
        <Wordmark href="/" size={20} />
        <span className="hidden h-5 w-px bg-[var(--hairline)] sm:block" />
        <Link
          href="/parts"
          title="All parts"
          aria-label="All parts"
          className="theme-control theme-muted flex h-9 shrink-0 items-center gap-1.5 rounded-lg px-2.5 text-xs transition-colors hover:text-[var(--page-fg)]"
        >
          <LayoutGrid className="size-3.5" />
          <span className="hidden lg:inline">Parts</span>
        </Link>
        <Select
          value={projectId ?? UNSAVED_PROJECT}
          onValueChange={onProjectChange}
          disabled={busy}
        >
          <SelectTrigger
            aria-label="Current part"
            className="hidden h-9 min-w-0 max-w-[220px] flex-1 border-[var(--hairline)] bg-transparent text-xs sm:flex"
          >
            <SelectValue placeholder="Unsaved part" />
          </SelectTrigger>
          <SelectContent>
            <SelectGroup>
              <SelectItem value={UNSAVED_PROJECT} disabled>
                Unsaved part
              </SelectItem>
              {projects.map((project) => (
                <SelectItem key={project.id} value={project.id}>
                  {project.name}
                </SelectItem>
              ))}
            </SelectGroup>
          </SelectContent>
        </Select>
        <button
          type="button"
          onClick={onNewProject}
          disabled={busy}
          title="New part"
          aria-label="New part"
          className="theme-control theme-muted hidden h-9 items-center gap-1.5 rounded-lg px-2.5 text-xs transition-colors hover:text-[var(--page-fg)] disabled:opacity-40 sm:flex"
        >
          <FilePlus2 className="size-3.5" />
          <span className="hidden xl:inline">New</span>
        </button>
        <button
          type="button"
          onClick={onSave}
          disabled={busy || isSaving || (!isDirty && projectId !== null)}
          title={
            projectId === null
              ? "Save part"
              : isDirty
                ? "Save revision"
                : "No unsaved changes"
          }
          className="theme-control theme-muted relative hidden h-9 items-center gap-1.5 rounded-lg px-2.5 text-xs transition-colors hover:text-[var(--page-fg)] disabled:cursor-not-allowed disabled:opacity-40 sm:flex"
        >
          <Save className="size-3.5" />
          <span className="hidden xl:inline">
            {isSaving ? "Saving…" : "Save"}
          </span>
          {isDirty && (
            <span className="absolute -right-1 -top-1 size-2 rounded-full bg-[var(--accent)]" />
          )}
        </button>
      </div>
      <div className="flex shrink-0 items-center justify-end gap-2">
        <Button variant="ghost" size="icon-sm" onClick={onOpenCommands} aria-label="Search Studio commands" title="Search commands (⌘K / Ctrl+K)">
          <Search />
        </Button>
        <ThemeToggle />
        <button
          type="button"
          onClick={() => onAdvancedChange(!advancedOpen)}
          aria-pressed={advancedOpen}
          className={cn(
            // The code editor needs room, so phones keep the bar for the essentials.
            "hidden h-9 items-center gap-1.5 rounded-lg px-3 text-xs font-medium transition-colors sm:flex",
            advancedOpen
              ? "bg-[var(--control-hover)] text-[var(--page-fg)]"
              : "theme-muted theme-control hover:text-[var(--page-fg)]"
          )}
        >
          <Code2 className="size-3.5" />
          <span className="hidden sm:inline">Advanced</span>
        </button>
        <div className="sm:hidden">
          <SmoothDrawer onExport={onExport} disabled={busy} />
        </div>
        <div className="relative hidden sm:block" ref={exportRef}>
          <button
            type="button"
            onClick={() => setExportOpen((o) => !o)}
            aria-label="Export"
            disabled={busy}
            className="theme-primary-button flex h-9 items-center gap-1.5 rounded-lg px-3 text-xs font-semibold shadow-sm transition-transform hover:scale-[1.02] sm:px-3.5"
          >
            <Download className="size-3.5" />
            <span className="hidden sm:inline">Export</span>
            <ChevronDown
              className={cn("size-3.5 transition-transform", exportOpen && "rotate-180")}
            />
          </button>
          {exportOpen && (
            <div className="theme-floating absolute right-0 top-full z-50 mt-2 min-w-[240px] rounded-xl border p-1.5 shadow-2xl">
              {EXPORT_FORMATS.map(({ id, label, ext, desc }) => (
                <button
                  key={id}
                  type="button"
                  onClick={() => handleExportClick(id)}
                  className="theme-control flex w-full flex-col items-start gap-0.5 rounded-lg px-3 py-2.5 text-left text-xs"
                >
                  <span className="font-medium">
                    {label} {ext}
                  </span>
                  <span className="text-[10px] text-zinc-500">{desc}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
