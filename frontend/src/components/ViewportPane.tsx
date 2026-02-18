"use client";

import { Center, OrbitControls, useGLTF } from "@react-three/drei";
import { Canvas, useThree } from "@react-three/fiber";
import { Suspense, useEffect } from "react";
import * as THREE from "three";

// Fusion 360 Photo Booth–style light gray environment
const PHOTO_BOOTH_GRAY = "#d4d4d4";

function SceneBackground() {
  const { scene } = useThree();
  useEffect(() => {
    scene.background = new THREE.Color(PHOTO_BOOTH_GRAY);
  }, [scene]);
  return null;
}

function Model({ url }: { url: string }) {
  const { scene } = useGLTF(url);

  useEffect(() => {
    scene.traverse((child) => {
      if (child instanceof THREE.Mesh) {
        child.material = child.material.clone();
        if (child.material instanceof THREE.MeshStandardMaterial) {
          child.material.color = new THREE.Color(0x6b7280);
          child.material.metalness = 0.3;
          child.material.roughness = 0.6;
        }
      }
    });
  }, [scene]);

  return (
    <Center>
      <primitive
        object={scene}
        scale={100}
      />
    </Center>
  );
}

function Scene({ glbUrl }: { glbUrl: string | null }) {
  if (!glbUrl) {
    return (
      <mesh>
        <boxGeometry args={[1, 1, 1]} />
        <meshStandardMaterial color="#9ca3af" wireframe />
      </mesh>
    );
  }

  return (
    <Suspense fallback={null}>
      <Model key={glbUrl} url={glbUrl} />
    </Suspense>
  );
}

interface ViewportPaneProps {
  glbUrl: string | null;
  isLoading: boolean;
}

export function ViewportPane({ glbUrl, isLoading }: ViewportPaneProps) {
  return (
    <div className="relative h-full w-full bg-[#d4d4d4]">
      {isLoading && (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-[#d4d4d4]/90">
          <div className="flex flex-col items-center gap-3">
            <div className="h-10 w-10 animate-spin rounded-full border-2 border-zinc-300 border-t-blue-500" />
            <span className="text-sm text-zinc-600">Generating mesh...</span>
          </div>
        </div>
      )}
      <Canvas
        camera={{ position: [5, 5, 5], fov: 50 }}
        gl={{ antialias: true }}
        className="h-full w-full"
      >
        <SceneBackground />
        <OrbitControls />
        <ambientLight intensity={0.7} />
        <directionalLight position={[5, 8, 5]} intensity={1.2} />
        <directionalLight position={[-5, 5, -5]} intensity={0.6} />
        <directionalLight position={[0, -5, 5]} intensity={0.4} />
        <Suspense fallback={null}>
          <Scene glbUrl={glbUrl} />
        </Suspense>
      </Canvas>
    </div>
  );
}
