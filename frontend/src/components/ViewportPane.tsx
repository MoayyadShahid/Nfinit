"use client";

import { Center, GizmoHelper, GizmoViewcube, OrbitControls, useGLTF } from "@react-three/drei";
import { Layers } from "lucide-react";
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
  /** B-rep identity, read from the face's node in the GLB. */
  faceId?: string;
  surfaceType?: string;
  featureId?: string | null;
}

/** A feature as the GLB's scene extras describe it. */
export type ModelFeature = {
  id: string;
  name: string;
  operation: string;
  parentId: string | null;
  ownedFaceIds: string[];
};

type ModelInfo = { topologyVersion?: string; features: ModelFeature[] };

const FACE_COLOR = new THREE.Color(0x8a93a3);
const EDGE_COLOR = new THREE.Color(0x1b1e24);
const HOVER_GLOW = new THREE.Color(0x4f8ff7);
const FEATURE_GLOW = new THREE.Color(0x3b82f6);
const SELECTED_GLOW = new THREE.Color(0xf26b3a);
const WARNING_GLOW = new THREE.Color(0xf59e0b);

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
  onInfo,
  selectedFaceId,
  featureFaceIds,
  warningFaceIds,
  interactive = true,
  fitRequest = 0,
}: {
  url: string;
  interactive?: boolean;
  fitRequest?: number;
  onFaceClick: (sel: ThreeFaceSelection) => void;
  onThumbnail?: (image: Blob) => void;
  onLoaded?: (url: string) => void;
  onInfo?: (info: ModelInfo) => void;
  selectedFaceId?: string | null;
  featureFaceIds?: ReadonlySet<string>;
  warningFaceIds?: ReadonlySet<string>;
}) {
  const { scene } = useGLTF(url);
  const [hoveredFaceId, setHoveredFaceId] = useState<string | null>(null);
  // Faces a build preview marks as new glow for a moment when it appears.
  const [glowNew, setGlowNew] = useState(true);
  useEffect(() => {
    const timer = window.setTimeout(() => setGlowNew(false), 1_000);
    return () => window.clearTimeout(timer);
  }, [scene]);

  useEffect(() => {
    scene.traverse((child) => {
      if (child instanceof THREE.LineSegments) {
        // B-rep edges: drawn on top of the faces, never picked.
        child.material = new THREE.LineBasicMaterial({ color: EDGE_COLOR });
        child.raycast = () => {};
      } else if (child instanceof THREE.Mesh) {
        // Each face gets its own material, so it can be highlighted alone.
        child.material = child.material.clone();
        if (child.material instanceof THREE.MeshStandardMaterial) {
          child.material.color = FACE_COLOR.clone();
          child.material.metalness = 0.18;
          child.material.roughness = 0.48;
          // Push faces back slightly so the edge lines do not flicker.
          child.material.polygonOffset = true;
          child.material.polygonOffsetFactor = 1;
          child.material.polygonOffsetUnits = 1;
        }
      }
    });
    onInfo?.({
      topologyVersion: scene.userData.topologyVersion,
      features: Array.isArray(scene.userData.features) ? scene.userData.features : [],
    });
    onLoaded?.(url);
  }, [scene, url, onLoaded, onInfo]);

  useEffect(() => {
    scene.traverse((child) => {
      if (!(child instanceof THREE.Mesh)) return;
      const material = child.material;
      if (!(material instanceof THREE.MeshStandardMaterial)) return;
      const faceId = child.userData.faceId as string | undefined;
      if (faceId && faceId === selectedFaceId) {
        material.emissive.copy(SELECTED_GLOW);
        material.emissiveIntensity = 0.45;
      } else if (faceId && faceId === hoveredFaceId) {
        material.emissive.copy(HOVER_GLOW);
        material.emissiveIntensity = 0.28;
      } else if (faceId && warningFaceIds?.has(faceId)) {
        material.emissive.copy(WARNING_GLOW);
        material.emissiveIntensity = 0.5;
      } else if (
        (faceId && featureFaceIds?.has(faceId)) ||
        (glowNew && child.userData.isNew)
      ) {
        material.emissive.copy(FEATURE_GLOW);
        material.emissiveIntensity = 0.35;
      } else {
        material.emissive.setRGB(0, 0, 0);
        material.emissiveIntensity = 1;
      }
    });
  }, [scene, selectedFaceId, hoveredFaceId, featureFaceIds, warningFaceIds, glowNew]);

  // The pointer cursor is set while a face is hovered; reset it on unmount.
  useEffect(() => () => void (document.body.style.cursor = ""), []);

  const handlePointerMove = useCallback((e: ThreeEvent<PointerEvent>) => {
    e.stopPropagation();
    const faceId = (e.object.userData.faceId as string | undefined) ?? null;
    setHoveredFaceId(faceId);
    document.body.style.cursor = faceId ? "pointer" : "";
  }, []);

  const handlePointerOut = useCallback(() => {
    setHoveredFaceId(null);
    document.body.style.cursor = "";
  }, []);

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

      // The GLB stores CAD coordinates in meters under one Y-up rotation;
      // convert mesh-local coordinates back to the millimeters of the code.
      const cadPoint = e.object
        .worldToLocal(e.point.clone())
        .multiplyScalar(1000);
      const cadNormal = e.face.normal.clone().normalize();

      onFaceClick({
        point: e.point.clone(),
        normal: snapped,
        cadPoint,
        cadNormal,
        faceId: e.object.userData.faceId,
        surfaceType: e.object.userData.surfaceType,
        featureId: e.object.userData.featureId ?? null,
      });
    },
    [onFaceClick]
  );

  return (
    <>
      <Center>
        <primitive
          object={scene}
          scale={100}
          onClick={interactive ? handleClick : undefined}
          onPointerMove={interactive ? handlePointerMove : undefined}
          onPointerOut={interactive ? handlePointerOut : undefined}
        />
      </Center>
      <FitCamera model={scene} fitRequest={fitRequest} />
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
  onInfo,
  selectedFaceId,
  featureFaceIds,
  warningFaceIds,
  interactive = true,
  fitRequest = 0,
}: {
  glbUrl: string | null;
  interactive?: boolean;
  fitRequest?: number;
  onFaceClick: (sel: ThreeFaceSelection) => void;
  onThumbnail?: (image: Blob) => void;
  onModelShown?: (url: string) => void;
  onInfo?: (info: ModelInfo) => void;
  selectedFaceId?: string | null;
  featureFaceIds?: ReadonlySet<string>;
  warningFaceIds?: ReadonlySet<string>;
}) {
  // The last model that finished loading. It stays on screen (it is already
  // in useGLTF's cache) while the next one downloads.
  const [shownUrl, setShownUrl] = useState<string | null>(null);
  const handleLoaded = useCallback(
    (url: string) => {
      setShownUrl(url);
      onModelShown?.(url);
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
        onInfo={onInfo}
        selectedFaceId={selectedFaceId}
        featureFaceIds={featureFaceIds}
        warningFaceIds={warningFaceIds}
        interactive={interactive}
        fitRequest={fitRequest}
      />
    </Suspense>
  );
}

/**
 * Frames the part in view when it first appears, and again when its size
 * changes noticeably, keeping the direction the user is looking from. Small
 * changes (a hole, a fillet, the next build preview) leave the camera alone.
 */
function FitCamera({ model, fitRequest }: { model: THREE.Object3D; fitRequest: number }) {
  const lastFitRequest = useRef(fitRequest);
  const { camera, controls } = useThree();

  useEffect(() => {
    let frame = requestAnimationFrame(() => {
      // Second frame: <Center> has positioned the model by now.
      frame = requestAnimationFrame(() => {
        if (!(camera instanceof THREE.PerspectiveCamera)) return;
        const box = new THREE.Box3().setFromObject(model);
        if (box.isEmpty()) return;
        const sphere = box.getBoundingSphere(new THREE.Sphere());
        const fitted = camera.userData.fitRadius as number | undefined;
        const requested = fitRequest !== lastFitRequest.current;
        lastFitRequest.current = fitRequest;
        if (!requested && fitted && sphere.radius / fitted > 0.8 && sphere.radius / fitted < 1.25) {
          return;
        }
        camera.userData.fitRadius = sphere.radius;
        const orbit = controls as unknown as {
          target: THREE.Vector3;
          update: () => void;
        } | null;
        const target = orbit?.target ?? new THREE.Vector3();
        const direction = camera.position.clone().sub(target).normalize();
        if (direction.lengthSq() === 0) direction.set(1, 1, 1).normalize();
        const halfFov = THREE.MathUtils.degToRad(camera.fov / 2);
        const halfWidth = Math.atan(Math.tan(halfFov) * camera.aspect);
        const distance = (sphere.radius * 1.2) / Math.sin(Math.min(halfFov, halfWidth));
        camera.position.copy(sphere.center).add(direction.multiplyScalar(distance));
        camera.near = Math.max(0.01, distance / 100);
        camera.far = distance * 100;
        camera.updateProjectionMatrix();
        if (orbit) {
          orbit.target.copy(sphere.center);
          orbit.update();
        } else {
          camera.lookAt(sphere.center);
        }
      });
    });
    return () => cancelAnimationFrame(frame);
  }, [camera, controls, model, fitRequest]);

  return null;
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

const OPERATION_LABELS: Record<string, string> = {
  additive: "Add",
  subtractive: "Cut",
  pattern: "Pattern",
  fillet: "Fillet",
  chamfer: "Chamfer",
  transform: "Move",
  reference: "Reference",
};

/** The part's authored feature history; a click highlights its faces. */
function FeatureList({
  features,
  activeFeatureId,
  selectedFeatureId,
  onToggle,
}: {
  features: ModelFeature[];
  activeFeatureId: string | null;
  selectedFeatureId: string | null;
  onToggle: (featureId: string) => void;
}) {
  return (
    <div className="absolute right-3 top-[118px] z-20 hidden w-[230px] sm:block">
      <div className="theme-floating rounded-2xl border p-2 shadow-xl shadow-black/10 backdrop-blur-xl">
        <p className="flex items-center gap-1.5 px-1.5 pb-1.5 pt-0.5 text-[10px] uppercase tracking-[0.14em] text-zinc-600">
          <Layers className="size-3" />
          Features
        </p>
        <ol className="max-h-[38dvh] space-y-0.5 overflow-y-auto">
          {features.map((feature) => {
            const active = feature.id === activeFeatureId;
            const holdsSelection = feature.id === selectedFeatureId;
            return (
              <li key={feature.id}>
                <button
                  type="button"
                  onClick={() => onToggle(feature.id)}
                  aria-pressed={active}
                  title={`${feature.ownedFaceIds.length} face(s) · ${feature.id}`}
                  className={`flex w-full items-center gap-2 rounded-lg px-1.5 py-1 text-left text-[11px] transition-colors ${
                    active
                      ? "bg-[var(--control-hover)] text-[var(--ink)]"
                      : "text-[var(--ink-2)] hover:bg-[var(--control-hover)]"
                  }`}
                  style={{ paddingLeft: feature.parentId ? 18 : 6 }}
                >
                  <span
                    className={`size-1.5 shrink-0 rounded-full ${
                      holdsSelection
                        ? "bg-[#f26b3a]"
                        : active
                          ? "bg-[#3b82f6]"
                          : "bg-zinc-400/60"
                    }`}
                  />
                  <span className="min-w-0 flex-1 truncate">{feature.name}</span>
                  <span className="shrink-0 text-[9px] text-zinc-500">
                    {OPERATION_LABELS[feature.operation] ?? ""}
                  </span>
                </button>
              </li>
            );
          })}
        </ol>
      </div>
    </div>
  );
}

interface ViewportPaneProps {
  /** Increment to frame the model without reloading it. */
  fitRequest?: number;
  glbUrl: string | null;
  code: string;
  isLoading: boolean;
  /** What the agent is doing now; shown in the progress strip. */
  progressMessage?: string;
  /** A build preview shown in place of the model while a run builds it. */
  previewUrl?: string;
  /** What the preview shows, e.g. "Built: Mounting holes". */
  previewLabel?: string;
  showSelectionCard?: boolean;
  onSelectionChange?: (selection: FaceSelection | null) => void;
  /** Called once per loaded model with a 480×360 preview image. */
  onThumbnail?: (image: Blob) => void;
  /** Faces a check points at, drawn in a warning colour. */
  warningFaceIds?: readonly string[];
}

function ViewportContent({
  fitRequest = 0,
  glbUrl,
  code,
  isLoading,
  progressMessage,
  previewUrl,
  previewLabel,
  showSelectionCard = true,
  onSelectionChange,
  onThumbnail,
  warningFaceIds,
}: ViewportPaneProps) {
  const warningFaces = useMemo(() => new Set(warningFaceIds ?? []), [warningFaceIds]);
  const [faceSelection, setFaceSelection] = useState<ThreeFaceSelection | null>(null);
  const [resolvedFace, setResolvedFace] = useState<FaceSelection | null>(null);
  const [modelInfo, setModelInfo] = useState<ModelInfo>({ features: [] });
  const [activeFeatureId, setActiveFeatureId] = useState<string | null>(null);
  const handleModelInfo = useCallback((info: ModelInfo) => {
    setModelInfo(info);
    setActiveFeatureId(null);
  }, []);
  const featureFaceIds = useMemo(
    () =>
      new Set(
        modelInfo.features.find((feature) => feature.id === activeFeatureId)
          ?.ownedFaceIds ?? []
      ),
    [modelInfo, activeFeatureId]
  );
  const [boothColor, setBoothColor] = useState("#ddd3c2");
  const resolutionRequest = useRef(0);
  // Bumped when a new model appears; restarts the reveal fade.
  const [reveal, setReveal] = useState(0);
  const [shownModelUrl, setShownModelUrl] = useState<string | null>(null);
  const handleModelShown = useCallback((url: string) => {
    setShownModelUrl(url);
    setReveal((count) => count + 1);
  }, []);
  const displayedUrl = previewUrl ?? glbUrl;
  const statusMessage =
    previewUrl && shownModelUrl === previewUrl ? previewLabel : progressMessage;

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
      if (selection.faceId) {
        const semanticSelection: FaceSelection = {
          ...geometricSelection,
          entityId: selection.faceId,
          topologyVersion: modelInfo.topologyVersion,
          surfaceType: selection.surfaceType,
          confidence: 1,
        };
        resolutionRequest.current += 1;
        setResolvedFace(semanticSelection);
        onSelectionChange?.(semanticSelection);
        return;
      }
      onSelectionChange?.(geometricSelection);
      // A mesh without face IDs (an older format): resolve on the backend.
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
    [code, glbUrl, modelInfo.topologyVersion, onSelectionChange]
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
      {glbUrl && !previewUrl && modelInfo.features.length > 0 && (
        <FeatureList
          features={modelInfo.features}
          activeFeatureId={activeFeatureId}
          selectedFeatureId={faceSelection?.featureId ?? null}
          onToggle={(featureId) =>
            setActiveFeatureId((current) => (current === featureId ? null : featureId))
          }
        />
      )}
      {faceSelection && showSelectionCard && (
        <div className="absolute bottom-3 left-3 z-20 rounded-xl border border-[var(--hairline-strong)] bg-[var(--sheet)] px-3.5 py-2.5 text-xs text-[var(--ink)] shadow-xl">
          <div className="font-medium">Face selected</div>
          <div className="mt-0.5 text-[10px] text-[var(--muted)]">
            {resolvedFace?.entityId
              ? `${resolvedFace.surfaceType ?? "surface"} · ${resolvedFace.entityId.slice(0, 13)}`
              : glbUrl
                ? "Identifying the B-rep face…"
                : "Positional selection"}
          </div>
        </div>
      )}
      {isLoading && displayedUrl && (
        // The current model stays visible and usable while the next one builds.
        <div className="pointer-events-none absolute inset-x-0 top-0 z-10 flex flex-col items-center">
          <div className="viewport-progress-bar h-0.5 w-full" />
          <div className="theme-floating mt-3 max-w-[80%] truncate rounded-full border px-3 py-1 text-[11px] text-[var(--ink-2)] shadow-sm">
            {statusMessage || "Building your model…"}
          </div>
        </div>
      )}
      {isLoading && !displayedUrl && (
        <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center">
          <div className="flex max-w-[70%] flex-col items-center gap-3 text-center">
            <div className="h-10 w-10 animate-spin rounded-full border-2 border-[var(--hairline-strong)] border-t-[var(--accent)]" />
            <span className="theme-floating rounded-full border px-3.5 py-1.5 text-sm text-[var(--ink-2)] shadow-sm">
              {statusMessage || "Building your model…"}
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
        <Suspense fallback={null}>
          <Scene
            glbUrl={displayedUrl}
            fitRequest={fitRequest}
            interactive={!previewUrl}
            onFaceClick={selectFace}
            // A preview is never the part's thumbnail.
            onThumbnail={previewUrl ? undefined : onThumbnail}
            onModelShown={handleModelShown}
            onInfo={handleModelInfo}
            selectedFaceId={faceSelection?.faceId ?? null}
            featureFaceIds={featureFaceIds}
            warningFaceIds={warningFaces}
          />
        </Suspense>
      </Canvas>
    </div>
  );
}

export function ViewportPane(props: ViewportPaneProps) {
  return <ViewportContent key={props.glbUrl ?? "empty"} {...props} />;
}
