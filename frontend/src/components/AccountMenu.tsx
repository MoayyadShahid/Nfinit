"use client";

import type { Viewer } from "@/components/CommandBar";
import { ChevronDown, LayoutGrid, LogOut, UserRound } from "lucide-react";
import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";

/**
 * Everything about the account in one place: who is signed in, their parts,
 * the Account page and signing out. The studio and the Parts page
 * use the same menu.
 */
export function AccountMenu({ viewer }: { viewer: Viewer }) {
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: PointerEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("pointerdown", onPointer);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("pointerdown", onPointer);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const label = viewer.name ?? viewer.email ?? "Account";
  const initial = label.charAt(0).toUpperCase();

  const item =
    "theme-control flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-xs text-[var(--ink)]";

  return (
    <div className="relative" ref={menuRef}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        aria-controls={menuId}
        aria-label={`Account: ${label}`}
        className="theme-control theme-muted flex h-9 items-center gap-2 rounded-full pl-1 pr-2 text-xs hover:text-[var(--page-fg)]"
      >
        <span className="flex size-7 items-center justify-center rounded-full bg-[var(--clay)] text-[11px] font-semibold text-[var(--ink)]">
          {initial}
        </span>
        <span className="hidden max-w-28 truncate xl:inline">{label}</span>
        <ChevronDown className={`size-3 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>

      {open && (
        <div
          id={menuId}
          className="theme-floating absolute right-0 top-full z-50 mt-2 w-72 rounded-xl border p-1.5 shadow-2xl"
        >
          <div className="px-3 pb-3 pt-2">
            <p className="truncate text-sm font-semibold text-[var(--ink)]">{label}</p>
            {viewer.email && viewer.name && (
              <p className="truncate text-xs text-[var(--ink-2)]">{viewer.email}</p>
            )}
          </div>
          <div className="border-t border-[var(--hairline)] pt-1.5">
            <Link href="/parts" className={item} onClick={() => setOpen(false)}>
              <LayoutGrid className="size-3.5 text-[var(--ink-2)]" />
              Your parts
            </Link>
            <Link href="/account" className={item} onClick={() => setOpen(false)}>
              <UserRound className="size-3.5 text-[var(--ink-2)]" />
              Account
            </Link>
            <form action="/auth/signout" method="post">
              <button type="submit" className={item}>
                <LogOut className="size-3.5 text-[var(--ink-2)]" />
                Sign out
              </button>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
