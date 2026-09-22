"use client";

import { ContactShadows, OrbitControls } from "@react-three/drei";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import {
  CanvasTexture,
  ExtrudeGeometry,
  Path,
  RepeatWrapping,
  SRGBColorSpace,
  Shape,
  type Group,
} from "three";

/*
 * A bare 5-inch FPV frame for the landing hero, modelled on a real stretched-X
 * carbon frame: a one-piece bottom plate with drilled motor pads, standoffs,
 * a top plate with an X cut-out and a camera cage. No motors, props or
 * electronics. Scene units are centimetres. The two camera-cage nuts are the
 * only Hot PLA on screen (spec §2).
 */

const MOTOR_RADIUS = 11; // 220 mm motor-to-motor diagonal.
const PAD_RADIUS = 1.35;
const ARM_ANGLES = [58, 122, 238, 302]; // Degrees from +x; +y is forward.
const HOT_PLA = "#EE4A0E";

// ---------- 2D profiles (x right, y forward) ----------

function circleHole(x: number, y: number, r: number) {
  const hole = new Path();
  hole.absarc(x, y, r, 0, Math.PI * 2, false);
  return hole;
}

function slotHole(x0: number, x1: number, y: number, r: number) {
  const hole = new Path();
  hole.absarc(x0, y, r, Math.PI / 2, (Math.PI * 3) / 2, false);
  hole.absarc(x1, y, r, -Math.PI / 2, Math.PI / 2, false);
  return hole;
}

function roundedRect(w: number, h: number, r: number, cx = 0, cy = 0) {
  const s = new Shape();
  const x = cx - w / 2;
  const y = cy - h / 2;
  s.moveTo(x + r, y);
  s.lineTo(x + w - r, y);
  s.absarc(x + w - r, y + r, r, -Math.PI / 2, 0, false);
  s.lineTo(x + w, y + h - r);
  s.absarc(x + w - r, y + h - r, r, 0, Math.PI / 2, false);
  s.lineTo(x + r, y + h);
  s.absarc(x + r, y + h - r, r, Math.PI / 2, Math.PI, false);
  s.lineTo(x, y + r);
  s.absarc(x + r, y + r, r, Math.PI, (Math.PI * 3) / 2, false);
  return s;
}

type Vec = [number, number];

/** Body outline: a chamfered rectangle, counter-clockwise. */
const BODY_HALF_W = 2.3;
const BODY_HALF_L = 5.2;
const CHAMFER = 0.7;
const BODY: Vec[] = [
  [BODY_HALF_W - CHAMFER, -BODY_HALF_L],
  [BODY_HALF_W, -BODY_HALF_L + CHAMFER],
  [BODY_HALF_W, BODY_HALF_L - CHAMFER],
  [BODY_HALF_W - CHAMFER, BODY_HALF_L],
  [-BODY_HALF_W + CHAMFER, BODY_HALF_L],
  [-BODY_HALF_W, BODY_HALF_L - CHAMFER],
  [-BODY_HALF_W, -BODY_HALF_L + CHAMFER],
  [-BODY_HALF_W + CHAMFER, -BODY_HALF_L],
];

/** Where segment a→b (a inside the body) crosses the body outline. */
function exitPoint(a: Vec, b: Vec): { point: Vec; param: number } {
  const n = BODY.length;
  for (let k = 0; k < n; k++) {
    const p = BODY[k];
    const q = BODY[(k + 1) % n];
    const r: Vec = [b[0] - a[0], b[1] - a[1]];
    const e: Vec = [q[0] - p[0], q[1] - p[1]];
    const den = r[0] * e[1] - r[1] * e[0];
    if (Math.abs(den) < 1e-9) continue;
    const w: Vec = [p[0] - a[0], p[1] - a[1]];
    const s = (w[0] * e[1] - w[1] * e[0]) / den; // along a→b
    const f = (w[0] * r[1] - w[1] * r[0]) / den; // along the body edge
    if (s > 0 && s <= 1 && f >= 0 && f <= 1) {
      return { point: [a[0] + s * r[0], a[1] + s * r[1]], param: k + f };
    }
  }
  throw new Error("Arm edge does not leave the body");
}

