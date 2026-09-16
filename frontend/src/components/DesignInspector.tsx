"use client";

import type { ProjectRevision } from "@/lib/projects";
import type { FaceSelection, ModelInspection } from "@/lib/types";
import {
  Box,
  CheckCircle2,
  ChevronRight,
  CircleDashed,
  MousePointer2,
  Ruler,
} from "lucide-react";

interface DesignInspectorProps {
  inspection: ModelInspection | null;
  selection: FaceSelection | null;
  revisions: ProjectRevision[];
  currentRevision: number | null;
  isDirty: boolean;
  onRevisionChange: (revision: number) => void;
}

function formatNumber(value: number | undefined, digits = 1) {
  if (value === undefined) return "—";
  return new Intl.NumberFormat("en", { maximumFractionDigits: digits }).format(value);
}

export function DesignInspector({
  inspection,
  selection,
  revisions,
  currentRevision,
  isDirty,
  onRevisionChange,
}: DesignInspectorProps) {
  const bounds = inspection?.bounding_box_mm;

  return (
    <aside className="flex min-h-0 flex-col border-l border-white/8 bg-[#0e0f13]">
      <div className="border-b border-white/8 px-5 py-4">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-white">Design</h2>
          <span className="flex items-center gap-1.5 text-[11px] text-zinc-500">
            {isDirty ? (
              <>
                <CircleDashed className="size-3 text-amber-400" />
                Unsaved
              </>
            ) : (
              <>
                <CheckCircle2 className="size-3 text-emerald-400" />
                Saved
              </>
            )}
          </span>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <section className="border-b border-white/8 p-5">
          <div className="mb-3 flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.14em] text-zinc-500">
            <Ruler className="size-3.5" />
            Overall size
          </div>
          {bounds ? (
            <div className="grid grid-cols-3 gap-2">
              {(["x", "y", "z"] as const).map((axis) => (
                <div key={axis} className="rounded-xl border border-white/8 bg-white/[0.025] p-3">
                  <div className="text-[10px] uppercase text-zinc-600">{axis}</div>
                  <div className="mt-1 text-sm font-medium text-zinc-200">
                    {formatNumber(bounds[axis])}
                    <span className="ml-0.5 text-[10px] font-normal text-zinc-600">mm</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-xs leading-5 text-zinc-500">
              Dimensions appear after your first model is generated.
            </p>
          )}
          {inspection && (
            <div className="mt-3 flex items-center justify-between text-xs text-zinc-500">
              <span>{inspection.shape_type ?? "Solid"}</span>
              <span>{formatNumber(inspection.volume_mm3, 0)} mm³</span>
            </div>
          )}
        </section>

        <section className="border-b border-white/8 p-5">
          <div className="mb-3 flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.14em] text-zinc-500">
            <MousePointer2 className="size-3.5" />
            Edit target
          </div>
          {selection ? (
            <div className="rounded-xl border border-violet-400/20 bg-violet-400/8 p-3">
              <div className="text-xs font-medium text-violet-200">
                {selection.surfaceType
                  ? `${selection.surfaceType[0].toUpperCase()}${selection.surfaceType.slice(1)} face`
                  : "Selected face"}
              </div>
              <p className="mt-1 font-mono text-[10px] text-violet-300/60">
                {selection.entityId?.slice(0, 18) ?? selection.point.join(", ")}
              </p>
              <p className="mt-2 text-[11px] leading-4 text-zinc-400">
                Your next request will edit this face.
              </p>
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-white/10 p-3">
              <p className="text-xs leading-5 text-zinc-500">
                Click any face in the model, then describe the change you want.
              </p>
            </div>
          )}
        </section>

        <section className="p-5">
          <div className="mb-3 flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.14em] text-zinc-500">
            <Box className="size-3.5" />
            Revision history
          </div>
          {revisions.length === 0 ? (
            <p className="text-xs leading-5 text-zinc-500">
              Every successful change creates a restorable version.
            </p>
          ) : (
            <div className="space-y-1">
              {revisions.map((revision) => {
                const active = revision.revisionNumber === currentRevision;
                return (
                  <button
                    key={revision.id}
                    type="button"
                    onClick={() => onRevisionChange(revision.revisionNumber)}
                    className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors ${
                      active
                        ? "bg-white/8 text-white"
                        : "text-zinc-500 hover:bg-white/5 hover:text-zinc-300"
                    }`}
                  >
                    <span
                      className={`size-2 rounded-full ${
                        active ? "bg-violet-400 ring-4 ring-violet-400/10" : "bg-zinc-700"
                      }`}
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block text-xs font-medium">
                        Revision {revision.revisionNumber}
                      </span>
                      <span className="block text-[10px] text-zinc-600">
                        {new Date(revision.createdAt).toLocaleString([], {
                          month: "short",
                          day: "numeric",
                          hour: "numeric",
                          minute: "2-digit",
                        })}
                      </span>
                    </span>
                    <ChevronRight className="size-3.5 opacity-40" />
                  </button>
                );
              })}
            </div>
          )}
        </section>
      </div>
    </aside>
  );
}
