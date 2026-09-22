import Link from "next/link";

/**
 * The Missing Dot lockup (spec §4): the Hot PLA dot that "nfinit" lost from
 * "infinite", followed by the name in the serif italic.
 */
export function Wordmark({
  href = "/",
  size = 22,
  className = "",
}: {
  href?: string | null;
  size?: number;
  className?: string;
}) {
  const content = (
    <>
      <span className="wb-dot" aria-hidden="true" />
      <span>nfinit</span>
    </>
  );

  if (href === null) {
    return (
      <span className={`wb-wordmark ${className}`} style={{ fontSize: size }}>
        {content}
      </span>
    );
  }

  return (
    <Link
      href={href}
      aria-label="nfinit home"
      className={`wb-wordmark ${className}`}
      style={{ fontSize: size }}
    >
      {content}
    </Link>
  );
}