/**
 * The unibody bottom plate: body and four arms cut as one flat outline, like
 * a CNC'd carbon frame, so everything sits on one level.
 */
function unibodyShape() {
  const rootHalf = 0.8;
  const tipHalf = 0.58;
  const a = Math.asin(tipHalf / PAD_RADIUS);
  const meet = MOTOR_RADIUS - Math.sqrt(PAD_RADIUS ** 2 - tipHalf ** 2);

  const arms = ARM_ANGLES.map((deg) => {
    const t = (deg * Math.PI) / 180;
    const d: Vec = [Math.cos(t), Math.sin(t)];
    const nrm: Vec = [-d[1], d[0]];
    const edge = (side: 1 | -1) => {
      const root: Vec = [side * rootHalf * nrm[0], side * rootHalf * nrm[1]];
      const tip: Vec = [
        meet * d[0] + side * tipHalf * nrm[0],
        meet * d[1] + side * tipHalf * nrm[1],
      ];
      return { tip, exit: exitPoint(root, tip) };
    };
    return { t, d, right: edge(-1), left: edge(1) };
  });

  const n = BODY.length;
  const s = new Shape();
  arms.forEach((arm, i) => {
    const [cx, cy] = [MOTOR_RADIUS * arm.d[0], MOTOR_RADIUS * arm.d[1]];
    if (i === 0) s.moveTo(...arm.right.exit.point);
    else s.lineTo(...arm.right.exit.point);
    s.lineTo(...arm.right.tip);
    s.absarc(cx, cy, PAD_RADIUS, arm.t + Math.PI + a, arm.t + 3 * Math.PI - a, false);
    s.lineTo(...arm.left.exit.point);

    // Walk the body outline counter-clockwise to the next arm.
    const next = arms[(i + 1) % arms.length];
    const from = arm.left.exit.param;
    let to = next.right.exit.param;
    if (to < from) to += n;
    for (let j = Math.ceil(from); j <= Math.floor(to); j++) {
      if (j === from) continue;
      s.lineTo(...BODY[j % n]);
    }
  });
  s.closePath();

  // Motor pads: 12 × 12 mm pattern and shaft clearance. Arm lightening slots.
  for (const arm of arms) {
    const [cx, cy] = [MOTOR_RADIUS * arm.d[0], MOTOR_RADIUS * arm.d[1]];
    for (const [u, v] of [
      [0.6, 0.6],
      [-0.6, 0.6],
      [0.6, -0.6],
      [-0.6, -0.6],
    ]) {
      const x = cx + u * arm.d[0] - v * arm.d[1];
      const y = cy + u * arm.d[1] + v * arm.d[0];
      s.holes.push(circleHole(x, y, 0.16));
    }
    s.holes.push(circleHole(cx, cy, 0.42));
    s.holes.push(rotatedSlot(arm.t, 3.6, 7.6, 0.2));
  }

  // 30.5 mm flight-controller stack and two body cut-outs.
  for (const [x, y] of [
    [1.525, 1.525],
    [-1.525, 1.525],
    [1.525, -1.525],
    [-1.525, -1.525],
  ]) {
    s.holes.push(circleHole(x, y, 0.17));
  }
  s.holes.push(slotHole(-0.9, 0.9, -3.9, 0.3));
  s.holes.push(slotHole(-0.9, 0.9, 3.9, 0.3));
  return s;
}

/** A rounded slot along direction `t`, from distance t0 to t1. */
function rotatedSlot(t: number, t0: number, t1: number, r: number) {
  const [dx, dy] = [Math.cos(t), Math.sin(t)];
  const hole = new Path();
  hole.absarc(t0 * dx, t0 * dy, r, t + Math.PI / 2, t + (Math.PI * 3) / 2, false);
  hole.absarc(t1 * dx, t1 * dy, r, t - Math.PI / 2, t + Math.PI / 2, false);
  return hole;
}

