"use client";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import type { ProjectSummary } from "@/lib/projects";
import { ThemeToggle } from "@/components/ThemeToggle";
import {
  ChevronDown,
  Code2,
  Download,
  FilePlus2,
  Save,
  Sparkles,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

const EXPORT_FORMATS = [
  { id: "step", label: "STEP", ext: ".step", desc: "CAD (Fusion, SolidWorks, Onshape)" },
  { id: "brep", label: "BREP", ext: ".brep", desc: "OpenCASCADE tools" },
  { id: "stl", label: "STL", ext: ".stl", desc: "3D printing" },
] as const;
const UNSAVED_PROJECT = "__unsaved__";

export type ExportFormat = (typeof EXPORT_FORMATS)[number]["id"];

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

  return (
    <header className="theme-chrome flex h-16 shrink-0 items-center gap-3 border-b px-4 backdrop-blur-xl md:px-5">
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <div className="flex shrink-0 items-center gap-2">
          <span className="flex size-8 items-center justify-center rounded-xl bg-gradient-to-br from-violet-400 to-blue-500 text-white shadow-lg shadow-violet-500/20">
            <Sparkles className="size-4" />
          </span>
          <span className="hidden text-sm font-semibold tracking-tight sm:inline">
            nfinit
          </span>
        </div>
        <span className="hidden h-5 w-px bg-[var(--hairline)] sm:block" />
        <Select
          value={projectId ?? UNSAVED_PROJECT}
          onValueChange={onProjectChange}
        >
          <SelectTrigger
            aria-label="Current part"
            className="h-9 min-w-0 max-w-[220px] flex-1 border-[var(--hairline)] bg-transparent text-xs"
          >
            <SelectValue placeholder="Unsaved part" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={UNSAVED_PROJECT} disabled>
              Unsaved part
            </SelectItem>
            {projects.map((project) => (
              <SelectItem key={project.id} value={project.id}>
                {project.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <button
          type="button"
          onClick={onNewProject}
          title="New part"
          className="theme-control theme-muted flex h-9 items-center gap-1.5 rounded-lg px-2.5 text-xs transition-colors hover:text-[var(--page-fg)]"
        >
          <FilePlus2 className="size-3.5" />
          <span className="hidden xl:inline">New</span>
        </button>
        <button
          type="button"
          onClick={onSave}
          disabled={isSaving || (!isDirty && projectId !== null)}
          title={
            projectId === null
              ? "Save part"
              : isDirty
                ? "Save revision"
                : "No unsaved changes"
          }
          className="theme-control theme-muted relative flex h-9 items-center gap-1.5 rounded-lg px-2.5 text-xs transition-colors hover:text-[var(--page-fg)] disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Save className="size-3.5" />
          <span className="hidden xl:inline">
            {isSaving ? "Saving…" : "Save"}
          </span>
          {isDirty && (
            <span className="absolute -right-1 -top-1 size-2 rounded-full bg-blue-400" />
          )}
        </button>
      </div>
      <div className="flex min-w-0 items-center justify-end gap-2">
        <ThemeToggle />
        <button
          type="button"
          onClick={() => onAdvancedChange(!advancedOpen)}
          aria-pressed={advancedOpen}
          className={cn(
            "flex h-9 items-center gap-1.5 rounded-lg px-3 text-xs font-medium transition-colors",
            advancedOpen
              ? "bg-[var(--control-hover)] text-[var(--page-fg)]"
              : "theme-muted theme-control hover:text-[var(--page-fg)]"
          )}
        >
          <Code2 className="size-3.5" />
          <span className="hidden sm:inline">Advanced</span>
        </button>
        <div className="relative" ref={exportRef}>
          <button
            type="button"
            onClick={() => setExportOpen((o) => !o)}
            className="theme-primary-button flex h-9 items-center gap-1.5 rounded-lg px-3.5 text-xs font-semibold shadow-sm transition-transform hover:scale-[1.02]"
          >
            <Download className="size-3.5" />
            Export
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
