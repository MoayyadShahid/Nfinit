"use client";

import { Center, GizmoHelper, GizmoViewcube, Grid, OrbitControls, useGLTF } from "@react-three/drei";
import { Canvas, ThreeEvent, useThree } from "@react-three/fiber";
import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import * as THREE from "three";

const PHOTO_BOOTH_GRAY = "#d4d4d4";
const NORMAL_TOLERANCE = 0.01;

interface FaceSelection {
  point: THREE.Vector3;
  normal: THREE.Vector3;
}

function SceneBackground() {
  const { scene } = useThree();
  useEffect(() => {
    scene.background = new THREE.Color(PHOTO_BOOTH_GRAY);
  }, [scene]);
  return null;
}

function FaceGrid({ selection }: { selection: FaceSelection }) {
  const quaternion = useMemo(() => {
    const up = new THREE.Vector3(0, 1, 0);
    return new THREE.Quaternion().setFromUnitVectors(up, selection.normal);
  }, [selection.normal]);

  const position = useMemo(() => {
    return selection.point
      .clone()
      .add(selection.normal.clone().multiplyScalar(0.005));
  }, [selection.point, selection.normal]);

  return (
    <group position={position} quaternion={quaternion}>
      <Grid
        infiniteGrid
        cellSize={0.25}
        sectionSize={1}
        cellColor="#5b9bd5"
        sectionColor="#2e75b6"
        fadeDistance={15}
        fadeStrength={2}
        cellThickness={0.5}
        sectionThickness={0.8}
      />
    </group>
  );
}

function ClickableModel({
  url,
  onFaceClick,
}: {
  url: string;
  onFaceClick: (sel: FaceSelection) => void;
}) {
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

  const handleClick = useCallback(
    (e: ThreeEvent<MouseEvent>) => {
      e.stopPropagation();
      if (!e.face) return;

      const worldNormal = e.face.normal
        .clone()
        .transformDirection(e.object.matrixWorld)
        .normalize();

      const snapped = new THREE.Vector3(
        Math.abs(worldNormal.x) < NORMAL_TOLERANCE ? 0 : worldNormal.x,
        Math.abs(worldNormal.y) < NORMAL_TOLERANCE ? 0 : worldNormal.y,
        Math.abs(worldNormal.z) < NORMAL_TOLERANCE ? 0 : worldNormal.z
      ).normalize();

      onFaceClick({ point: e.point.clone(), normal: snapped });
    },
    [onFaceClick]
  );

  return (
    <Center>
      <primitive object={scene} scale={100} onClick={handleClick} />
    </Center>
  );
}

function ClickablePlaceholder({
  onFaceClick,
}: {
  onFaceClick: (sel: FaceSelection) => void;
}) {
  const handleClick = useCallback(
    (e: ThreeEvent<MouseEvent>) => {
      e.stopPropagation();
      if (!e.face) return;

      const worldNormal = e.face.normal
        .clone()
        .transformDirection(e.object.matrixWorld)
        .normalize();

      onFaceClick({ point: e.point.clone(), normal: worldNormal });
    },
    [onFaceClick]
  );

  return (
    <mesh onClick={handleClick}>
      <boxGeometry args={[1, 1, 1]} />
      <meshStandardMaterial color="#9ca3af" wireframe />
    </mesh>
  );
}

function Scene({
  glbUrl,
  onFaceClick,
}: {
  glbUrl: string | null;
  onFaceClick: (sel: FaceSelection) => void;
}) {
  if (!glbUrl) {
    return <ClickablePlaceholder onFaceClick={onFaceClick} />;
  }

  return (
    <Suspense fallback={null}>
      <ClickableModel key={glbUrl} url={glbUrl} onFaceClick={onFaceClick} />
    </Suspense>
  );
}

function ClearSelectionOnMiss({ onMiss }: { onMiss: () => void }) {
  const { scene, camera, gl } = useThree();

  useEffect(() => {
    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();

    const handleClick = (e: MouseEvent) => {
      const rect = gl.domElement.getBoundingClientRect();
      pointer.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
      raycaster.setFromCamera(pointer, camera);

      const meshes: THREE.Object3D[] = [];
      scene.traverse((obj) => {
        if (obj instanceof THREE.Mesh) meshes.push(obj);
      });

      const hits = raycaster.intersectObjects(meshes, false);
      if (hits.length === 0) onMiss();
    };

    gl.domElement.addEventListener("click", handleClick);
    return () => gl.domElement.removeEventListener("click", handleClick);
  }, [scene, camera, gl, onMiss]);

  return null;
}

interface ViewportPaneProps {
  glbUrl: string | null;
  isLoading: boolean;
}

export function ViewportPane({ glbUrl, isLoading }: ViewportPaneProps) {
  const [faceSelection, setFaceSelection] = useState<FaceSelection | null>(null);

  const clearSelection = useCallback(() => setFaceSelection(null), []);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") clearSelection();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [clearSelection]);

  useEffect(() => {
    setFaceSelection(null);
  }, [glbUrl]);

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
        <ClearSelectionOnMiss onMiss={clearSelection} />
        <OrbitControls makeDefault />
        <GizmoHelper alignment="bottom-right" margin={[80, 80]}>
          <GizmoViewcube
            color="#888"
            textColor="#fff"
            strokeColor="#555"
            hoverColor="#60a5fa"
          />
        </GizmoHelper>
        <ambientLight intensity={0.7} />
        <directionalLight position={[5, 8, 5]} intensity={1.2} />
        <directionalLight position={[-5, 5, -5]} intensity={0.6} />
        <directionalLight position={[0, -5, 5]} intensity={0.4} />
        {faceSelection && <FaceGrid selection={faceSelection} />}
        <Suspense fallback={null}>
          <Scene glbUrl={glbUrl} onFaceClick={setFaceSelection} />
        </Suspense>
      </Canvas>
    </div>
  );
}
