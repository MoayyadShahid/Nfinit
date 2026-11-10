"use client";

import type {
  Acceptance,
  ChangeReport,
  ModelInspection,
  PrintabilityReport,
  RequirementStatus,
} from "@/lib/types";
import { AlertTriangle, Check, CircleDashed, Eye, Printer, X } from "lucide-react";
import type { ReactNode } from "react";

const VERDICT_LABEL: Record<Acceptance["verdict"], string> = {
  verified: "Verified",
  partial: "Partly verified",
  failed: "Failed",
};

const STATUS_LABEL: Record<RequirementStatus, string> = {
  passed: "Passed",
  failed: "Failed",
  review: "Review",
  unverified: "Not measured",
  not_measurable: "From images",
};

function StatusIcon({ status }: { status: RequirementStatus | "pass" | "fail" }) {
  if (status === "passed" || status === "pass") {
    return <Check className="size-3 shrink-0 text-emerald-500" aria-label="Passed" />;
  }
  if (status === "failed" || status === "fail") {
    return <X className="size-3 shrink-0 text-red-500" aria-label="Failed" />;
  }
  if (status === "review") {
    return <AlertTriangle className="size-3 shrink-0 text-amber-500" aria-label="Review" />;
  }
  return <CircleDashed className="size-3 shrink-0 text-zinc-500" aria-label="Not measured" />;
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(3).replace(/0+$/, "");
  if (Array.isArray(value)) return value.map(formatValue).join(" × ");
  if (typeof value === "object") {
    const entries = value as Record<string, unknown>;
    if (["x", "y", "z"].every((axis) => axis in entries)) {
      return `${formatValue(entries.x)} × ${formatValue(entries.y)} × ${formatValue(entries.z)}`;
    }
    return Object.entries(entries)
      .map(([key, entry]) => `${key.replace(/_mm$/, "")} ${formatValue(entry)}`)
      .join(", ");
  }
  return String(value);
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="mt-2 border-t border-[var(--hairline)] pt-2">
      <p className="mb-1.5 text-[10px] uppercase tracking-[0.14em] text-zinc-500">{title}</p>
      {children}
    </div>
  );
}

function verdictTone(verdict: Acceptance["verdict"]) {
  if (verdict === "verified") return "text-emerald-500";
  if (verdict === "failed") return "text-red-500";
  return "text-amber-500";
}

/**
 * What a run proved about its part: each requirement with its measured value,
 * warnings, printability findings and changes outside the request. Every
 * section is hidden when the run did not produce it, so older runs and API
 * runs show only what they have.
 */
