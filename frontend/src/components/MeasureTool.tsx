"use client";

import { sandboxRequest } from "@/lib/sandbox";
import { Html, Line } from "@react-three/drei";
import { Ruler, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import type * as THREE from "three";

/** A point the user clicked on the part, in the scene and in CAD millimetres. */
export type MeasurePick = {
  point: THREE.Vector3;
  cadPoint: THREE.Vector3;
  faceId?: string;
  surfaceType?: string;
};

type FaceFacts = { surface_type: string; area_mm2: number; radius_mm: number | null };
type Closest = { distance_mm: number };

const MARK = "#e2541f";

function format(value: number) {
  return value.toFixed(2);
}

function describeFace(facts: FaceFacts | null | undefined, fallback?: string) {
  if (!facts) return fallback ? `${fallback[0].toUpperCase()}${fallback.slice(1)} face` : "Point";
  if (facts.radius_mm && (facts.surface_type === "cylinder" || facts.surface_type === "sphere")) {
    return `${facts.surface_type === "cylinder" ? "Round face" : "Sphere"} ⌀ ${format(2 * facts.radius_mm)} mm`;
  }
  if (facts.radius_mm) return `${facts.surface_type} r ${format(facts.radius_mm)} mm`;
  return `${facts.surface_type[0].toUpperCase()}${facts.surface_type.slice(1)} · ${Math.round(facts.area_mm2).toLocaleString()} mm²`;
}

async function measure(code: string, query: object): Promise<unknown> {
  const response = await sandboxRequest("measure-model", { code, query }, { signal: AbortSignal.timeout(30_000) });
  if (!response.ok) throw new Error("measure failed");
  return response.json();
}

/**
 * Click one point to see what the face is (a hole's diameter, a plane's
 * area); click a second to see the distance between the points, along each
 * axis, and the exact closest distance between the two faces.
 */
export function useMeasure(code: string) {
  const [picks, setPicks] = useState<MeasurePick[]>([]);
  const [faces, setFaces] = useState<(FaceFacts | null)[]>([]);
  const [closest, setClosest] = useState<Closest | null>(null);
  // Answers apply only to the measurement that asked for them.
  const session = useRef(0);
  // One request at a time: the backend runs at most two sandbox jobs per user.
  const queue = useRef<Promise<unknown>>(Promise.resolve());

  const clear = useCallback(() => {
    session.current += 1;
    setPicks([]);
    setFaces([]);
    setClosest(null);
  }, []);

  const ask = useCallback(
    (query: object, apply: (answer: unknown) => void) => {
      const id = session.current;
      queue.current = queue.current
        .then(() => (id === session.current ? measure(code, query) : null))
        .then((answer) => {
          if (answer !== null && id === session.current) apply(answer);
        })
        .catch(() => {});
    },
    [code]
  );

  const add = useCallback(
    (pick: MeasurePick) => {
      const restart = picks.length >= 2;
      const next = restart ? [pick] : [...picks, pick];
      if (next.length === 1) session.current += 1;
      setPicks(next);
      setFaces((current) => (next.length === 1 ? [null] : [current[0] ?? null, null]));
      setClosest(null);
      const index = next.length - 1;
      if (pick.faceId) {
        ask({ kind: "face", face_id: pick.faceId }, (facts) =>
          setFaces((current) => {
            const updated = [...current];
            updated[index] = facts as FaceFacts;
            return updated;
          })
        );
      }
      const [first, second] = next;
      if (second && first.faceId && second.faceId && first.faceId !== second.faceId) {
        ask({ kind: "distance", a: first.faceId, b: second.faceId }, (answer) =>
          setClosest(answer as Closest)
        );
      }
    },
    [ask, picks]
  );

  // A new model makes old points meaningless.
  useEffect(() => clear, [code, clear]);

  return { picks, faces, closest, add, clear };
}

/** Points and the line between them, drawn over the part. */
export function MeasureMarks({ picks }: { picks: MeasurePick[] }) {
  const [first, second] = picks;
  return (
    <>
      {picks.map((pick, index) => (
        <Html key={index} position={pick.point} center zIndexRange={[30, 20]}>
          <span
            className="block size-2.5 rounded-full border-2 border-white shadow"
            style={{ background: MARK }}
          />
        </Html>
      ))}
      {first && second && (
        <>
          <Line points={[first.point, second.point]} color={MARK} lineWidth={2} depthTest={false} renderOrder={10} />
          <Html position={first.point.clone().add(second.point).multiplyScalar(0.5)} center zIndexRange={[30, 20]}>
            <span className="whitespace-nowrap rounded-md bg-[var(--sheet)] px-1.5 py-0.5 font-mono text-[11px] font-medium text-[var(--ink)] shadow">
              {format(first.cadPoint.distanceTo(second.cadPoint))} mm
            </span>
          </Html>
        </>
      )}
    </>
  );
}

export function MeasurePanel({
  active,
  onToggle,
  picks,
  faces,
  closest,
  onClear,
}: {
  active: boolean;
  onToggle: () => void;
  picks: MeasurePick[];
  faces: (FaceFacts | null)[];
  closest: Closest | null;
  onClear: () => void;
}) {
  const [first, second] = picks;
  const delta = first && second ? second.cadPoint.clone().sub(first.cadPoint) : null;
  return (
    <div className="absolute bottom-3 left-3 z-20 hidden flex-col items-start gap-2 sm:flex">
      {active && (
        <div className="theme-floating w-[250px] rounded-xl border p-3 text-[11px] shadow-xl" aria-live="polite">
          {picks.length === 0 ? (
            <p className="text-zinc-500">Click a point on the part.</p>
          ) : (
            <>
              <ul className="space-y-0.5 text-[var(--ink-2)]">
                {picks.map((pick, index) => (
                  <li key={index}>
                    <span className="mr-1.5 font-medium text-zinc-500">{index === 0 ? "A" : "B"}</span>
                    {describeFace(faces[index], pick.surfaceType)}
                  </li>
                ))}
              </ul>
              {delta ? (
                <div className="mt-2 border-t border-[var(--hairline)] pt-2">
                  <p className="font-medium">
                    Distance {format(first.cadPoint.distanceTo(second.cadPoint))} mm
                  </p>
                  <p className="mt-0.5 font-mono text-[10px] text-zinc-500">
                    Δx {format(Math.abs(delta.x))} · Δy {format(Math.abs(delta.y))} · Δz {format(Math.abs(delta.z))}
                  </p>
                  {closest && (
                    <p className="mt-1 text-zinc-500">
                      Closest between the faces {format(closest.distance_mm)} mm
                    </p>
                  )}
                </div>
              ) : (
                <p className="mt-1.5 text-zinc-500">Click a second point to measure between them.</p>
              )}
            </>
          )}
          {picks.length > 0 && (
            <button type="button" onClick={onClear} className="mt-2 flex items-center gap-1 text-zinc-500 hover:text-[var(--ink)]">
              <X className="size-3" />
              Clear
            </button>
          )}
        </div>
      )}
      <button
        type="button"
        onClick={onToggle}
        aria-pressed={active}
        className={`theme-floating flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[11px] font-medium shadow-sm ${
          active ? "text-[var(--accent)]" : "text-[var(--ink-2)]"
        }`}
      >
        <Ruler className="size-3.5" />
        {active ? "Measuring" : "Measure"}
      </button>
    </div>
  );
}
