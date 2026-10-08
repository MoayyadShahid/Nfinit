"use client";

import { Center, GizmoHelper, GizmoViewcube, Grid, OrbitControls, useGLTF } from "@react-three/drei";
import { LayoutGrid } from "lucide-react";
import { sandboxRequest } from "@/lib/sandbox";
import type { FaceSelection } from "@/lib/types";
import { Canvas, ThreeEvent, useThree } from "@react-three/fiber";
import { Suspense, useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";

const NORMAL_TOLERANCE = 0.01;

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

const THUMBNAIL_WIDTH = 480;
const THUMBNAIL_HEIGHT = 360;

/**
 * Captures the part from a fixed three-quarter view once it has loaded, so
 * the parts dashboard thumbnail does not depend on where the user orbited.
 * The frame is drawn and copied within one callback, then the user's view is
 * redrawn, so nothing flashes on screen.
 */
function ThumbnailCapture({
  model,
  onCapture,
}: {
  model: THREE.Object3D;
  onCapture: (image: Blob) => void;
}) {
  const { gl, scene, camera } = useThree();

  useEffect(() => {
    let frame = requestAnimationFrame(() => {
      // Second frame: <Center> has positioned the model by now.
      frame = requestAnimationFrame(() => {
        const box = new THREE.Box3().setFromObject(model);
        if (box.isEmpty()) return;
        const sphere = box.getBoundingSphere(new THREE.Sphere());
        const canvas = gl.domElement;
        const shot = new THREE.PerspectiveCamera(
          35,
          canvas.width / canvas.height,
          sphere.radius / 100,
          sphere.radius * 100
        );
        const verticalHalf = THREE.MathUtils.degToRad(shot.fov / 2);
        const horizontalHalf = Math.atan(Math.tan(verticalHalf) * shot.aspect);
        const distance =
          (sphere.radius * 1.15) / Math.sin(Math.min(verticalHalf, horizontalHalf));
        shot.position
          .copy(sphere.center)
          .add(new THREE.Vector3(1, 0.85, 1).normalize().multiplyScalar(distance));
        shot.lookAt(sphere.center);

        gl.render(scene, shot);
        const output = document.createElement("canvas");
        output.width = THUMBNAIL_WIDTH;
        output.height = THUMBNAIL_HEIGHT;
        const context = output.getContext("2d");
        if (context) {
          // Centre-crop the canvas to the thumbnail's 4:3 frame.
          const scale = Math.min(
            canvas.width / THUMBNAIL_WIDTH,
            canvas.height / THUMBNAIL_HEIGHT
          );
          const cropWidth = THUMBNAIL_WIDTH * scale;
          const cropHeight = THUMBNAIL_HEIGHT * scale;
          context.drawImage(
            canvas,
            (canvas.width - cropWidth) / 2,
            (canvas.height - cropHeight) / 2,
            cropWidth,
            cropHeight,
            0,
            0,
            THUMBNAIL_WIDTH,
            THUMBNAIL_HEIGHT
          );
        }
        gl.render(scene, camera);
        if (!context) return;
        // Safari cannot encode WebP and falls back to PNG; both are accepted.
        output.toBlob(
          (image) => {
            if (image) onCapture(image);
          },
          "image/webp",
          0.82
        );
      });
    });
    return () => cancelAnimationFrame(frame);
  }, [gl, scene, camera, model, onCapture]);

  return null;
}

function ClickableModel({
  url,
  onFaceClick,
  onThumbnail,
  onLoaded,
}: {
  url: string;
  onFaceClick: (sel: ThreeFaceSelection) => void;
  onThumbnail?: (image: Blob) => void;
  onLoaded?: (url: string) => void;
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
    onLoaded?.(url);
  }, [scene, url, onLoaded]);

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
    <>
      <Center>
        <primitive object={scene} scale={100} onClick={handleClick} />
      </Center>
      {onThumbnail && <ThumbnailCapture model={scene} onCapture={onThumbnail} />}
    </>
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
  onThumbnail,
  onModelShown,
}: {
  glbUrl: string | null;
  onFaceClick: (sel: ThreeFaceSelection) => void;
  onThumbnail?: (image: Blob) => void;
  onModelShown?: () => void;
}) {
  // The last model that finished loading. It stays on screen (it is already
  // in useGLTF's cache) while the next one downloads.
  const [shownUrl, setShownUrl] = useState<string | null>(null);
  const handleLoaded = useCallback(
    (url: string) => {
      setShownUrl(url);
      onModelShown?.();
    },
    [onModelShown]
  );

  if (!glbUrl) {
    return <ClickablePlaceholder onFaceClick={onFaceClick} />;
  }

  const previous =
    shownUrl && shownUrl !== glbUrl ? (
      <ClickableModel key={shownUrl} url={shownUrl} onFaceClick={onFaceClick} />
    ) : null;

  return (
    <Suspense fallback={previous}>
      <ClickableModel
        key={glbUrl}
        url={glbUrl}
        onFaceClick={onFaceClick}
        onThumbnail={onThumbnail}
        onLoaded={handleLoaded}
      />
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
  /** What the agent is doing now; shown in the progress strip. */
  progressMessage?: string;
  showSelectionCard?: boolean;
  onSelectionChange?: (selection: FaceSelection | null) => void;
  /** Called once per loaded model with a 480×360 preview image. */
  onThumbnail?: (image: Blob) => void;
  /** When set, clicking a face calls this instead of selecting it. */
  onSelectBlocked?: () => void;
}

function ViewportContent({
  glbUrl,
  code,
  isLoading,
  progressMessage,
  showSelectionCard = true,
  onSelectionChange,
  onThumbnail,
  onSelectBlocked,
}: ViewportPaneProps) {
  const [faceSelection, setFaceSelection] = useState<ThreeFaceSelection | null>(null);
  const [resolvedFace, setResolvedFace] = useState<FaceSelection | null>(null);
  const [showGrid, setShowGrid] = useState(true);
  const [boothColor, setBoothColor] = useState("#ddd3c2");
  const resolutionRequest = useRef(0);
  // Bumped when a new model appears; restarts the reveal fade.
  const [reveal, setReveal] = useState(0);
  const handleModelShown = useCallback(() => setReveal((count) => count + 1), []);

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
      if (onSelectBlocked) {
        onSelectBlocked();
        return;
      }
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
        const response = await sandboxRequest(
          "analyze-model",
          { code, selection: geometricSelection },
          { signal: AbortSignal.timeout(30_000) }
        );
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
    [code, glbUrl, onSelectionChange, onSelectBlocked]
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
      {isLoading && glbUrl && (
        // The current model stays visible and usable while the next one builds.
        <div className="pointer-events-none absolute inset-x-0 top-0 z-10 flex flex-col items-center">
          <div className="viewport-progress-bar h-0.5 w-full" />
          <div className="theme-floating mt-3 max-w-[80%] truncate rounded-full border px-3 py-1 text-[11px] text-[var(--ink-2)] shadow-sm">
            {progressMessage || "Building your model…"}
          </div>
        </div>
      )}
      {isLoading && !glbUrl && (
        <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center">
          <div className="flex max-w-[70%] flex-col items-center gap-3 text-center">
            <div className="h-10 w-10 animate-spin rounded-full border-2 border-[var(--hairline-strong)] border-t-[var(--accent)]" />
            <span className="theme-floating rounded-full border px-3.5 py-1.5 text-sm text-[var(--ink-2)] shadow-sm">
              {progressMessage || "Building your model…"}
            </span>
          </div>
        </div>
      )}
      {reveal > 0 && (
        <div
          key={reveal}
          className="viewport-reveal pointer-events-none absolute inset-0 z-[5] bg-[var(--clay)]"
        />
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
          <Scene
            glbUrl={glbUrl}
            onFaceClick={selectFace}
            onThumbnail={onThumbnail}
            onModelShown={handleModelShown}
          />
        </Suspense>
      </Canvas>
    </div>
  );
}

export function ViewportPane(props: ViewportPaneProps) {
  return <ViewportContent key={props.glbUrl ?? "empty"} {...props} />;
}
