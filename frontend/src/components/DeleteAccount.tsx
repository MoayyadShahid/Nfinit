"use client";

import { useState } from "react";

const CONFIRMATION = "DELETE";

/** Deletes the signed-in account after the user types DELETE. */
export function DeleteAccount() {
  const [typed, setTyped] = useState("");
  const [isDeleting, setIsDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const deleteAccount = async () => {
    setIsDeleting(true);
    setError(null);
    try {
      const response = await fetch("/api/account", { method: "DELETE" });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        throw new Error(
          payload?.detail || `Your account could not be deleted (${response.status}).`
        );
      }
      // The account is gone: end the session and leave the app.
      await fetch("/auth/signout", { method: "POST", redirect: "manual" }).catch(
        () => undefined
      );
      try {
        window.localStorage.removeItem("nfinit:last-project-id");
      } catch {
        // Storage can be blocked; nothing to clear then.
      }
      window.location.assign("/?account=deleted");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Your account could not be deleted.");
      setIsDeleting(false);
    }
  };

  return (
    <div className="rounded-2xl border border-[var(--danger)] p-5 sm:p-6">
      <h2 className="text-lg font-semibold text-[var(--ink)]">Delete account</h2>
      <p className="mt-2 text-[15px] leading-6 text-[var(--ink-2)]">
        This permanently deletes your account, all your projects and their history, your
        part files and your run records. It also cancels your subscription at once,
        without a refund for the rest of the month. You cannot undo this.
      </p>
      <p className="mt-2 text-[15px] leading-6 text-[var(--ink-2)]">
        Export any parts you want to keep first. Stripe keeps its payment and tax records,
        as the law requires.
      </p>
      <label className="mt-5 block text-sm text-[var(--ink)]" htmlFor="confirm-delete">
        Type <strong>{CONFIRMATION}</strong> to confirm
      </label>
      <input
        id="confirm-delete"
        value={typed}
        onChange={(event) => setTyped(event.target.value)}
        autoComplete="off"
        spellCheck={false}
        className="theme-inset mt-2 w-full max-w-xs rounded-lg border px-3 py-2 text-sm text-[var(--ink)]"
      />
      <div className="mt-4">
        <button
          type="button"
          onClick={deleteAccount}
          disabled={typed !== CONFIRMATION || isDeleting}
          className="rounded-lg bg-[var(--danger)] px-4 py-2 text-sm font-medium text-white transition-opacity disabled:cursor-not-allowed disabled:opacity-40"
        >
          {isDeleting ? "Deleting…" : "Delete my account"}
        </button>
      </div>
      {error && (
        <p role="alert" className="mt-3 text-sm text-[var(--danger)]">
          {error}
        </p>
      )}
    </div>
  );
}
