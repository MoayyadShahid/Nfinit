"use client";

import { ContactShadows, OrbitControls, RoundedBox } from "@react-three/drei";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useEffect, useRef } from "react";
import type { Group } from "three";

/*
 * A small, hand-built 5" quad frame for the landing hero. Scene units are
 * centimetres. Colours follow the render palette (spec §2.5): graphite frame,
 * a single Hot PLA part (the camera mount), bone props, clay floor.
 */

const GRAPHITE = "#2B2A28";
const BONE = "#E6DECF";
const HOT_PLA = "#EE4A0E";
const METAL = "#B9B5AD";
const MOTOR_RADIUS = 11; // 220 mm motor-to-motor diagonal.

function Prop({ spin }: { spin: boolean }) {
  const ref = useRef<Group>(null);
  useFrame((_, delta) => {
    if (spin && ref.current) ref.current.rotation.y += delta * 5;
  });
  return (
    <group ref={ref} position={[0, 2.05, 0]}>
      <mesh rotation={[0.12, 0, 0]}>
        <boxGeometry args={[6.2, 0.07, 0.75]} />
        <meshStandardMaterial color={BONE} roughness={0.55} transparent opacity={0.92} />
      </mesh>
      <mesh>
        <cylinderGeometry args={[0.35, 0.35, 0.3, 20]} />
        <meshStandardMaterial color={METAL} metalness={0.6} roughness={0.35} />
      </mesh>
    </group>
  );
}

function Arm({ angle, spin }: { angle: number; spin: boolean }) {
  return (
    <group rotation={[0, angle, 0]}>
      <RoundedBox args={[MOTOR_RADIUS, 0.5, 1.5]} radius={0.2} position={[MOTOR_RADIUS / 2, 0, 0]}>
        <meshStandardMaterial color={GRAPHITE} roughness={0.8} />
      </RoundedBox>
      <group position={[MOTOR_RADIUS, 0, 0]}>
        <mesh>
          <cylinderGeometry args={[1.55, 1.55, 0.5, 32]} />
          <meshStandardMaterial color={GRAPHITE} roughness={0.8} />
        </mesh>
        {/* Motor: dark stator base, brushed bell, shaft. */}
        <mesh position={[0, 0.65, 0]}>
          <cylinderGeometry args={[1.1, 1.15, 0.8, 32]} />
          <meshStandardMaterial color="#3A3834" roughness={0.6} metalness={0.3} />
        </mesh>
        <mesh position={[0, 1.35, 0]}>
          <cylinderGeometry args={[1.05, 1.1, 0.7, 32]} />
          <meshStandardMaterial color={METAL} roughness={0.35} metalness={0.7} />
        </mesh>
        <Prop spin={spin} />
      </group>
    </group>
  );
}

function Drone({ animate }: { animate: boolean }) {
  const ref = useRef<Group>(null);
  useFrame(({ clock }) => {
    if (!animate || !ref.current) return;
    const t = clock.getElapsedTime();
    ref.current.position.y = Math.sin(t * 1.4) * 0.25;
    ref.current.rotation.z = Math.sin(t * 0.9) * 0.025;
    ref.current.rotation.x = Math.cos(t * 0.7) * 0.02;
  });

  const standoffs: [number, number][] = [
    [1.6, 2.6],
    [-1.6, 2.6],
    [1.6, -2.6],
    [-1.6, -2.6],
  ];

  return (
    <group ref={ref}>
      {/* Bottom plate and arms. */}
      <RoundedBox args={[4.8, 0.45, 8.4]} radius={0.2}>
        <meshStandardMaterial color={GRAPHITE} roughness={0.8} />
      </RoundedBox>
      {[45, 135, 225, 315].map((deg) => (
        <Arm key={deg} angle={(deg * Math.PI) / 180} spin={animate} />
      ))}

      {/* Standoffs and top plate. */}
      {standoffs.map(([x, z]) => (
        <mesh key={`${x}${z}`} position={[x, 1.2, z]}>
          <cylinderGeometry args={[0.2, 0.2, 2, 12]} />
          <meshStandardMaterial color={METAL} metalness={0.6} roughness={0.35} />
        </mesh>
      ))}
      <RoundedBox args={[4.4, 0.35, 7.4]} radius={0.15} position={[0, 2.3, 0]}>
        <meshStandardMaterial color={GRAPHITE} roughness={0.8} />
      </RoundedBox>

      {/* Battery with a strap. */}
      <RoundedBox args={[3.4, 1.7, 6]} radius={0.3} position={[0, 3.35, -0.4]}>
        <meshStandardMaterial color="#3C3A36" roughness={0.7} />
      </RoundedBox>
      <mesh position={[0, 3.35, -0.4]}>
        <boxGeometry args={[3.5, 1.78, 0.6]} />
        <meshStandardMaterial color="#1E1D1B" roughness={0.9} />
      </mesh>

      {/* The one Hot PLA part: a printed camera mount, with the camera. */}
      <RoundedBox args={[3, 1.9, 1.3]} radius={0.25} position={[0, 1.2, 4.1]}>
        <meshStandardMaterial color={HOT_PLA} roughness={0.7} />
      </RoundedBox>
      <RoundedBox args={[1.9, 1.7, 1.5]} radius={0.2} position={[0, 1.25, 4.35]}>
        <meshStandardMaterial color="#1E1D1B" roughness={0.5} />
      </RoundedBox>
      <mesh position={[0, 1.25, 5.2]} rotation={[Math.PI / 2, 0, 0]}>
        <cylinderGeometry args={[0.55, 0.65, 0.5, 24]} />
        <meshStandardMaterial color="#111" roughness={0.2} metalness={0.4} />
      </mesh>
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
      camera={{ position: [32, 23, 38], fov: 39 }}
      gl={{ antialias: true, alpha: true }}
      aria-label="A 5 inch quadcopter frame you can drag to spin"
      role="img"
      style={{ cursor: "grab" }}
    >
      <ambientLight intensity={0.55} />
      <hemisphereLight args={["#ffffff", "#DDD3C2", 0.7]} />
      <directionalLight position={[-8, 14, 8]} intensity={2.1} />
      <directionalLight position={[10, 4, -6]} intensity={0.5} />
      <group position={[0, 0.2, 0]}>
        <Drone animate={animate} />
      </group>
      <ContactShadows
        position={[0, -1.6, 0]}
        opacity={0.35}
        scale={34}
        blur={2.6}
        far={8}
        resolution={512}
        color="#3C2A1A"
      />
      <OrbitControls
        enablePan={false}
        enableZoom={false}
        autoRotate={animate}
        autoRotateSpeed={0.9}
        minPolarAngle={0.75}
        maxPolarAngle={1.3}
        target={[0, 1, 0]}
      />
      <TouchPanY />
    </Canvas>
  );
}
