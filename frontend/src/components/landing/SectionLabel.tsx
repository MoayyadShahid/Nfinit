/** A plain mono section label (`01 DESCRIBE`). No rule lines. */
export function SectionLabel({
  label,
  className = "",
}: {
  label: string;
  className?: string;
}) {
  return <p className={`type-label ${className}`}>{label}</p>;
}
