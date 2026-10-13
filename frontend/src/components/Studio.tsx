"use client";

import { ChatPane } from "@/components/ChatPane";
import {
  CommandBar,
  type ExportFormat,
  type Viewer,
} from "@/components/CommandBar";
import { DemoReplay } from "@/components/DemoReplay";
import { EditorPane } from "@/components/EditorPane";
import { Paywall, type PaywallReason } from "@/components/Paywall";
import { ViewportPane } from "@/components/ViewportPane";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  getBillingStatus,
  openBillingPortal,
  savePendingAction,
  type PendingAction,
  SubscriptionRequiredError,
  takePendingAction,
  waitForActiveSubscription,
  type BillingStatus,
} from "@/lib/billing";
import { DEFAULT_MODEL, getModelConfig, MODEL_CONFIGS } from "@/lib/constants";
import {
  addRevision,
  createProject,
  getProject,
  getRevisionMesh,
  listProjects,
  listRevisions,
  uploadThumbnail,
  type ProjectRevision,
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
  FIRST_DEMO,
  getDemo,
  listDemos,
  toRunEvent,
  type Demo,
  type DemoSummary,
} from "@/lib/demos";
import { sandboxRequest } from "@/lib/sandbox";
import { useBuildPreview } from "@/lib/useBuildPreview";
import {
  getTextContent,
  type ChatMessage,
  type ContentPart,
  type FaceSelection,
  type ModelInspection,
  type RunEvent,
} from "@/lib/types";
import {
  Box,
  CheckCircle2,
  Code2,
  MousePointer2,
  Ruler,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

const LAST_PROJECT_KEY = "nfinit:last-project-id";
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

const LAPSED_MESSAGE = "Subscribe to open and edit your parts again.";

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

/** The chat of a demo's first `steps` steps, as the agent recorded it. */
function demoHistory(target: Demo, steps: number): ChatMessage[] {
  return target.steps.slice(0, steps).flatMap((recorded): ChatMessage[] => [
    { role: "user", content: recorded.prompt },
    { role: "assistant", content: recorded.code, agent: recorded.agent },
  ]);
}

export default function Studio({
  viewer,
  initialPrompt,
  initialProjectId,
  initialDemo,
  startNew = false,
}: {
  viewer?: Viewer | null;
  initialPrompt?: string;
  initialProjectId?: string;
  /** Open this recorded demo, e.g. from /studio?demo=drone-frame. */
  initialDemo?: string;
  startNew?: boolean;
}) {
  const [code, setCode] = useState(DEFAULT_CODE);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [modelId, setModelId] = useState<string>(DEFAULT_MODEL);
  const [glbUrl, setGlbUrl] = useState<string | null>(null);
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
  const [revisions, setRevisions] = useState<ProjectRevision[]>([]);
  const [currentRevision, setCurrentRevision] = useState<number | null>(null);
  const [lastRunId, setLastRunId] = useState<string | null>(null);
  const [isDirty, setIsDirty] = useState(true);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [hasInitialized, setHasInitialized] = useState(false);
  const [inspection, setInspection] = useState<ModelInspection | null>(null);
  // A recorded demo being replayed (no project, no backend runs).
  const [demos, setDemos] = useState<DemoSummary[]>([]);
  const [demo, setDemo] = useState<Demo | null>(null);
  const [demoStep, setDemoStep] = useState(0);
  const [demoPlaying, setDemoPlaying] = useState(false);
  const demoTimers = useRef<number[]>([]);
  const demoGeneration = useRef(0);
  const demoOpened = useRef(false);
  // Code from a failed run, offered so the tokens spent on it are not lost.
  const [recoverableCode, setRecoverableCode] = useState<string | null>(null);
  const [billing, setBilling] = useState<BillingStatus | null>(null);
  const [paywall, setPaywall] = useState<PaywallReason | null>(null);
  // Unknown status is not locked: the backend still answers 402 if it must.
  const isLocked = billing !== null && !billing.active;
  const [isActivating, setIsActivating] = useState(false);
  // An action interrupted by the paywall, run once the subscription is live.
  const [resumeAction, setResumeAction] = useState<PendingAction | null>(null);
  const mountedRef = useRef(true);
  const lastThumbnailRef = useRef<Blob | null>(null);
  const thumbnailContextRef = useRef({
    projectId: null as string | null,
    isDirty: true,
    isLatestRevision: false,
    needsThumbnail: false,
  });

  const modelConfig = useMemo(() => getModelConfig(modelId), [modelId]);

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
        if (prev) URL.revokeObjectURL(prev);
        return url;
      });
    } catch (e) {
      setError(
        e instanceof SubscriptionRequiredError
          ? LAPSED_MESSAGE
          : e instanceof Error
            ? e.message
            : "Mesh generation failed"
      );
    }
  }, []);

  // A saved revision's mesh is stored on the backend: download it instead of
  // building it again, and take its geometry facts from the same answer.
  const loadRevisionMesh = useCallback(async (revision: ProjectRevision) => {
    setError(null);
    try {
      const mesh = await getRevisionMesh(
        revision.projectId,
        revision.revisionNumber
      );
      setInspection(mesh.inspection.valid ? mesh.inspection : null);
      setGlbUrl((prev) => {
        if (prev) URL.revokeObjectURL(prev);
        return mesh.url;
      });
    } catch (e) {
      setError(
        e instanceof SubscriptionRequiredError
          ? LAPSED_MESSAGE
          : e instanceof Error
            ? e.message
            : "Mesh generation failed"
      );
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
      const state = revision.state;
      setCode(state.code);
      setMessages(state.messages);
      // A model no longer offered (e.g. GPT-5.6 Sol) falls back to the default.
      setModelId(getModelConfig(state.modelId) ? state.modelId : DEFAULT_MODEL);
      setSelectedFace(state.selection);
      setLastRunId(state.lastRunId);
      setCurrentRevision(revision.revisionNumber);
      setIsDirty(false);
      await loadRevisionMesh(revision);
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
        return;
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
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load project");
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
          setRevisions((previous) => [
            revision,
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
          setRevisions(project.latestRevision ? [project.latestRevision] : []);
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
      });
    } catch (e) {
      if (e instanceof SubscriptionRequiredError) {
        setPaywall("build");
      } else {
        setError(e instanceof Error ? e.message : "Failed to save revision");
      }
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
  ]);

  const startNewProject = useCallback(() => {
    if (isDirty && !window.confirm("Discard unsaved changes and start a new part?")) {
      return;
    }
    setGlbUrl((previous) => {
      if (previous) URL.revokeObjectURL(previous);
      return null;
    });
    setProjectId(null);
    window.localStorage.removeItem(LAST_PROJECT_KEY);
    setRevisions([]);
    setCurrentRevision(null);
    setCode(DEFAULT_CODE);
    setMessages([]);
    setModelId(DEFAULT_MODEL);
    setSelectedFace(null);
    setInspection(null);
    setLastRunId(null);
    setIsDirty(true);
    setError(null);
  }, [isDirty]);

  const loadRevision = useCallback(
    async (revisionNumber: number) => {
      if (
        isDirty &&
        !window.confirm("Discard unsaved changes and load this revision?")
      ) {
        return;
      }
      const revision = revisions.find(
        (item) => item.revisionNumber === revisionNumber
      );
      if (!revision) return;
      setIsProjectLoading(true);
      setError(null);
      try {
        await applyRevision(revision);
      } finally {
        setIsProjectLoading(false);
      }
    },
    [applyRevision, isDirty, revisions]
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

  /** Show a demo step's finished part and the chat that led to it. */
  const showDemoStep = useCallback((target: Demo, step: number) => {
    const recorded = target.steps[step - 1];
    setMessages(demoHistory(target, step));
    setCode(recorded.code);
    setInspection(recorded.agent.inspection.valid ? recorded.agent.inspection : null);
    setGlbUrl((previous) => {
      if (previous) URL.revokeObjectURL(previous);
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

  const openDemo = useCallback(
    async (slug: string) => {
      try {
        const target = await getDemo(slug);
        if (!mountedRef.current) return;
        setProjectId(null);
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
          code,
          modelId,
          selection: selectedFace,
          supportsStructuredOutputs:
            modelConfig?.supportsStructuredOutputs ?? false,
          projectId,
        });
      } catch (e) {
        if (e instanceof SubscriptionRequiredError) {
          savePendingAction({ kind: "send", text: text.trim(), images: imageUrls });
          setPaywall("build");
        } else {
          setError(e instanceof Error ? e.message : "Could not start generation");
        }
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
      followRun,
      demo,
      stopDemoPlayback,
    ]
  );

  // Stopped at the paywall, the prompt stays in the box (ChatPane keeps its
  // input when this returns false) and is replayed after Checkout.
  const sendOrPaywall = useCallback(
    (text: string, imageUrls?: string[]) => {
      if (isLocked) {
        savePendingAction({ kind: "send", text: text.trim(), images: imageUrls });
        setPaywall("build");
        return false;
      }
      void handleChatSend(text, imageUrls);
      return true;
    },
    [handleChatSend, isLocked]
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
    async (format: ExportFormat) => {
      setError(null);
      if (isLocked) {
        savePendingAction({ kind: "export", format });
        setPaywall("export");
        return;
      }
      try {
        const res = await sandboxRequest("export-model", { code, format });

        if (!res.ok) {
          const err = await res
            .json()
            .catch(() => ({ detail: res.statusText }));
          throw new Error(err.detail || "Export failed");
        }

        const blob = await res.blob();
        const ext = { step: ".step", brep: ".brep", stl: ".stl" }[format];
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `model${ext}`;
        a.click();
        URL.revokeObjectURL(url);
      } catch (e) {
        if (e instanceof SubscriptionRequiredError) {
          savePendingAction({ kind: "export", format });
          setPaywall("export");
        } else {
          setError(e instanceof Error ? e.message : "Export failed");
        }
      }
    },
    [code, isLocked]
  );

  const handleAdvancedChange = useCallback(
    (open: boolean) => {
      if (open && isLocked) {
        setPaywall("build");
        return;
      }
      setAdvancedOpen(open);
    },
    [isLocked]
  );

  const handleSelectionChange = useCallback(
    (selection: FaceSelection | null) => {
      setSelectedFace(selection);
      setIsDirty(true);
    },
    []
  );

  const closePaywall = useCallback(() => {
    takePendingAction();
    setPaywall(null);
  }, []);

  const manageBilling = useCallback(() => {
    openBillingPortal().catch((e) =>
      setError(e instanceof Error ? e.message : "Could not open billing")
    );
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useEffect(() => {
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
    getBillingStatus()
      .then((status) => {
        if (mountedRef.current) setBilling(status);
      })
      .catch(() => {
        // Unknown status leaves the studio open; the backend still enforces.
      });
  }, []);

  // Back from Checkout: Stripe's webhook may land a moment after the
  // redirect, so wait for it, then finish what the paywall interrupted.
  useEffect(() => {
    if (!hasInitialized) return;
    const url = new URL(window.location.href);
    const outcome = url.searchParams.get("checkout");
    if (!outcome) return;
    url.searchParams.delete("checkout");
    window.history.replaceState(null, "", `${url.pathname}${url.search}`);
    if (outcome !== "success") {
      takePendingAction();
      return;
    }
    setIsActivating(true);
    void waitForActiveSubscription().then((status) => {
      if (!mountedRef.current) return;
      setIsActivating(false);
      if (!status) {
        setError(
          "Payment received. Your subscription is still activating; refresh in a minute."
        );
        return;
      }
      setBilling(status);
      setResumeAction(takePendingAction());
    });
  }, [hasInitialized]);

  useEffect(() => {
    if (!resumeAction || isLocked) return;
    setResumeAction(null);
    if (resumeAction.kind === "send") {
      void handleChatSend(resumeAction.text, resumeAction.images);
    } else {
      void handleExport(resumeAction.format);
    }
  }, [resumeAction, isLocked, handleChatSend, handleExport]);

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
      if (e.altKey && e.key === "Enter") {
        e.preventDefault();
        handleGenerate();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [handleGenerate]);

  useEffect(() => {
    return () => {
      if (glbUrl) URL.revokeObjectURL(glbUrl);
    };
  }, [glbUrl]);

  const showWelcome =
    hasInitialized && !projectId && messages.length === 0 && glbUrl === null;

  useEffect(() => {
    if (demoOpened.current || !hasInitialized || billing === null) return;
    const slug =
      initialDemo ??
      (showWelcome && isLocked && !initialPrompt ? FIRST_DEMO : undefined);
    if (!slug || !demos.some((item) => item.slug === slug)) return;
    demoOpened.current = true;
    void openDemo(slug);
  }, [billing, demos, hasInitialized, initialDemo, initialPrompt, isLocked, openDemo, showWelcome]);

  return (
    <div className="wb theme-page flex h-dvh flex-col overflow-hidden">
      <CommandBar
        viewer={viewer}
        onExport={handleExport}
        projects={projects}
        projectId={projectId}
        isDirty={isDirty}
        isSaving={isSaving}
        advancedOpen={advancedOpen}
        onAdvancedChange={handleAdvancedChange}
        onManageBilling={
          billing?.enabled && billing.status !== "none" ? manageBilling : undefined
        }
        onProjectChange={loadProject}
        onNewProject={startNewProject}
        onSave={saveCurrentRevision}
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
            <div className="h-[340px] w-full max-w-3xl">
              <ChatPane
                messages={messages}
                onSend={sendOrPaywall}
                isLoading={isLoading || isProjectLoading}
                lastError={error}
                supportsVision={modelConfig?.supportsVision ?? false}
                selection={selectedFace}
                variant="welcome"
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
        <main className="theme-viewport-frame relative min-h-0 flex-1 overflow-hidden p-2">
          <div className="h-full overflow-hidden rounded-2xl border border-[var(--hairline)] bg-[var(--clay)]">
            <ViewportPane
              glbUrl={glbUrl}
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
              onSelectBlocked={isLocked ? () => setPaywall("build") : undefined}
            />
          </div>

          <div className="pointer-events-none absolute left-5 top-5 z-20 hidden sm:block">
            <div className="theme-floating pointer-events-auto min-w-[230px] rounded-2xl border p-3.5 shadow-xl shadow-black/10 backdrop-blur-xl">
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

          {selectedFace && (
            <div className="pointer-events-none absolute right-5 top-20 z-20 max-w-[260px]">
              <div className="selection-surface pointer-events-auto rounded-2xl border border-[var(--hairline-strong)] p-4 shadow-xl">
                <div className="flex items-start gap-3">
                  <span className="flex size-8 shrink-0 items-center justify-center rounded-xl bg-[var(--clay)] text-[var(--accent)]">
                    <MousePointer2 className="size-4" />
                  </span>
                  <div className="min-w-0">
                    <p className="text-xs font-semibold text-[var(--ink)]">
                      {selectedFace.surfaceType
                        ? `${selectedFace.surfaceType[0].toUpperCase()}${selectedFace.surfaceType.slice(1)} face`
                        : "Selected face"}
                    </p>
                    <p className="mt-1 font-mono text-[9px] text-[var(--muted)]">
                      {selectedFace.entityId?.slice(0, 18) ??
                        selectedFace.point.join(", ")}
                    </p>
                    <p className="mt-2 text-[11px] leading-4 text-[var(--ink-2)]">
                      Describe the change below. Your request will target this face.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          )}

          <div className="pointer-events-none absolute inset-x-3 bottom-4 z-30 flex flex-col items-center gap-2">
            {revisions.length > 0 && (
              <div className="theme-floating pointer-events-auto flex max-w-[calc(100vw-2rem)] items-center gap-1 overflow-x-auto rounded-full border p-1.5 shadow-xl backdrop-blur-xl">
                <span className="hidden items-center gap-1.5 px-2 text-[10px] font-medium text-zinc-500 sm:flex">
                  <CheckCircle2 className="size-3 text-emerald-400" />
                  History
                </span>
                {revisions
                  .slice()
                  .reverse()
                  .map((revision) => {
                    const active = revision.revisionNumber === currentRevision;
                    return (
                      <button
                        key={revision.id}
                        type="button"
                        onClick={() => loadRevision(revision.revisionNumber)}
                        title={`Revision ${revision.revisionNumber} · ${new Date(
                          revision.createdAt
                        ).toLocaleString()}`}
                        className={`flex h-7 shrink-0 items-center gap-1.5 rounded-full px-2.5 text-[10px] font-medium transition-colors ${
                          active
                            ? "theme-primary-button shadow-sm"
                            : "theme-control text-zinc-500 hover:text-[var(--page-fg)]"
                        }`}
                      >
                        <span
                          className={`size-1.5 rounded-full ${
                            active ? "bg-[var(--accent)]" : "bg-[var(--hairline-strong)]"
                          }`}
                        />
                        v{revision.revisionNumber}
                      </button>
                    );
                  })}
              </div>
            )}
            <div className="pointer-events-auto w-full max-w-3xl">
              <ChatPane
                messages={messages}
                onSend={sendOrPaywall}
                isLoading={isLoading || isProjectLoading}
                lastError={error}
                supportsVision={modelConfig?.supportsVision ?? false}
                selection={selectedFace}
                runEvents={isLoading ? runEvents : undefined}
                runStartedAt={runStartedAt}
                header={
                  demo ? (
                    <DemoReplay
                      demo={demo}
                      step={demoStep}
                      playing={demoPlaying}
                      onNext={() => playDemoStep(demo, demoStep + 1)}
                      onReplay={() =>
                        playDemoStep(demo, demoStep >= demo.steps.length ? 1 : demoStep)
                      }
                      onExit={exitDemo}
                    />
                  ) : undefined
                }
              />
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

      {isActivating && (
        <div
          role="status"
          className="theme-floating fixed left-1/2 top-20 z-[70] -translate-x-1/2 rounded-full border px-4 py-2 text-sm shadow-xl"
        >
          Activating your subscription…
        </div>
      )}

      <Paywall
        reason={paywall}
        onClose={closePaywall}
        taxAtCheckout={billing?.taxAtCheckout ?? false}
      />

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
              <Select
                value={modelId}
                onValueChange={(value) => {
                  setModelId(value);
                  setIsDirty(true);
                }}
              >
                <SelectTrigger
                  aria-label="Generation model"
                  className="h-8 w-[180px] border-[var(--hairline)] bg-transparent text-xs"
                >
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {MODEL_CONFIGS.map((model) => (
                    <SelectItem key={model.id} value={model.id}>
                      {model.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
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
