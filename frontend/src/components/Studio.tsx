"use client";

import { ChatPane } from "@/components/ChatPane";
import { ReferenceImport, type ImportedReference } from "@/components/ReferenceImport";
import { Button } from "@/components/ui/button";
import {
  CommandBar,
  type ExportFormat,
} from "@/components/CommandBar";
import { DemoControls } from "@/components/DemoReplay";
import { EditorPane } from "@/components/EditorPane";
import { VersionRail, type RailVersion } from "@/components/VersionRail";
import { VerificationPanel } from "@/components/VerificationPanel";
import { ViewportPane } from "@/components/ViewportPane";
import AIModelSelector, { type ModelOption } from "@/components/kokonutui/ai-model-selector";
import ActionSearchBar, { type StudioCommand } from "@/components/kokonutui/action-search-bar";
import { EXPORT_FORMATS, exportFileName } from "@/lib/exports";
import { PRINTER_KEY, PRINTERS, readPrinter, type PrinterId } from "@/lib/printers";
import { DEFAULT_MODEL, getModelConfig, MODEL_CONFIGS, LOCAL_MODEL_CONFIGS } from "@/lib/constants";
import {
  addRevision,
  createProject,
  getProject,
  getRevisionMesh,
  listProjects,
  listRevisions,
  uploadThumbnail,
  requestJson,
  type ProjectRevision,
  type RevisionSummary,
  getRevision,
  toRevisionSummary,
  type ProjectState,
  type ProjectSummary,
} from "@/lib/projects";
import {
  RunStillWorkingError,
  startRun,
  waitForRun,
  type CadRun,
} from "@/lib/runs";
import {
  demoFile,
  getDemo,
  listDemos,
  stepTitle,
  toRunEvent,
  type Demo,
  type DemoSummary,
} from "@/lib/demos";
import { sandboxRequest } from "@/lib/sandbox";
import { DEMO_ONLY, RUN_LOCALLY_URL } from "@/lib/site";
import { useBuildPreview } from "@/lib/useBuildPreview";
import {
  getTextContent,
  type ChatMessage,
  type ContentPart,
  type FaceSelection,
  type ModelInspection,
  type RunEvent,
  type MeshReference,
} from "@/lib/types";
import {
  ArrowRight,
  Box,
  Code2,
  Download,
  FilePlus2,
  FolderOpen,
  History,
  Maximize,
  Save,
  RotateCcw,
  Ruler,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

const LAST_PROJECT_KEY = "nfinit:last-project-id";
const EMPTY_FACE_IDS: string[] = [];
const RAIL_OPEN_KEY = "nfinit:version-rail-open";

const VERSION_TIME = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
});
// A run in flight survives a reload: the studio resumes polling it.
const PENDING_RUN_KEY = "nfinit:pending-run";

type PendingRun = { runId: string; projectId: string | null; prompt: string };

function readPendingRun(): PendingRun | null {
  try {
    const raw = window.localStorage.getItem(PENDING_RUN_KEY);
    return raw ? (JSON.parse(raw) as PendingRun) : null;
  } catch {
    return null;
  }
}

function writePendingRun(pending: PendingRun | null) {
  try {
    if (pending) {
      window.localStorage.setItem(PENDING_RUN_KEY, JSON.stringify(pending));
    } else {
      window.localStorage.removeItem(PENDING_RUN_KEY);
    }
  } catch {
    // Storage can be unavailable (private mode); resuming is a convenience.
  }
}

const DEFAULT_CODE = [
  "width, depth, height = 10.0, 10.0, 10.0",
  "",
  "with BuildPart() as part:",
  "    Box(width, depth, height)",
  "",
  "result = part.part",
].join("\n");

// A replayed demo step lasts at most this long before its previews play.
const DEMO_REPLAY_MS = 7_000;

/** The chat of a demo's first `steps` versions: each request and its reply. */
function demoHistory(target: Demo, steps: number): ChatMessage[] {
  return target.steps.slice(0, steps).flatMap((recorded): ChatMessage[] => [
    { role: "user", content: recorded.prompt },
    { role: "assistant", content: recorded.code, agent: recorded.agent },
  ]);
}


/** Models kept in memory per studio session, as blob URLs. */
const MESH_CACHE_SIZE = 12;

function revisionKey(projectId: string, revisionNumber: number): string {
  return `${projectId}:${revisionNumber}`;
}

/** Free a model URL unless the version cache still holds it. */
function releaseGlbUrl(
  url: string | null,
  cache: Map<string, { url: string }>
): void {
  if (!url || !url.startsWith("blob:")) return;
  for (const entry of cache.values()) if (entry.url === url) return;
  URL.revokeObjectURL(url);
}

