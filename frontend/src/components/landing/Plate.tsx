import type { CSSProperties, ReactNode } from "react";
import { LayerReveal } from "./LayerReveal";

/**
 * A plate: one part on clay, with mono corner labels (spec §6). Until real
 * renders exist it holds a labelled demo slot rather than fake product UI
 * (spec §7, "Visual assets").
 */
export function Plate({
  label,
  spec,
  prompt,
  slotLabel = "Demo · coming soon",
  halted,
  className = "",
  style,
  children,
}: {
  label: string;
  spec?: ReactNode;
  prompt?: string;
  slotLabel?: string;
  halted?: boolean;
  className?: string;
  style?: CSSProperties;
  children?: ReactNode;
}) {
  return (
    <figure
      className={`wb-plate ${className}`}
      style={style}
      data-has-prompt={Boolean(prompt)}
      aria-label={`${label}: demo placeholder`}
    >
      <span className="wb-plate-corner wb-plate-tl">{label}</span>
      <LayerReveal halted={halted}>
        <div className="wb-slot">
          <span className="type-label">{slotLabel}</span>
        </div>
      </LayerReveal>
      {children}
      {spec && <span className="wb-plate-corner wb-plate-br">{spec}</span>}
      {prompt && (
        <figcaption className="wb-plate-prompt">“{prompt}”</figcaption>
      )}
    </figure>
  );
}