function topPlateShape() {
  const s = roundedRect(3.8, 9.6, 0.7);
  // Four triangles removed leave an X of material over the stack.
  const half = 1.25;
  const gap = 0.26;
  const cy = -0.6;
  const tri = (pts: [number, number][]) => {
    const p = new Path();
    p.moveTo(pts[0][0], pts[0][1] + cy);
    for (const [x, y] of pts.slice(1)) p.lineTo(x, y + cy);
    p.closePath();
    return p;
  };
  const k = gap * 1.4;
  s.holes.push(tri([[-half + k, half], [half - k, half], [0, k]]));
  s.holes.push(tri([[-half + k, -half], [0, -k], [half - k, -half]]));
  s.holes.push(tri([[-half, -half + k], [-half, half - k], [-k, 0]]));
  s.holes.push(tri([[half, -half + k], [k, 0], [half, half - k]]));
  s.holes.push(slotHole(-0.7, 0.7, 3.4, 0.28));
  s.holes.push(circleHole(0, -3.8, 0.3));
  return s;
}

/** Camera-cage side plate, drawn in (forward, up) coordinates. */
function cagePlateShape() {
  const s = roundedRect(2.6, 2.9, 0.45, 0, 1.45);
  s.holes.push(circleHole(0.1, 1.55, 0.2));
  s.holes.push(slotHole(-0.7, -0.3, 0.6, 0.16));
  return s;
}

function extrude(shape: Shape, depth: number) {
  return new ExtrudeGeometry(shape, {
    depth,
    bevelEnabled: true,
    bevelThickness: 0.03,
    bevelSize: 0.03,
    bevelSegments: 2,
    curveSegments: 24,
  });
}

// ---------- Materials ----------

/** A procedural 2×2 twill weave so the plates read as carbon fibre. */
function useCarbonTexture() {
  return useMemo(() => {
    const size = 128;
    const cell = 16;
    const canvas = document.createElement("canvas");
    canvas.width = size;
    canvas.height = size;
    const ctx = canvas.getContext("2d")!;
    ctx.fillStyle = "#18181a";
    ctx.fillRect(0, 0, size, size);
    for (let i = 0; i < size / cell; i++) {
      for (let j = 0; j < size / cell; j++) {
        const twill = Math.floor((i + j) / 2) % 2 === 0;
        const x = i * cell;
        const y = j * cell;
        const grad = twill
          ? ctx.createLinearGradient(x, y, x + cell, y)
          : ctx.createLinearGradient(x, y, x, y + cell);
        grad.addColorStop(0, "#1c1c1f");
        grad.addColorStop(0.5, "#34343a");
        grad.addColorStop(1, "#1c1c1f");
        ctx.fillStyle = grad;
        ctx.fillRect(x + 0.5, y + 0.5, cell - 1, cell - 1);
      }
    }
    const texture = new CanvasTexture(canvas);
    texture.wrapS = RepeatWrapping;
    texture.wrapT = RepeatWrapping;
    texture.repeat.set(0.45, 0.45);
    texture.colorSpace = SRGBColorSpace;
    texture.anisotropy = 4;
    return texture;
  }, []);
}

function Carbon({ map }: { map: CanvasTexture }) {
  return <meshStandardMaterial map={map} roughness={0.55} metalness={0.05} />;
}

function Aluminium() {
  return <meshStandardMaterial color="#C4C4C8" metalness={0.8} roughness={0.28} />;
}

// ---------- Parts ----------

/** Lays a 2D profile flat: shape +y points forward (world −z), depth goes up. */
function FlatPart({
  geometry,
  y,
  map,
}: {
  geometry: ExtrudeGeometry;
  y: number;
  map: CanvasTexture;
}) {
  return (
    <group position={[0, y, 0]}>
      <mesh geometry={geometry} rotation={[-Math.PI / 2, 0, 0]}>
        <Carbon map={map} />
      </mesh>
    </group>
  );
}

function Standoff({ x, z, from, to }: { x: number; z: number; from: number; to: number }) {
  const h = to - from;
  return (
    <group position={[x, from, z]}>
      <mesh position={[0, h / 2, 0]}>
        <cylinderGeometry args={[0.24, 0.24, h, 6]} />
        <Aluminium />
      </mesh>
      {/* Button-head screw on the top plate. */}
      <mesh position={[0, h + 0.3, 0]}>
        <cylinderGeometry args={[0.26, 0.28, 0.14, 20]} />
        <meshStandardMaterial color="#2A2A2C" metalness={0.6} roughness={0.4} />
      </mesh>
    </group>
  );
}

