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
 * carbon frame: flat arms with drilled motor pads, a bottom plate, standoffs,
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

/** One arm along +x: a tapered bar ending in a round motor pad. */
function armShape() {
  const root = -2;
  const rootHalf = 0.8;
  const tipHalf = 0.58;
  const a = Math.asin(tipHalf / PAD_RADIUS);
  const meet = MOTOR_RADIUS - Math.sqrt(PAD_RADIUS ** 2 - tipHalf ** 2);

  const s = new Shape();
  s.moveTo(root, -rootHalf);
  s.lineTo(meet, -tipHalf);
  s.absarc(MOTOR_RADIUS, 0, PAD_RADIUS, Math.PI + a, 3 * Math.PI - a, false);
  s.lineTo(root, rootHalf);
  s.closePath();

  // 12 × 12 mm motor pattern, shaft clearance, and a lightening slot.
  for (const [dx, dy] of [
    [0.6, 0.6],
    [-0.6, 0.6],
    [0.6, -0.6],
    [-0.6, -0.6],
  ]) {
    s.holes.push(circleHole(MOTOR_RADIUS + dx, dy, 0.16));
  }
  s.holes.push(circleHole(MOTOR_RADIUS, 0, 0.42));
  s.holes.push(slotHole(3.2, 7.4, 0, 0.2));
  return s;
}

function bottomPlateShape() {
  const s = roundedRect(4.6, 10.4, 0.9);
  // 30.5 mm flight-controller stack pattern.
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
  rotationY = 0,
}: {
  geometry: ExtrudeGeometry;
  y: number;
  map: CanvasTexture;
  rotationY?: number;
}) {
  return (
    <group rotation={[0, rotationY, 0]} position={[0, y, 0]}>
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
      arm: extrude(armShape(), 0.4),
      bottom: extrude(bottomPlateShape(), 0.2),
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
      <FlatPart geometry={geo.bottom} y={-0.25} map={map} />
      {ARM_ANGLES.map((deg) => (
        <FlatPart
          key={deg}
          geometry={geo.arm}
          y={0}
          map={map}
          rotationY={(deg * Math.PI) / 180}
        />
      ))}
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