export default function Studio({
  initialPrompt,
  initialProjectId,
  initialDemo,
  startNew = false,
}: {
  initialPrompt?: string;
  initialProjectId?: string;
  /** Open this demo, e.g. from /studio?demo=fpv-drone. */
  initialDemo?: string;
  startNew?: boolean;
}) {
  const [code, setCode] = useState(DEFAULT_CODE);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [modelId, setModelId] = useState<string>(DEFAULT_MODEL);
  const [localAgents, setLocalAgents] = useState<{ id: string; label: string; installed: boolean }[] | null>(null);
  const [meshReference, setMeshReference] = useState<MeshReference | null>(null);
  const [glbUrl, setGlbUrl] = useState<string | null>(null);
  const glbUrlRef = useRef<string | null>(null);
  useEffect(() => {
    glbUrlRef.current = glbUrl;
  }, [glbUrl]);
  // Versions never change once saved, so what was fetched stays valid:
  // their states, and their models as blob URLs (newest last). Switching
  // back to a version is then instant, and the viewer's own cache, keyed by
  // URL, also hits.
  const revisionCacheRef = useRef(new Map<string, ProjectRevision>());
  const meshCacheRef = useRef(
    new Map<string, { url: string; inspection: ModelInspection | null }>()
  );
  const [selectedFace, setSelectedFace] = useState<FaceSelection | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  // Progress of the run in flight; cleared when it finishes.
  const [runEvents, setRunEvents] = useState<RunEvent[]>([]);
  const [runStartedAt, setRunStartedAt] = useState<number | null>(null);
  // The part after each feature, played back while the run builds it.
  const {
    preview: buildPreview,
    enqueue: enqueuePreview,
    enqueueFiles: enqueuePreviewFiles,
    settle: settlePreview,
    clear: clearPreview,
  } = useBuildPreview();
  const [isProjectLoading, setIsProjectLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [revisions, setRevisions] = useState<RevisionSummary[]>([]);
  const [currentRevision, setCurrentRevision] = useState<number | null>(null);
  const [lastRunId, setLastRunId] = useState<string | null>(null);
  const [isDirty, setIsDirty] = useState(true);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [commandsOpen, setCommandsOpen] = useState(false);
  // Like the rail, the printer menu is only drawn after the studio
  // initialises, so reading storage here cannot differ from the server's markup.
  const [printer, setPrinter] = useState<PrinterId>(() =>
    typeof window === "undefined" ? "generic" : readPrinter()
  );
  const choosePrinter = useCallback((id: PrinterId) => {
    setPrinter(id);
    try {
      window.localStorage.setItem(PRINTER_KEY, id);
    } catch {
      /* the choice still applies to this session */
    }
  }, []);
  const [fitRequest, setFitRequest] = useState(0);
  // The version rail starts collapsed on phones, where width is scarce. It is
  // only drawn after the studio initialises, so reading storage here cannot
  // differ from the server's markup.
  const [railOpen, setRailOpen] = useState(() => {
    if (typeof window === "undefined") return true;
    try {
      const saved = window.localStorage.getItem(RAIL_OPEN_KEY);
      if (saved !== null) return saved === "1";
    } catch {
      /* storage can be unavailable; fall back to the screen size */
    }
    return window.innerWidth >= 640;
  });
  // The public demo has no saved parts to load, so it is ready at once.
  const [hasInitialized, setHasInitialized] = useState(DEMO_ONLY);
  const [inspection, setInspection] = useState<ModelInspection | null>(null);
  // Faces a check's "Show on part" points at, on the part they were found on.
  const [warning, setWarning] = useState<{ url: string | null; faceIds: string[] }>({
    url: null,
    faceIds: [],
  });
  const warningFaceIds = warning.url === glbUrl ? warning.faceIds : EMPTY_FACE_IDS;
  // The evidence of the run that produced the code on screen, if any.
  const evidence = useMemo(() => {
    for (let index = messages.length - 1; index >= 0; index -= 1) {
      const message = messages[index];
      if (message.role === "assistant" && message.agent?.inspection && message.content === code) {
        return message.agent.inspection;
      }
    }
    return null;
  }, [messages, code]);
  const showFaces = useCallback((faceIds: string[]) => setWarning({ url: glbUrl, faceIds }), [glbUrl]);
  // A recorded demo being replayed (no project, no backend runs).
  const [demos, setDemos] = useState<DemoSummary[]>([]);
  const [demo, setDemo] = useState<Demo | null>(null);
  const [demoStep, setDemoStep] = useState(0);
  // The furthest version built in this replay; its chat stays visible when an
  // earlier version is shown, like a CAD timeline.
  const [demoReached, setDemoReached] = useState(0);
  const demoReachedRef = useRef(0);
  const [demoPlaying, setDemoPlaying] = useState(false);
  const demoTimers = useRef<number[]>([]);
  const demoGeneration = useRef(0);
  const demoOpened = useRef(false);
  // Code from a failed run, offered so the tokens spent on it are not lost.
  const [recoverableCode, setRecoverableCode] = useState<string | null>(null);
  const mountedRef = useRef(true);
  const lastThumbnailRef = useRef<Blob | null>(null);
  const thumbnailContextRef = useRef({
    projectId: null as string | null,
    isDirty: true,
    isLatestRevision: false,
    needsThumbnail: false,
  });

  const modelConfig = useMemo(() => getModelConfig(modelId), [modelId]);
  const modelOptions: ModelOption[] = localAgents === null ? MODEL_CONFIGS : [
    ...LOCAL_MODEL_CONFIGS.map((model) => ({
      ...model,
      disabled: !localAgents.some((agent) => agent.id === model.id && agent.installed),
    })),
    ...MODEL_CONFIGS,
  ];

  useEffect(() => {
    if (DEMO_ONLY) return;
    let active = true;
    requestJson<{ local: boolean; agents: { id: string; label: string; installed: boolean }[] }>("/cad/local-agents")
      .then((result) => {
        if (!active || !result.local) return;
        setLocalAgents(result.agents);
        setModelId((current) => current === DEFAULT_MODEL ? (result.agents.find((agent) => agent.installed)?.id ?? "local/claude") : current);
      }).catch(() => {});
    return () => { active = false; };
  }, []);

  const inspectModel = useCallback(async (codeToInspect: string) => {
    const response = await sandboxRequest("inspect-model", {
      code: codeToInspect,
    }).catch(() => null);
    if (!response) return null;
    const result = await response.json().catch(() => null);
    if (response.ok && result?.valid) {
      setInspection(result);
      return result as ModelInspection;
    }
    return null;
  }, []);

  const generateMesh = useCallback(async (
    codeToExecute: string,
    clearSelection = true
  ) => {
    setError(null);
    try {
      const res = await sandboxRequest("generate-mesh", { code: codeToExecute });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || "Failed to generate mesh");
      }

      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      if (clearSelection) setSelectedFace(null);
      setGlbUrl((prev) => {
        releaseGlbUrl(prev, meshCacheRef.current);
        return url;
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Mesh generation failed");
    }
  }, []);

  // A saved revision's mesh is stored on the backend: download it instead of
  // building it again, and take its geometry facts from the same answer.
  const loadRevisionMesh = useCallback(async (revision: RevisionSummary) => {
    setError(null);
    const key = revisionKey(revision.projectId, revision.revisionNumber);
    const show = (entry: { url: string; inspection: ModelInspection | null }) => {
      setInspection(entry.inspection);
      setGlbUrl((prev) => {
        if (prev !== entry.url) releaseGlbUrl(prev, meshCacheRef.current);
        return entry.url;
      });
    };
    const cached = meshCacheRef.current.get(key);
    if (cached) {
      meshCacheRef.current.delete(key); // most recently used goes last
      meshCacheRef.current.set(key, cached);
      show(cached);
      return;
    }
    try {
      const mesh = await getRevisionMesh(
        revision.projectId,
        revision.revisionNumber
      );
      const response = await fetch(mesh.url);
      if (!response.ok) throw new Error("Could not download the model.");
      const entry = {
        url: URL.createObjectURL(await response.blob()),
        inspection: mesh.inspection.valid ? mesh.inspection : null,
      };
      const cache = meshCacheRef.current;
      cache.set(key, entry);
      while (cache.size > MESH_CACHE_SIZE) {
        const [oldestKey, oldest] = cache.entries().next().value!;
        cache.delete(oldestKey);
        // The shown model is released when it is replaced.
        if (oldest.url !== glbUrlRef.current) URL.revokeObjectURL(oldest.url);
      }
      show(entry);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Mesh generation failed");
    }
  }, []);

  const projectNameFromMessages = useCallback(
    (items: ChatMessage[]) => {
      const firstRequest = items.find((message) => message.role === "user");
      const text = firstRequest ? getTextContent(firstRequest.content).trim() : "";
      return text ? text.slice(0, 60) : "Untitled part";
    },
    []
  );

  const applyRevision = useCallback(
    async (revision: ProjectRevision) => {
      revisionCacheRef.current.set(
        revisionKey(revision.projectId, revision.revisionNumber),
        revision
      );
      const state = revision.state;
      setCode(state.code);
      setMessages(state.messages);
      setMeshReference(state.meshReference ?? null);
      // A model no longer offered (e.g. GPT-5.6 Sol) falls back to the default.
      setModelId(getModelConfig(state.modelId) ? state.modelId : DEFAULT_MODEL);
      setSelectedFace(state.selection);
      setLastRunId(state.lastRunId);
      setCurrentRevision(revision.revisionNumber);
      setIsDirty(false);
      if (state.code.trim()) await loadRevisionMesh(revision);
      else { setGlbUrl(null); setInspection(null); }
      setSelectedFace(state.selection);
    },
    [loadRevisionMesh]
  );

  const loadProject = useCallback(
    async (nextProjectId: string) => {
      if (
        isDirty &&
        !window.confirm("Discard unsaved changes and load another part?")
      ) {
        return false;
      }
      setIsProjectLoading(true);
      setError(null);
      try {
        const [project, history] = await Promise.all([
          getProject(nextProjectId),
          listRevisions(nextProjectId),
        ]);
        setProjectId(project.id);
        window.localStorage.setItem(LAST_PROJECT_KEY, project.id);
        setRevisions(history);
        if (project.latestRevision) {
          await applyRevision(project.latestRevision);
        }
        return true;
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load project");
        return false;
      } finally {
        setIsProjectLoading(false);
      }
    },
    [applyRevision, isDirty]
  );

  const sendThumbnail = useCallback(
    async (targetProjectId: string, image: Blob) => {
      try {
        await uploadThumbnail(targetProjectId, image);
        const now = new Date().toISOString();
        setProjects((previous) =>
          previous.map((project) =>
            project.id === targetProjectId
              ? { ...project, thumbnailUpdatedAt: now }
              : project
          )
        );
      } catch (thumbnailError) {
        // A missing preview is cosmetic; never interrupt the user for it.
        console.warn("Thumbnail upload failed", thumbnailError);
      }
    },
    []
  );

  // Stable for the viewport (a changing callback would re-capture); reads the
  // latest studio state through a ref instead.
  const handleThumbnail = useCallback(
    (image: Blob) => {
      lastThumbnailRef.current = image;
      const context = thumbnailContextRef.current;
      if (
        context.projectId &&
        !context.isDirty &&
        context.isLatestRevision &&
        context.needsThumbnail
      ) {
        context.needsThumbnail = false;
        void sendThumbnail(context.projectId, image);
      }
    },
    [sendThumbnail]
  );

  const persistSnapshot = useCallback(
    async (state: ProjectState, suggestedName?: string) => {
      setIsSaving(true);
      try {
        let savedProjectId: string;
        if (projectId) {
          savedProjectId = projectId;
          const revision = await addRevision(projectId, state);
          revisionCacheRef.current.set(
            revisionKey(revision.projectId, revision.revisionNumber),
            revision
          );
          setRevisions((previous) => [
            toRevisionSummary(revision),
            ...previous.filter((item) => item.id !== revision.id),
          ]);
          setCurrentRevision(revision.revisionNumber);
          setProjects((previous) =>
            previous.map((project) =>
              project.id === projectId
                ? {
                    ...project,
                    revisionCount: revision.revisionNumber,
                    updatedAt: revision.createdAt,
                  }
                : project
            )
          );
          window.localStorage.setItem(LAST_PROJECT_KEY, projectId);
        } else {
          const project = await createProject(
            suggestedName || projectNameFromMessages(state.messages),
            state
          );
          savedProjectId = project.id;
          setProjectId(project.id);
          window.localStorage.setItem(LAST_PROJECT_KEY, project.id);
          setProjects((previous) => [
            project,
            ...previous.filter((item) => item.id !== project.id),
          ]);
          setRevisions(
            project.latestRevision ? [toRevisionSummary(project.latestRevision)] : []
          );
          setCurrentRevision(
            project.latestRevision?.revisionNumber ?? null
          );
        }
        setIsDirty(false);
        if (lastThumbnailRef.current) {
          void sendThumbnail(savedProjectId, lastThumbnailRef.current);
        }
      } finally {
        setIsSaving(false);
      }
    },
    [projectId, projectNameFromMessages, sendThumbnail]
  );

  const saveCurrentRevision = useCallback(async () => {
    setError(null);
    setIsSaving(true);
    try {
      const validationResponse = await sandboxRequest("inspect-model", { code });
      const validation = await validationResponse.json().catch(() => null);
      if (!validationResponse.ok || !validation?.valid) {
        throw new Error(
          validation?.error ||
            validation?.detail ||
            "Fix the code error before saving this revision."
        );
      }
      setInspection(validation);
      await persistSnapshot({
        code,
        messages,
        modelId,
        selection: selectedFace,
        lastRunId,
        meshReference,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save revision");
    } finally {
      setIsSaving(false);
    }
  }, [
    code,
    lastRunId,
    messages,
    modelId,
    persistSnapshot,
    selectedFace,
    meshReference,
  ]);

  const startNewProject = useCallback(() => {
    if (isDirty && !window.confirm("Discard unsaved changes and start a new part?")) {
      return false;
    }
    setGlbUrl((previous) => {
      releaseGlbUrl(previous, meshCacheRef.current);
      return null;
    });
    setProjectId(null);
    window.localStorage.removeItem(LAST_PROJECT_KEY);
    setRevisions([]);
    setCurrentRevision(null);
    setCode(DEFAULT_CODE);
    setMessages([]);
    setMeshReference(null);
    setModelId(localAgents?.find((agent) => agent.installed)?.id ?? DEFAULT_MODEL);
    setSelectedFace(null);
    setInspection(null);
    setLastRunId(null);
    setIsDirty(true);
    setError(null);
    return true;
  }, [isDirty, localAgents]);

  const loadRevision = useCallback(
    async (revisionNumber: number) => {
      if (
        isDirty &&
        !window.confirm("Discard unsaved changes and load this revision?")
      ) {
        return;
      }
      if (!projectId) return;
      const key = revisionKey(projectId, revisionNumber);
      const cached = revisionCacheRef.current.get(key);
      // A version seen before switches at once, without the loading cover.
      const instant = Boolean(cached && meshCacheRef.current.has(key));
      if (!instant) setIsProjectLoading(true);
      setError(null);
      try {
        await applyRevision(cached ?? (await getRevision(projectId, revisionNumber)));
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not load this version.");
      } finally {
        if (!instant) setIsProjectLoading(false);
      }
    },
    [applyRevision, isDirty, projectId]
  );

  // Load what a finished run produced. The backend has already saved a
  // successful run into the project, so this only has to display it.
  const completeRun = useCallback(
    async (run: CadRun) => {
      writePendingRun(null);
      if (run.status === "succeeded" && run.projectId) {
        const [project, history, items] = await Promise.all([
          getProject(run.projectId),
          listRevisions(run.projectId),
          listProjects(),
        ]);
        if (!mountedRef.current) return;
        setProjects(items);
        setProjectId(project.id);
        window.localStorage.setItem(LAST_PROJECT_KEY, project.id);
        setRevisions(history);
        setLastRunId(run.runId);
        if (project.latestRevision) {
          await applyRevision(project.latestRevision);
        }
        return;
      }
      setMessages((previous) =>
        previous.length > 0 && previous[previous.length - 1].role === "user"
          ? previous.slice(0, -1)
          : previous
      );
      setRecoverableCode(run.result?.code || null);
      setError(run.error || "Generation failed");
    },
    [applyRevision]
  );

  const followRun = useCallback(
    async (runId: string) => {
      setIsLoading(true);
      setRunEvents([]);
      setRunStartedAt(Date.now());
      try {
        const run = await waitForRun(
          runId,
          () => !mountedRef.current,
          (events) => {
            if (!mountedRef.current) return;
            setRunEvents((previous) => [...previous, ...events]);
            enqueuePreview(runId, events);
            // A resumed run started before this page: time it from its first event.
            const first = Date.parse(events[0].createdAt);
            if (!Number.isNaN(first)) {
              setRunStartedAt((previous) =>
                previous === null ? first : Math.min(previous, first)
              );
            }
          }
        );
        // Let the last previews play before the finished part replaces them.
        await settlePreview(3_000);
        if (mountedRef.current) await completeRun(run);
      } catch (e) {
        if (!mountedRef.current) return;
        if (e instanceof RunStillWorkingError) {
          // Keep the pending marker: a reload will pick the run back up.
          setError(e.message);
        } else {
          setError(e instanceof Error ? e.message : "Lost track of the run");
        }
      } finally {
        if (mountedRef.current) {
          setIsLoading(false);
          setRunEvents([]);
          setRunStartedAt(null);
          clearPreview();
        }
      }
    },
    [clearPreview, completeRun, enqueuePreview, settlePreview]
  );

  const stopDemoPlayback = useCallback(() => {
    demoGeneration.current += 1;
    demoTimers.current.forEach((timer) => window.clearTimeout(timer));
    demoTimers.current = [];
    clearPreview();
    setDemoPlaying(false);
  }, [clearPreview]);

  /** Show one version of a demo, with the chat of every version built so far. */
  const showDemoStep = useCallback((target: Demo, step: number) => {
    const recorded = target.steps[step - 1];
    const reached = Math.max(demoReachedRef.current, step);
    demoReachedRef.current = reached;
    setDemoReached(reached);
    setMessages(demoHistory(target, reached));
    setCode(recorded.code);
    setInspection(recorded.agent.inspection.valid ? recorded.agent.inspection : null);
    setGlbUrl((previous) => {
      releaseGlbUrl(previous, meshCacheRef.current);
      return demoFile(target.slug, recorded.glb);
    });
    setDemoStep(step);
  }, []);

  /**
   * Replay one recorded step as the studio shows a live run: the request in
   * the chat, the agent's steps in the progress list, then the part growing
   * feature by feature. The recorded timing is compressed to a few seconds.
   */
  const playDemoStep = useCallback(
    (target: Demo, step: number) => {
      stopDemoPlayback();
      const generation = demoGeneration.current;
      const recorded = target.steps[step - 1];
      const startedAt = Date.now();
      setDemo(target);
      setDemoStep(step);
      setDemoPlaying(true);
      setMessages([
        ...demoHistory(target, step - 1),
        { role: "user", content: recorded.prompt },
      ]);
      setRunEvents([]);
      setRunStartedAt(startedAt);
      setIsLoading(true);

      const end = Math.max(1, ...recorded.events.map((event) => event.at_ms));
      const scale = Math.min(1, DEMO_REPLAY_MS / end);
      // Previews appear while the last (passing) check builds the part.
      const lastCheck = recorded.events
        .map((event) => event.stage === "inspect" && event.status === "started")
        .lastIndexOf(true);
      const schedule = (callback: () => void, delay: number) =>
        demoTimers.current.push(
          window.setTimeout(() => {
            if (generation === demoGeneration.current) callback();
          }, delay)
        );
      recorded.events.forEach((event, index) =>
        schedule(() => {
          setRunEvents((previous) => [
            ...previous,
            toRunEvent(event, index + 1, startedAt),
          ]);
          if (index === lastCheck) {
            // Each step rebuilds the whole part; play only what this step adds.
            const before = new Set(
              (target.steps[step - 2]?.previews ?? []).map((preview) => preview.name)
            );
            const added = recorded.previews.filter((preview) => !before.has(preview.name));
            enqueuePreviewFiles(
              (added.length > 0 ? added : recorded.previews.slice(-1)).map((preview) => ({
                url: demoFile(target.slug, preview.file),
                name: preview.name,
              }))
            );
          }
        }, event.at_ms * scale)
      );
      schedule(async () => {
        await settlePreview(4_000);
        if (generation !== demoGeneration.current) return;
        showDemoStep(target, step);
        setIsLoading(false);
        setRunEvents([]);
        setRunStartedAt(null);
        clearPreview();
        setDemoPlaying(false);
      }, end * scale + 400);
    },
    [clearPreview, enqueuePreviewFiles, settlePreview, showDemoStep, stopDemoPlayback]
  );

  /** Jump to a version without replaying it, e.g. from the timeline. */
  const selectDemoStep = useCallback(
    (target: Demo, step: number) => {
      stopDemoPlayback();
      setIsLoading(false);
      setRunEvents([]);
      setRunStartedAt(null);
      showDemoStep(target, step);
    },
    [showDemoStep, stopDemoPlayback]
  );

  const openDemo = useCallback(
    async (slug: string) => {
      try {
        const target = await getDemo(slug);
        if (!mountedRef.current) return;
        demoReachedRef.current = 0;
        setDemoReached(0);
        setProjectId(null);
        setMeshReference(null);
        setRevisions([]);
        setCurrentRevision(null);
        setLastRunId(null);
        setSelectedFace(null);
        setIsDirty(false);
        setError(null);
        playDemoStep(target, 1);
      } catch (e) {
        setError(e instanceof Error ? e.message : "This demo is not available.");
      }
    },
    [playDemoStep]
  );

  const exitDemo = useCallback(() => {
    stopDemoPlayback();
    setDemo(null);
    setMeshReference(null);
    demoReachedRef.current = 0;
    setDemoReached(0);
    setIsLoading(false);
    setRunEvents([]);
    setRunStartedAt(null);
    setGlbUrl(null);
    setCode(DEFAULT_CODE);
    setMessages([]);
    setInspection(null);
  }, [stopDemoPlayback]);

  useEffect(() => {
    listDemos()
      .then((items) => {
        if (mountedRef.current) setDemos(items);
      })
      .catch(() => {});
  }, []);

  useEffect(() => () => stopDemoPlayback(), [stopDemoPlayback]);

  const handleChatSend = useCallback(
    async (text: string, imageUrls?: string[]) => {
      if (!text.trim()) return;
      if (demo) {
        stopDemoPlayback();
        setDemo(null);
      }

      setIsLoading(true);
      setError(null);
      setRecoverableCode(null);

      let msgContent: string | ContentPart[];
      if (imageUrls && imageUrls.length > 0) {
        msgContent = [
          { type: "text" as const, text: text.trim() },
          ...imageUrls.map((url) => ({
            type: "image_url" as const,
            image_url: { url },
          })),
        ];
      } else {
        msgContent = text.trim();
      }

      const newMessages: ChatMessage[] = [
        ...messages,
        { role: "user", content: msgContent },
      ];
      setMessages(newMessages);

      let run: CadRun;
      try {
        run = await startRun({
          messages: newMessages,
          // A new part starts from nothing, not from the editor's starter box.
          code: messages.length === 0 && code === DEFAULT_CODE ? "" : code,
          modelId,
          selection: selectedFace,
          supportsStructuredOutputs:
            modelConfig?.supportsStructuredOutputs ?? false,
          projectId,
          meshReference,
          printProfile: { printer },
        });
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not start generation");
        setMessages((prev) => prev.slice(0, -1));
        setIsLoading(false);
        return;
      }
      writePendingRun({ runId: run.runId, projectId, prompt: text.trim() });
      await followRun(run.runId);
    },
    [
      messages,
      code,
      modelId,
      modelConfig,
      selectedFace,
      projectId,
      printer,
      followRun,
      demo,
      stopDemoPlayback,
      meshReference,
    ]
  );

  const sendChat = useCallback(
    (text: string, imageUrls?: string[]) => {
      void handleChatSend(text, imageUrls);
    },
    [handleChatSend]
  );

  const recoverLastAttempt = useCallback(() => {
    if (!recoverableCode) return;
    setCode(recoverableCode);
    setIsDirty(true);
    setAdvancedOpen(true);
    setRecoverableCode(null);
    setError(null);
  }, [recoverableCode]);

  const handleGenerate = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      await Promise.all([generateMesh(code), inspectModel(code)]);
    } finally {
      setIsLoading(false);
    }
  }, [code, generateMesh, inspectModel]);

  const handleExport = useCallback(
    async (id: ExportFormat) => {
      setError(null);
      const choice = EXPORT_FORMATS.find((item) => item.id === id)!;
      try {
        const res = await sandboxRequest("export-model", {
          code,
          format: choice.format,
          ...(choice.printReady ? { printReady: true } : {}),
        });

        if (!res.ok) {
          const err = await res
            .json()
            .catch(() => ({ detail: res.statusText }));
          throw new Error(err.detail || "Export failed");
        }

        const blob = await res.blob();
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = exportFileName(
          projects.find((project) => project.id === projectId)?.name ?? "part",
          id
        );
        a.click();
        URL.revokeObjectURL(url);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Export failed");
      }
    },
    [code, projects, projectId]
  );

  const handleSelectionChange = useCallback(
    (selection: FaceSelection | null) => {
      setSelectedFace(selection);
      setIsDirty(true);
    },
    []
  );

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
    if (DEMO_ONLY) return; // no backend: nothing saved to load or resume
    let active = true;
    let pending = readPendingRun();
    if (
      pending &&
      initialProjectId &&
      pending.projectId !== initialProjectId
    ) {
      // Opening a different part: the run still lands in its own project.
      writePendingRun(null);
      pending = null;
    }
    listProjects()
      .then(async (items) => {
        if (!active) return;
        setProjects(items);
        const storedProjectId = window.localStorage.getItem(LAST_PROJECT_KEY);
        const wantedProjectId = pending
          ? pending.projectId
          : initialProjectId ?? storedProjectId;
        const target = pending
          ? items.find((project) => project.id === pending.projectId)
          : startNew
            ? undefined
            : items.find((project) => project.id === wantedProjectId) ??
              (initialProjectId ? undefined : items[0]);
        if (initialProjectId && !pending && !target) {
          setError("That part could not be found.");
        }
        if (target) {
          setIsProjectLoading(true);
          const [project, history] = await Promise.all([
            getProject(target.id),
            listRevisions(target.id),
          ]);
          if (!active) return;
          setProjectId(project.id);
          window.localStorage.setItem(LAST_PROJECT_KEY, project.id);
          setRevisions(history);
          if (project.latestRevision) {
            await applyRevision(project.latestRevision);
          }
        }
        if (pending && active) {
          const resumed = pending;
          setMessages((previous) => [
            ...previous,
            { role: "user", content: resumed.prompt },
          ]);
          void followRun(resumed.runId);
        }
      })
      .catch((loadError) => {
        if (active) {
          setError(
            loadError instanceof Error
              ? loadError.message
              : "Failed to list saved projects"
          );
        }
      })
      .finally(() => {
        if (active) {
          setIsProjectLoading(false);
          setHasInitialized(true);
        }
      });
    return () => {
      active = false;
    };
  }, [applyRevision, followRun, initialProjectId, startNew]);

  useEffect(() => {
    const latestRevision = revisions[0] ?? null;
    const currentProject = projects.find((project) => project.id === projectId);
    thumbnailContextRef.current = {
      projectId,
      isDirty,
      isLatestRevision:
        latestRevision !== null &&
        currentRevision === latestRevision.revisionNumber,
      needsThumbnail:
        latestRevision !== null &&
        (!currentProject?.thumbnailUpdatedAt ||
          Date.parse(currentProject.thumbnailUpdatedAt) <
            Date.parse(latestRevision.createdAt)),
    };
  }, [projectId, isDirty, revisions, currentRevision, projects]);

  useEffect(() => {
    const warnBeforeUnload = (event: BeforeUnloadEvent) => {
      if (!isDirty) return;
      event.preventDefault();
    };
    window.addEventListener("beforeunload", warnBeforeUnload);
    return () => window.removeEventListener("beforeunload", warnBeforeUnload);
  }, [isDirty]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.altKey && e.key === "Enter" && !DEMO_ONLY) {
        e.preventDefault();
        handleGenerate();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [handleGenerate]);

  useEffect(() => {
    const cache = meshCacheRef.current; // the same Map for the studio's life
    return () => releaseGlbUrl(glbUrl, cache);
  }, [glbUrl]);

  useEffect(() => {
    const cache = meshCacheRef.current;
    return () => {
      for (const entry of cache.values()) URL.revokeObjectURL(entry.url);
      cache.clear();
    };
  }, []);

  const showWelcome =
    !DEMO_ONLY && hasInitialized && !projectId && messages.length === 0 && glbUrl === null;

  async function importReference(source: ImportedReference) {
    if (isDirty && !window.confirm("Import into a new project? Unsaved changes in this project will be left behind.")) return;
    const facts = source.reference.facts;
    const importedMessages: ChatMessage[] = [{ role: "user", content: [
      { type: "text", text: `STL reference: ${source.reference.name}. Source units: ${source.reference.units}; all measured values below are mm. ${JSON.stringify(facts)}. ${source.reference.mode === "preserve" ? "The original mesh is preserved as a faceted solid. Build changes on it." : "Reconstruct an approximate parametric version from these views and measured bounds. Original feature history is unavailable; identify assumptions and verify dimensions."}` },
      ...source.views.map((url): ContentPart => ({ type: "image_url", image_url: { url } })),
    ] }];
    const state: ProjectState = { code: source.code, messages: importedMessages, modelId,
      selection: null, lastRunId: null, meshReference: source.reference };
    const project = await createProject(`${source.reference.name.replace(/\.stl$/i, "")} — working copy`.slice(0, 120), state);
    stopDemoPlayback();
    setDemo(null);
    setProjectId(project.id);
    setProjects((previous) => [project, ...previous]);
    setRevisions(project.latestRevision ? [toRevisionSummary(project.latestRevision)] : []);
    if (project.latestRevision) revisionCacheRef.current.set(revisionKey(project.id, 1), project.latestRevision);
    setCurrentRevision(1);
    setCode(source.code);
    setMessages(importedMessages);
    setMeshReference(source.reference);
    setSelectedFace(null);
    setInspection(source.inspection);
    setLastRunId(null);
    setIsDirty(false);
    setGlbUrl((previous) => { releaseGlbUrl(previous, meshCacheRef.current); return null; });
    window.localStorage.setItem(LAST_PROJECT_KEY, project.id);
    if (source.code) await generateMesh(source.code);
  }

  async function saveCopy() {
    setIsSaving(true);
    try {
      const project = await createProject(`${projectNameFromMessages(messages)} — copy`.slice(0, 120), {
        code, messages, modelId, selection: selectedFace, lastRunId, meshReference,
      });
      setProjectId(project.id);
      setProjects((previous) => [project, ...previous]);
      setRevisions(project.latestRevision ? [toRevisionSummary(project.latestRevision)] : []);
      if (project.latestRevision) revisionCacheRef.current.set(revisionKey(project.id, 1), project.latestRevision);
      setCurrentRevision(1);
      setIsDirty(false);
      window.localStorage.setItem(LAST_PROJECT_KEY, project.id);
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not save a copy.");
    } finally { setIsSaving(false); }
  }

  const workspaceTools = (
    <div className="flex flex-col gap-2">
      {localAgents ? <p className="text-xs text-muted-foreground">{modelId.startsWith("local/") ? "Your agent account · local CAD" : "Hosted API"}</p> : null}
      {localAgents && !localAgents.some((agent) => agent.installed) ? <p className="text-xs text-muted-foreground">Install Claude Code or Codex, sign in in your terminal, then refresh.</p> : null}
      <label className="flex items-center justify-between gap-3 text-xs">
        <span className="text-muted-foreground">Printer</span>
        <select
          aria-label="Printer for printability checks"
          value={printer}
          onChange={(event) => choosePrinter(event.target.value as PrinterId)}
          className="theme-control min-w-0 max-w-[60%] rounded-md border border-[var(--hairline)] bg-transparent px-2 py-1 text-xs"
        >
          {PRINTERS.map((item) => (
            <option key={item.id} value={item.id}>
              {item.label}
            </option>
          ))}
        </select>
      </label>
      <details className="text-xs">
        <summary className="cursor-pointer py-1">References & copies{meshReference ? ` · ${meshReference.name}` : ""}</summary>
        <div className="flex max-h-64 flex-col gap-3 overflow-y-auto py-2">
          <ReferenceImport disabled={isLoading || isProjectLoading} onImport={importReference} />
          {meshReference ? <>
            <p className="text-muted-foreground">{meshReference.mode === "preserve" ? "Faceted STL source" : "Approximate reconstruction reference"} · {meshReference.facts.triangles.toLocaleString()} triangles · {Object.values(meshReference.facts.bounds).join(" × ")} mm</p>
            <div className="flex flex-wrap gap-2">
              <Button variant="outline" size="sm" onClick={() => {
                const bytes = Uint8Array.from(atob(meshReference.data), (value) => value.charCodeAt(0));
                const url = URL.createObjectURL(new Blob([bytes], { type: "model/stl" }));
                const link = document.createElement("a");
                link.href = url; link.download = meshReference.name; link.click();
                setTimeout(() => URL.revokeObjectURL(url), 1000);
              }}>Download original STL</Button>
              {meshReference.mode === "reconstruct" && !code.trim() ? <Button size="sm" disabled={isLoading} onClick={() => sendChat("Reconstruct an editable parametric copy of the imported STL. Preserve its measured dimensions, explain assumptions, and check the resulting geometry.")}>Reconstruct editable copy</Button> : null}
            </div>
          </> : null}
          {projectId ? <Button variant="outline" size="sm" disabled={isSaving || isLoading} onClick={() => void saveCopy()}>Save as a new copy</Button> : null}
        </div>
      </details>
    </div>
  );

  useEffect(() => {
    if (demoOpened.current || !hasInitialized) return;
    // The public demo opens the first demo part when no other was asked for.
    const slug = initialDemo ?? (DEMO_ONLY ? demos[0]?.slug : undefined);
    if (!slug || !demos.some((item) => item.slug === slug)) return;
    const timer = window.setTimeout(() => {
      demoOpened.current = true;
      void openDemo(slug);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [demos, hasInitialized, initialDemo, openDemo]);

  const changeRailOpen = useCallback((open: boolean) => {
    setRailOpen(open);
    try {
      window.localStorage.setItem(RAIL_OPEN_KEY, open ? "1" : "0");
    } catch {
      /* storage can be unavailable; the choice lasts for this visit */
    }
  }, []);

  const nextDemoVersion = (target: Demo) => {
    if (demoStep < demoReached) selectDemoStep(target, demoStep + 1);
    else playDemoStep(target, demoStep + 1);
  };

  const replayDemoVersion = (target: Demo) => {
    if (demoStep >= target.steps.length) {
      // "Watch again" builds the whole story from version 1.
      demoReachedRef.current = 0;
      setDemoReached(0);
      playDemoStep(target, 1);
    } else {
      playDemoStep(target, demoStep);
    }
  };

  // A demo shows its steps; a project shows its saved revisions, oldest first.
  const railVersions = useMemo<RailVersion[] | null>(() => {
    if (demo) {
      return demo.steps.map((step, index) => ({
        number: index + 1,
        title: stepTitle(step),
        detail: step.prompt,
        built: index + 1 <= demoReached,
      }));
    }
    if (revisions.length === 0) return null;
    return revisions
      .slice()
      .sort((a, b) => a.revisionNumber - b.revisionNumber)
      .map((revision) => ({
        number: revision.revisionNumber,
        title: `Version ${revision.revisionNumber}`,
        meta: VERSION_TIME.format(new Date(revision.createdAt)),
        built: true,
      }));
  }, [demo, demoReached, revisions]);

  const busy = !hasInitialized || isLoading || isProjectLoading || isSaving;
  const changeModel = (id: string) => {
    const option = modelOptions.find((model) => model.id === id);
    if (busy || !option || option.disabled || id === modelId) return;
    setModelId(id);
    setIsDirty(true);
  };

  const newPart = () => {
    if (!startNewProject()) return;
    stopDemoPlayback();
    setDemo(null);
  };
  const openPart = async (id: string) => {
    if (!(await loadProject(id))) return;
    stopDemoPlayback();
    setDemo(null);
  };

  const commands: StudioCommand[] = [
    { id: "new-part", label: "New part", group: "Actions", icon: FilePlus2, disabled: busy,
      onSelect: newPart },
    { id: "save-part", label: projectId ? "Save revision" : "Save part", group: "Actions", icon: Save,
      disabled: busy || (!isDirty && projectId !== null), onSelect: saveCurrentRevision },
    { id: "fit-view", label: "Fit model in view", group: "Actions", icon: Maximize, keywords: ["zoom", "camera", "center"],
      disabled: !glbUrl, onSelect: () => setFitRequest((value) => value + 1) },
    { id: "advanced", label: advancedOpen ? "Close advanced editor" : "Open advanced editor", group: "Actions", icon: Code2,
      disabled: busy, onSelect: () => setAdvancedOpen(!advancedOpen) },
    ...EXPORT_FORMATS.map(({ id, label, desc }): StudioCommand => ({
      id: `export-${id}`, label: `Export ${label}`, group: "Export", icon: Download,
      keywords: [desc], disabled: busy, onSelect: () => handleExport(id),
    })),
    ...projects.map((project): StudioCommand => ({
      id: `project-${project.id}`, label: project.name, group: "Open part", icon: FolderOpen,
      disabled: busy || project.id === projectId,
      onSelect: () => openPart(project.id),
    })),
    ...(railVersions ?? []).map((version): StudioCommand => ({
      id: `version-${version.number}`, label: `Version ${version.number} · ${version.title}`, group: "Versions", icon: History,
      disabled: busy || !version.built || version.number === (demo ? demoStep : currentRevision),
      onSelect: () => demo ? selectDemoStep(demo, version.number) : loadRevision(version.number),
    })),
  ];

  return (
    <div className="wb theme-page flex h-dvh flex-col overflow-hidden">
      <ActionSearchBar open={commandsOpen} onOpenChange={setCommandsOpen} commands={DEMO_ONLY ? [] : commands} onError={setError} />
      <CommandBar
        onExport={handleExport}
        projects={projects}
        projectId={projectId}
        isDirty={isDirty}
        isSaving={isSaving}
        advancedOpen={advancedOpen}
        onAdvancedChange={setAdvancedOpen}
        onProjectChange={openPart}
        onNewProject={newPart}
        onSave={saveCurrentRevision}
        onOpenCommands={() => setCommandsOpen(true)}
        demoOnly={DEMO_ONLY}
        busy={busy}
      />

      {!hasInitialized ? (
        <div className="flex min-h-0 flex-1 items-center justify-center">
          <div className="size-8 animate-spin rounded-full border-2 border-[var(--hairline-strong)] border-t-[var(--accent)]" />
        </div>
      ) : showWelcome ? (
        <main className="relative min-h-0 flex-1 overflow-y-auto">
          <div className="relative mx-auto flex min-h-full max-w-5xl flex-col items-center justify-center px-4 py-10 sm:px-8">
            <div className="mb-8 max-w-2xl text-center">
              <p className="type-label mb-4">Describe → Refine → Print</p>
              <h1 className="type-h1">
                What do you want to <em>make?</em>
              </h1>
              <p className="mx-auto mt-4 max-w-xl type-body-l">
                Describe a single part in plain language. Add dimensions if you have
                them—we’ll turn it into editable, export-ready CAD.
              </p>
            </div>
            <div className="min-h-[380px] w-full max-w-3xl">
              <ChatPane
                messages={messages}
                onSend={sendChat}
                isLoading={isLoading || isProjectLoading}
                lastError={error}
                modelId={modelId}
                modelOptions={modelOptions}
                onModelChange={changeModel}
                supportsVision={modelConfig?.supportsVision ?? false}
                selection={selectedFace}
                variant="welcome"
                tools={workspaceTools}
                initialInput={initialPrompt}
              />
            </div>
            <p className="mt-5 text-center text-[11px] text-zinc-600">
              Valid geometry is saved automatically as an immutable revision.
            </p>
            {demos.length > 0 && (
              <div className="mt-8 w-full max-w-3xl">
                <p className="type-label mb-3 text-center">See how it’s built</p>
                <div className="grid gap-2 sm:grid-cols-3">
                  {demos.map((item) => (
                    <button
                      key={item.slug}
                      type="button"
                      onClick={() => void openDemo(item.slug)}
                      className="theme-inset rounded-xl border p-3.5 text-left transition-colors hover:border-[var(--hairline-strong)]"
                    >
                      <p className="text-sm font-medium text-[var(--ink)]">{item.title}</p>
                      <p className="mt-1 text-xs leading-5 text-[var(--ink-2)]">
                        {item.summary}
                      </p>
                      <p className="mt-2 text-[10px] text-zinc-500">
                        {item.steps} steps · replay
                      </p>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </main>
      ) : (
        <main className="theme-viewport-frame relative flex min-h-0 flex-1 gap-2 overflow-hidden p-2">
          {railVersions && (
            <VersionRail
              heading={demo ? demo.title : "Versions"}
              versions={railVersions}
              selected={demo ? (demoPlaying ? null : demoStep) : currentRevision}
              disabled={demo ? demoPlaying : isLoading || isProjectLoading}
              open={railOpen}
              onOpenChange={changeRailOpen}
              onSelect={(number) =>
                demo ? selectDemoStep(demo, number) : void loadRevision(number)
              }
              onClose={demo && !DEMO_ONLY ? exitDemo : undefined}
              footer={
                demo ? (
                  <DemoControls
                    demo={demo}
                    step={demoStep}
                    reached={demoReached}
                    playing={demoPlaying}
                    onNext={() => nextDemoVersion(demo)}
                    onReplay={() => replayDemoVersion(demo)}
                  />
                ) : undefined
              }
              compactAction={
                demo ? (
                  <button
                    type="button"
                    onClick={() =>
                      demoStep >= demo.steps.length
                        ? replayDemoVersion(demo)
                        : nextDemoVersion(demo)
                    }
                    disabled={demoPlaying}
                    aria-label={
                      demoStep >= demo.steps.length ? "Watch again" : "Next version"
                    }
                    title={demoStep >= demo.steps.length ? "Watch again" : "Next version"}
                    className="flex size-9 items-center justify-center rounded-xl bg-[var(--ink)] text-[var(--paper)] disabled:opacity-50"
                  >
                    {demoStep >= demo.steps.length ? (
                      <RotateCcw className="size-4" />
                    ) : (
                      <ArrowRight className="size-4" />
                    )}
                  </button>
                ) : undefined
              }
            />
          )}

          <div className="relative min-w-0 flex-1">
            <div className="h-full overflow-hidden rounded-2xl border border-[var(--hairline)] bg-[var(--clay)]">
              <ViewportPane
                glbUrl={glbUrl}
                fitRequest={fitRequest}
                code={code}
                isLoading={isLoading || isProjectLoading}
                previewUrl={isLoading ? buildPreview?.url : undefined}
                previewLabel={buildPreview ? `Built: ${buildPreview.name}` : undefined}
                progressMessage={
                  isLoading
                    ? runEvents.filter((event) => event.stage !== "snapshot").at(-1)
                        ?.message
                    : undefined
                }
                showSelectionCard={false}
                onThumbnail={handleThumbnail}
                onSelectionChange={handleSelectionChange}
                warningFaceIds={warningFaceIds}
              />
            </div>

            {evidence && (
              <div className="pointer-events-none absolute left-3 top-3 z-20 hidden sm:block">
                <div className="theme-floating pointer-events-auto max-h-[calc(100dvh-16rem)] w-[300px] overflow-y-auto rounded-2xl border px-3.5 pb-3.5 shadow-xl shadow-black/10 backdrop-blur-xl empty:hidden">
                  <VerificationPanel inspection={evidence} onShowFaces={showFaces} framed={false} />
                </div>
              </div>
            )}

            <div className="pointer-events-none absolute right-3 top-3 z-20 hidden sm:block">
              <div className="theme-floating pointer-events-auto w-[230px] rounded-2xl border p-3.5 shadow-xl shadow-black/10 backdrop-blur-xl">
                <div className="flex items-center gap-2">
                  <span className="flex size-7 items-center justify-center rounded-lg bg-[var(--control-hover)] text-zinc-400">
                    <Ruler className="size-3.5" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-[10px] uppercase tracking-[0.14em] text-zinc-600">
                      Overall size
                    </p>
                    {inspection?.bounding_box_mm ? (
                      <p className="mt-0.5 text-xs font-medium">
                        {inspection.bounding_box_mm.x.toFixed(1)} ×{" "}
                        {inspection.bounding_box_mm.y.toFixed(1)} ×{" "}
                        {inspection.bounding_box_mm.z.toFixed(1)} mm
                      </p>
                    ) : (
                      <p className="mt-0.5 text-xs text-zinc-500">
                        Awaiting model dimensions
                      </p>
                    )}
                  </div>
                </div>
                {inspection && (
                  <div className="mt-3 flex items-center justify-between border-t border-[var(--hairline)] pt-2.5 text-[10px] text-zinc-500">
                    <span className="flex items-center gap-1.5">
                      <Box className="size-3" />
                      {inspection.shape_type ?? "Solid"}
                    </span>
                    <span>{Math.round(inspection.volume_mm3 ?? 0).toLocaleString()} mm³</span>
                  </div>
                )}
              </div>
            </div>

            <div className="pointer-events-none absolute inset-x-2 bottom-2 z-30 flex justify-center sm:inset-x-3 sm:bottom-3">
              <div className="pointer-events-auto w-full max-w-[620px]">
                <ChatPane
                  messages={messages}
                  onSend={sendChat}
                  isLoading={isLoading || isProjectLoading}
                  lastError={error}
                  modelId={modelId}
                  modelOptions={modelOptions}
                  onModelChange={changeModel}
                  supportsVision={modelConfig?.supportsVision ?? false}
                  selection={selectedFace}
                  runEvents={isLoading ? runEvents : undefined}
                  runStartedAt={runStartedAt}
                  tools={DEMO_ONLY ? undefined : workspaceTools}
                  onShowFaces={showFaces}
                  readOnly={
                    DEMO_ONLY ? (
                      <span>
                        This is a demo.{" "}
                        <a
                          href={RUN_LOCALLY_URL}
                          className="font-medium text-[var(--ink)] underline underline-offset-2"
                        >
                          Run Nfinit on your computer
                        </a>{" "}
                        to make your own parts with Claude Code or Codex.
                      </span>
                    ) : undefined
                  }
                  versions={
                    demo
                      ? {
                          selected: demoPlaying ? null : demoStep,
                          onSelect: (step) => selectDemoStep(demo, step),
                        }
                      : undefined
                  }
                />
              </div>
            </div>
          </div>
        </main>
      )}

      {error && (
        <div className="fixed left-1/2 top-20 z-[70] flex w-[calc(100%-2rem)] max-w-xl -translate-x-1/2 items-start gap-3 rounded-xl border border-[var(--danger)]/30 bg-[var(--sheet)] px-4 py-3 text-sm text-[var(--danger)] shadow-xl">
          <span className="min-w-0 flex-1">
            {error}
            {recoverableCode && (
              <button
                type="button"
                onClick={recoverLastAttempt}
                className="mt-2 block text-xs font-medium text-[var(--ink)] underline underline-offset-2"
              >
                Open the last attempt in the editor
              </button>
            )}
          </span>
          <button
            type="button"
            onClick={() => {
              setError(null);
              setRecoverableCode(null);
            }}
            aria-label="Dismiss error"
            className="rounded-md p-1 text-[var(--danger)] hover:bg-[var(--control-hover)]"
          >
            <X className="size-4" />
          </button>
        </div>
      )}

      {advancedOpen && (
        <>
          <button
            type="button"
            aria-label="Close advanced tools"
            className="fixed inset-0 top-16 z-40 bg-black/55 backdrop-blur-[2px]"
            onClick={() => setAdvancedOpen(false)}
          />
          <aside className="theme-floating fixed inset-y-0 right-0 z-50 mt-16 flex w-full max-w-3xl flex-col border-l shadow-2xl shadow-black/30">
            <div className="flex h-14 shrink-0 items-center gap-3 border-b border-[var(--hairline)] px-4">
              <Code2 className="size-4 text-[var(--ink-2)]" />
              <div className="min-w-0 flex-1">
                <h2 className="text-sm font-semibold">Advanced editor</h2>
                <p className="text-[10px] text-zinc-600">Edit build123d source directly</p>
              </div>
              <AIModelSelector value={modelId} options={modelOptions} onChange={changeModel} disabled={busy} />
              <button
                type="button"
                onClick={() => setAdvancedOpen(false)}
                aria-label="Close advanced editor"
                className="theme-control rounded-lg p-2 text-zinc-500 hover:text-[var(--page-fg)]"
              >
                <X className="size-4" />
              </button>
            </div>
            <div className="min-h-0 flex-1">
              <EditorPane
                code={code}
                onCodeChange={(value) => {
                  setCode(value);
                  setIsDirty(true);
                }}
                onGenerate={handleGenerate}
              />
            </div>
          </aside>
        </>
      )}
    </div>
  );
}