export function VerificationPanel({
  inspection,
  onShowFaces,
  framed = true,
}: {
  inspection: ModelInspection;
  /** Highlight faces on the part, or clear the highlight with an empty list. */
  onShowFaces?: (faceIds: string[]) => void;
  /** Draw its own border; off inside a card that already has one. */
  framed?: boolean;
}) {
  const acceptance = inspection.acceptance;
  const printability =
    inspection.printability && "findings" in inspection.printability
      ? (inspection.printability as PrintabilityReport)
      : null;
  const changes =
    inspection.changes && "flags" in inspection.changes ? (inspection.changes as ChangeReport) : null;
  const warnings = inspection.warnings ?? [];
  const findings = printability?.findings.filter(
    (finding) => finding.status === "fail" || finding.status === "review"
  );
  const checks = inspection.checks ?? [];

  if (!acceptance && !printability && !changes && !warnings.length && !checks.length) return null;

  const measurable = acceptance
    ? acceptance.passed + acceptance.failed + acceptance.unverified + (acceptance.review ?? 0)
    : 0;

  return (
    <div
      className={
        framed
          ? "mt-2 rounded-xl border border-[var(--hairline)] p-2.5 text-[11px]"
          : "mt-3 border-t border-[var(--hairline)] pt-2.5 text-[11px]"
      }
      data-testid="verification"
    >
      {acceptance ? (
        <p className="leading-4">
          <span className={`font-medium ${verdictTone(acceptance.verdict)}`}>
            {VERDICT_LABEL[acceptance.verdict]}
          </span>
          <span className="text-zinc-500">
            {" "}
            · {acceptance.passed} of {measurable} requirements measured and passed
          </span>
        </p>
      ) : checks.length ? (
        <p className="text-zinc-500">
          {checks.filter((check) => check.passed).length}/{checks.length} geometry measurements passed.
          Unmeasured requirements still need review.
        </p>
      ) : null}

      {acceptance && acceptance.rows.length > 0 && (
        <details className="mt-1.5">
          <summary className="cursor-pointer text-zinc-500 hover:text-[var(--ink)]">Requirements</summary>
          <table className="mt-1.5 w-full table-fixed border-collapse">
            <tbody>
              {acceptance.rows.map((row) => (
                <tr key={row.id} className="align-top" title={row.detail || undefined}>
                  <td className="w-4 py-0.5">
                    <StatusIcon status={row.status} />
                  </td>
                  <td className="py-0.5 pr-2 text-[var(--ink-2)]">
                    {row.text}
                    {row.source === "assumed" && <span className="ml-1 text-zinc-500">(assumed)</span>}
                    {row.status !== "passed" && row.detail && (
                      <span className="block text-zinc-500">{row.detail}</span>
                    )}
                  </td>
                  <td className="w-[30%] py-0.5 text-right font-mono text-[10px] text-zinc-500">
                    {row.measured !== null && row.measured !== undefined
                      ? formatValue(row.measured)
                      : STATUS_LABEL[row.status]}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {acceptance.assumptions.length > 0 && (
            <p className="mt-1.5 text-zinc-500">Assumed: {acceptance.assumptions.join(" ")}</p>
          )}
        </details>
      )}

      {warnings.length > 0 && (
        <Section title="Warnings">
          <ul className="space-y-1">
            {warnings.map((warning) => (
              <li key={warning} className="flex gap-1.5 text-[var(--ink-2)]">
                <AlertTriangle className="mt-0.5 size-3 shrink-0 text-amber-500" />
                {warning}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {printability && findings && (
        <Section title="Printability">
          {findings.length === 0 ? (
            <p className="flex items-center gap-1.5 text-zinc-500">
              <Printer className="size-3" />
              No printing problems found for this {formatValue(printability.profile.process ?? "fdm").toUpperCase()}{" "}
              profile.
            </p>
          ) : (
            <ul className="space-y-1.5">
              {findings.map((finding) => (
                <li key={finding.rule} className="flex gap-1.5">
                  <StatusIcon status={finding.status === "fail" ? "fail" : "review"} />
                  <span className="min-w-0 flex-1 text-[var(--ink-2)]">
                    {finding.suggestion || finding.rule.replace(/_/g, " ")}
                  </span>
                  {onShowFaces && finding.face_ids.length > 0 && (
                    <button
                      type="button"
                      className="flex shrink-0 items-center gap-1 text-zinc-500 hover:text-[var(--ink)]"
                      onClick={() => onShowFaces(finding.face_ids)}
                    >
                      <Eye className="size-3" />
                      Show on part
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Section>
      )}

      {changes && (changes.flags.length > 0 || Object.keys(changes.census_delta).length > 0) && (
        <Section title="Changes since the previous version">
          <ul className="space-y-1">
            {changes.flags.map((flag) => (
              <li key={flag} className="flex gap-1.5 text-[var(--ink-2)]">
                <AlertTriangle className="mt-0.5 size-3 shrink-0 text-amber-500" />
                {flag}
              </li>
            ))}
            {changes.flags.length === 0 &&
              Object.entries(changes.census_delta).map(([what, delta]) => (
                <li key={what} className="text-zinc-500">
                  {what}: {delta}
                </li>
              ))}
          </ul>
        </Section>
      )}
    </div>
  );
}
