"use client";

import { Center, GizmoHelper, GizmoViewcube, Grid, OrbitControls, useGLTF } from "@react-three/drei";
import { LayoutGrid } from "lucide-react";
import type { FaceSelection } from "@/lib/types";
import { Canvas, ThreeEvent, useThree } from "@react-three/fiber";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";

const NORMAL_TOLERANCE = 0.01;
const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";

interface ThreeFaceSelection {
  point: THREE.Vector3;
  normal: THREE.Vector3;
  cadPoint?: THREE.Vector3;
  cadNormal?: THREE.Vector3;
}

function FaceGrid({ selection }: { selection: ThreeFaceSelection }) {
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
  onFaceClick: (sel: ThreeFaceSelection) => void;
}) {
  const { scene } = useGLTF(url);

  useEffect(() => {
    scene.traverse((child) => {
      if (child instanceof THREE.Mesh) {
        child.material = child.material.clone();
        if (child.material instanceof THREE.MeshStandardMaterial) {
          child.material.color = new THREE.Color(0x485264);
          child.material.metalness = 0.18;
          child.material.roughness = 0.48;
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

      // build123d's GLTF export uses meters; convert mesh-local coordinates
      // back to the millimeters used by generated CAD code.
      const cadPoint = e.object
        .worldToLocal(e.point.clone())
        .multiplyScalar(1000);
      const cadNormal = e.face.normal.clone().normalize();

      onFaceClick({
        point: e.point.clone(),
        normal: snapped,
        cadPoint,
        cadNormal,
      });
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
  onFaceClick: (sel: ThreeFaceSelection) => void;
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
  onFaceClick: (sel: ThreeFaceSelection) => void;
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
  code: string;
  isLoading: boolean;
  showSelectionCard?: boolean;
  onSelectionChange?: (selection: FaceSelection | null) => void;
}

function ViewportContent({
  glbUrl,
  code,
  isLoading,
  showSelectionCard = true,
  onSelectionChange,
}: ViewportPaneProps) {
  const [faceSelection, setFaceSelection] = useState<ThreeFaceSelection | null>(null);
  const [resolvedFace, setResolvedFace] = useState<FaceSelection | null>(null);
  const [showGrid, setShowGrid] = useState(true);
  const [boothColor, setBoothColor] = useState("#ddd3c2");
  const resolutionRequest = useRef(0);

  useEffect(() => {
    const readBooth = () => {
      const value = getComputedStyle(document.documentElement)
        .getPropertyValue("--clay")
        .trim();
      if (value) setBoothColor(value);
    };
    readBooth();
    window.addEventListener("nfinit-theme-change", readBooth);
    return () => window.removeEventListener("nfinit-theme-change", readBooth);
  }, []);

  const clearSelection = useCallback(() => {
    resolutionRequest.current += 1;
    setFaceSelection(null);
    setResolvedFace(null);
    onSelectionChange?.(null);
  }, [onSelectionChange]);

  const selectFace = useCallback(
    async (selection: ThreeFaceSelection) => {
      setFaceSelection(selection);
      setResolvedFace(null);
      const geometricSelection: FaceSelection = {
        point: (selection.cadPoint ?? selection.point)
          .toArray()
          .map((value) => Number(value.toFixed(3))) as [
          number,
          number,
          number,
        ],
        normal: (selection.cadNormal ?? selection.normal)
          .toArray()
          .map((value) => Number(value.toFixed(4))) as [
          number,
          number,
          number,
        ],
      };
      onSelectionChange?.(geometricSelection);
      if (!glbUrl) return;

      const requestId = ++resolutionRequest.current;
      try {
        const response = await fetch(`${BACKEND_URL}/analyze-model`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ code, selection: geometricSelection }),
          signal: AbortSignal.timeout(30_000),
        });
        if (!response.ok) return;
        const analysis = await response.json();
        if (requestId !== resolutionRequest.current || !analysis.selectedFace) {
          return;
        }
        const semanticSelection: FaceSelection = {
          ...geometricSelection,
          entityId: analysis.selectedFace.faceId,
          topologyVersion: analysis.topologyVersion,
          surfaceType: analysis.selectedFace.surfaceType,
          confidence: analysis.selectedFace.confidence,
        };
        setResolvedFace(semanticSelection);
        onSelectionChange?.(semanticSelection);
      } catch {
        // Positional selection remains usable when semantic resolution fails.
      }
    },
    [code, glbUrl, onSelectionChange]
  );

  useEffect(
    () => () => {
      resolutionRequest.current += 1;
    },
    []
  );

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") clearSelection();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [clearSelection]);

  return (
    <div className="relative h-full w-full bg-[var(--clay)]">
      <div className="absolute right-3 top-3 z-20">
        <button
          type="button"
          onClick={() => setShowGrid((v) => !v)}
          title={showGrid ? "Hide face grid" : "Show face grid"}
          className={`flex h-8 items-center gap-1.5 rounded-lg border px-2.5 text-xs font-medium shadow-sm transition-colors ${
            showGrid
              ? "border-[var(--hairline-strong)] bg-[var(--ink)] text-[var(--paper)]"
              : "border-[var(--hairline)] bg-[var(--sheet)] text-[var(--ink-2)]"
          }`}
        >
          <LayoutGrid className="size-3.5" />
          Grid
        </button>
      </div>
      {faceSelection && showSelectionCard && (
        <div className="absolute bottom-3 left-3 z-20 rounded-xl border border-[var(--hairline-strong)] bg-[var(--sheet)] px-3.5 py-2.5 text-xs text-[var(--ink)] shadow-xl">
          <div className="font-medium">Face selected</div>
          <div className="mt-0.5 text-[10px] text-[var(--muted)]">
            {resolvedFace?.entityId
              ? `${resolvedFace.surfaceType ?? "surface"} · ${resolvedFace.entityId.slice(0, 13)}`
              : glbUrl
                ? "Resolving exact B-rep face…"
                : "Positional selection"}
          </div>
        </div>
      )}
      {isLoading && (
        <div className="absolute inset-0 z-10 flex items-center justify-center bg-[var(--clay)]/90">
          <div className="flex flex-col items-center gap-3">
            <div className="h-10 w-10 animate-spin rounded-full border-2 border-[var(--hairline-strong)] border-t-[var(--accent)]" />
            <span className="text-sm text-[var(--ink-2)]">Building your model…</span>
          </div>
        </div>
      )}
      <Canvas
        camera={{ position: [5, 5, 5], fov: 50 }}
        gl={{ antialias: true }}
        className="h-full w-full"
      >
        <color attach="background" args={[boothColor]} />
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
        {faceSelection && showGrid && <FaceGrid selection={faceSelection} />}
        <Suspense fallback={null}>
          <Scene glbUrl={glbUrl} onFaceClick={selectFace} />
        </Suspense>
      </Canvas>
    </div>
  );
}

export function ViewportPane(props: ViewportPaneProps) {
  return <ViewportContent key={props.glbUrl ?? "empty"} {...props} />;
}
