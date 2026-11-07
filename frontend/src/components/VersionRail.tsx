"use client";

import { History, PanelLeftClose, PanelLeftOpen, X } from "lucide-react";
import { useEffect, useRef, type ReactNode } from "react";

/** One point on the timeline of a part. */
export type RailVersion = {
  number: number;
  title: string;
  /** Shown under the title of the version on view, e.g. the request behind it. */
  detail?: string;
  /** Shown under every title in small type, e.g. when it was saved. */
  meta?: string;
  /** False for a demo version that has not been built yet in this replay. */
  built: boolean;
};

/**
 * The version history of a part, docked on the left of the studio so it never
 * covers the model. Collapsed, it keeps only the version numbers.
 */
export function VersionRail({
  heading,
  versions,
  selected,
  disabled = false,
  open,
  onOpenChange,
  onSelect,
  onClose,
  footer,
  compactAction,
}: {
  heading: string;
  versions: RailVersion[];
  /** The version on view; null while one is being built. */
  selected: number | null;
  disabled?: boolean;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSelect: (version: number) => void;
  /** Shows a close button, e.g. to leave a demo. */
  onClose?: () => void;
  footer?: ReactNode;
  /** Shown at the foot of the collapsed rail, e.g. a "next version" button. */
  compactAction?: ReactNode;
}) {
  const listRef = useRef<HTMLOListElement>(null);

  useEffect(() => {
    const active = listRef.current?.querySelector<HTMLElement>('[aria-current="step"]');
    active?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [selected, open, versions.length]);

  const position =
    selected !== null
      ? `${versions.findIndex((v) => v.number === selected) + 1} of ${versions.length}`
      : `${versions.length}`;

  // On a phone the open rail floats over the model instead of squeezing it,
  // and closes again once a version is picked.
  const select = (version: number) => {
    onSelect(version);
    if (window.matchMedia("(max-width: 639px)").matches) onOpenChange(false);
  };

  return (
    <div
      className={`relative h-full shrink-0 transition-[width] duration-200 ${
        open ? "w-[52px] sm:w-[236px]" : "w-[52px]"
      }`}
    >
      {open && (
        <button
          type="button"
          aria-label="Close version history"
          className="fixed inset-0 z-30 bg-black/20 sm:hidden"
          onClick={() => onOpenChange(false)}
        />
      )}
      <aside
        aria-label="Version history"
        className={`theme-floating absolute inset-y-0 left-0 z-40 flex flex-col overflow-hidden rounded-2xl border transition-[width] duration-200 ${
          open
          ? "w-[min(280px,calc(100vw-2rem))] shadow-2xl shadow-black/25 max-sm:bg-[var(--sheet)] sm:w-[236px] sm:shadow-none"
          : "w-[52px]"
        }`}
      >
        <div
          className={`flex h-11 shrink-0 items-center gap-1 border-b border-[var(--hairline)] ${
            open ? "pl-3 pr-1.5" : "justify-center"
          }`}
        >
          {open && (
            <div className="min-w-0 flex-1">
              <p className="truncate text-[10px] uppercase tracking-[0.14em] text-zinc-500">
                {heading}
              </p>
              <p className="text-[10px] tabular-nums text-zinc-600">
                {selected !== null ? `Version ${position}` : `${versions.length} versions`}
              </p>
            </div>
          )}
          {open && onClose && (
            <button
              type="button"
              onClick={onClose}
              aria-label="Close"
              title="Close"
              className="rounded-md p-1.5 text-zinc-500 hover:bg-[var(--control-hover)] hover:text-[var(--ink)]"
            >
              <X className="size-3.5" />
            </button>
          )}
          <button
            type="button"
            onClick={() => onOpenChange(!open)}
            aria-label={open ? "Collapse version history" : "Expand version history"}
            aria-expanded={open}
            title={open ? "Collapse" : "Version history"}
            className="rounded-md p-1.5 text-zinc-500 hover:bg-[var(--control-hover)] hover:text-[var(--ink)]"
          >
            {open ? <PanelLeftClose className="size-4" /> : <PanelLeftOpen className="size-4" />}
          </button>
        </div>

        <ol
          ref={listRef}
          className={`min-h-0 flex-1 overflow-y-auto ${open ? "px-2 py-2" : "px-1.5 py-2"}`}
        >
          {versions.map((version, index) => {
            const active = version.number === selected;
            const last = index === versions.length - 1;
            return (
              <li key={version.number} className="relative">
                {!last && (
                  <span
                    aria-hidden
                    className={`absolute -bottom-1 top-8 border-l border-[var(--hairline-strong)] ${
                      open ? "left-[18px]" : "left-1/2"
                    } ${versions[index + 1].built ? "" : "border-dashed"}`}
                  />
                )}
                <button
                  type="button"
                  onClick={() => select(version.number)}
                  disabled={disabled}
                  aria-current={active ? "step" : undefined}
                  title={`Version ${version.number}: ${version.title}`}
                  className={`relative mb-1 flex w-full items-start gap-2.5 rounded-xl text-left transition-colors disabled:cursor-default ${
                    open ? "p-1.5" : "justify-center py-1.5"
                  } ${active ? "bg-[var(--control-hover)]" : "hover:bg-[var(--control-hover)]"}`}
                >
                  <span
                    className={`flex size-6 shrink-0 items-center justify-center rounded-full border text-[10px] font-medium tabular-nums ${
                      active
                        ? "border-transparent bg-[var(--ink)] text-[var(--paper)]"
                        : version.built
                          ? "border-[var(--hairline-strong)] bg-[var(--sheet)] text-[var(--ink)]"
                          : "border-dashed border-[var(--hairline-strong)] bg-[var(--sheet)] text-zinc-500"
                    }`}
                  >
                    {version.number}
                  </span>
                  {open && (
                    <span className="min-w-0 flex-1 pt-0.5">
                      <span
                        className={`block truncate text-xs ${
                          version.built ? "font-medium text-[var(--ink)]" : "text-zinc-500"
                        }`}
                      >
                        {version.title}
                      </span>
                      {version.meta && (
                        <span className="block truncate text-[10px] text-zinc-500">
                          {version.meta}
                        </span>
                      )}
                      {active && version.detail && (
                        <span className="mt-1 line-clamp-4 block text-[11px] leading-4 text-[var(--ink-2)]">
                          “{version.detail}”
                        </span>
                      )}
                    </span>
                  )}
                </button>
              </li>
            );
          })}
          {versions.length === 0 && open && (
            <li className="flex flex-col items-center gap-2 px-3 py-8 text-center text-[11px] leading-4 text-zinc-500">
              <History className="size-4" />
              Each change you make is saved here as a version.
            </li>
          )}
        </ol>

        {open && footer && (
          <div className="shrink-0 border-t border-[var(--hairline)] p-2.5">{footer}</div>
        )}
        {!open && compactAction && (
          <div className="flex shrink-0 justify-center border-t border-[var(--hairline)] py-2">
            {compactAction}
          </div>
        )}
      </aside>
    </div>
  );
}