function Frame({ animate }: { animate: boolean }) {
  const map = useCarbonTexture();
  const ref = useRef<Group>(null);

  const geo = useMemo(
    () => ({
      base: extrude(unibodyShape(), 0.4),
      top: extrude(topPlateShape(), 0.2),
      cage: extrude(cagePlateShape(), 0.2),
    }),
    [],
  );

  useEffect(
    () => () => {
      Object.values(geo).forEach((g) => g.dispose());
      map.dispose();
    },
    [geo, map],
  );

  useFrame(({ clock }) => {
    if (!animate || !ref.current) return;
    const t = clock.getElapsedTime();
    ref.current.position.y = Math.sin(t * 1.2) * 0.18;
  });

  const PLATE_TOP = 3.1;
  const standoffs: [number, number][] = [
    [1.5, -4.2],
    [-1.5, -4.2],
    [1.5, 0.9],
    [-1.5, 0.9],
    [1.5, 3.9],
    [-1.5, 3.9],
  ];

  return (
    <group ref={ref}>
      <FlatPart geometry={geo.base} y={0} map={map} />
      {standoffs.map(([x, z]) => (
        <Standoff key={`${x},${z}`} x={x} z={z} from={0.4} to={PLATE_TOP} />
      ))}
      <FlatPart geometry={geo.top} y={PLATE_TOP} map={map} />

      {/* Camera cage: two upright side plates at the front, with Hot PLA nuts. */}
      {[-1, 1].map((side) => (
        <group key={side} position={[side * 1.75, 0.4, -3.9]} rotation={[0, Math.PI / 2, 0]}>
          <mesh geometry={geo.cage} position={[0, 0, side > 0 ? 0 : -0.2]}>
            <Carbon map={map} />
          </mesh>
          <mesh
            position={[0.1, 1.55, side > 0 ? 0.28 : -0.28]}
            rotation={[Math.PI / 2, 0, 0]}
          >
            <cylinderGeometry args={[0.32, 0.32, 0.18, 6]} />
            <meshStandardMaterial color={HOT_PLA} metalness={0.5} roughness={0.35} />
          </mesh>
        </group>
      ))}
    </group>
  );
}

/** Lets the page keep scrolling vertically on touch; drag sideways to spin. */
function TouchPanY() {
  const { gl } = useThree();
  useEffect(() => {
    const id = window.setTimeout(() => {
      gl.domElement.style.touchAction = "pan-y";
    }, 0);
    return () => window.clearTimeout(id);
  }, [gl]);
  return null;
}

export default function DroneScene({
  active,
  reducedMotion,
}: {
  active: boolean;
  reducedMotion: boolean;
}) {
  const animate = active && !reducedMotion;
  return (
    <Canvas
      frameloop={active ? "always" : "never"}
      dpr={[1, 2]}
      camera={{ position: [30, 26, 34], fov: 35 }}
      gl={{ antialias: true, alpha: true }}
      aria-label="A 5 inch FPV drone frame you can drag to spin"
      role="img"
      style={{ cursor: "grab" }}
    >
      <ambientLight intensity={0.5} />
      <hemisphereLight args={["#ffffff", "#DDD3C2", 0.6]} />
      <directionalLight position={[-10, 16, 8]} intensity={2} />
      <directionalLight position={[12, 6, -10]} intensity={0.9} />
      <group position={[0, 0.4, 0]} rotation={[0, Math.PI + 0.55, 0]}>
        <Frame animate={animate} />
      </group>
      <ContactShadows
        position={[0, -1.4, 0]}
        opacity={0.32}
        scale={36}
        blur={2.6}
        far={8}
        resolution={512}
        color="#3C2A1A"
      />
      <OrbitControls
        enablePan={false}
        enableZoom={false}
        autoRotate={animate}
        autoRotateSpeed={0.8}
        minPolarAngle={0.6}
        maxPolarAngle={1.25}
        target={[0, 1.2, 0]}
      />
      <TouchPanY />
    </Canvas>
  );
}
