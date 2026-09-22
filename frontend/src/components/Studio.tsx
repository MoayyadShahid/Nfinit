"use client";

import { ChatPane } from "@/components/ChatPane";
import { CommandBar, type ExportFormat } from "@/components/CommandBar";
import { EditorPane } from "@/components/EditorPane";
import { ViewportPane } from "@/components/ViewportPane";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { DEFAULT_MODEL, getModelConfig, MODEL_CONFIGS } from "@/lib/constants";
import {
  addRevision,
  createProject,
  getProject,
  listProjects,
  listRevisions,
  type ProjectRevision,
  type ProjectState,
  type ProjectSummary,
} from "@/lib/projects";
import {
  getTextContent,
  type ChatMessage,
  type ContentPart,
  type FaceSelection,
  type ModelInspection,
} from "@/lib/types";
import {
  Box,
  CheckCircle2,
  Code2,
  MousePointer2,
  Ruler,
  Sparkles,
  X,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";
const LAST_PROJECT_KEY = "nfinit:last-project-id";

const DEFAULT_CODE = [
  "width, depth, height = 10.0, 10.0, 10.0",
  "",
  "with BuildPart() as part:",
  "    Box(width, depth, height)",
  "",
  "result = part.part",
].join("\n");

export default function Home() {
  const [code, setCode] = useState(DEFAULT_CODE);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [modelId, setModelId] = useState<string>(DEFAULT_MODEL);
  const [glbUrl, setGlbUrl] = useState<string | null>(null);
  const [selectedFace, setSelectedFace] = useState<FaceSelection | null>(null);
  const [isLoading, setIsLoading] = useState(false);
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

  const modelConfig = useMemo(() => getModelConfig(modelId), [modelId]);

  const inspectModel = useCallback(async (codeToInspect: string) => {
    const response = await fetch(`${BACKEND_URL}/inspect-model`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code: codeToInspect }),
    });
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
      const res = await fetch(`${BACKEND_URL}/generate-mesh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code: codeToExecute }),
      });

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
      const state = revision.state;
      setCode(state.code);
      setMessages(state.messages);
      setModelId(state.modelId || DEFAULT_MODEL);
      setSelectedFace(state.selection);
      setLastRunId(state.lastRunId);
      setCurrentRevision(revision.revisionNumber);
      setIsDirty(false);
      await Promise.all([
        generateMesh(state.code, false),
        inspectModel(state.code),
      ]);
      setSelectedFace(state.selection);
    },
    [generateMesh, inspectModel]
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
          getProject(BACKEND_URL, nextProjectId),
          listRevisions(BACKEND_URL, nextProjectId),
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

  const persistSnapshot = useCallback(
    async (state: ProjectState, suggestedName?: string) => {
      setIsSaving(true);
      try {
        if (projectId) {
          const revision = await addRevision(BACKEND_URL, projectId, state);
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
            BACKEND_URL,
            suggestedName || projectNameFromMessages(state.messages),
            state
          );
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
      } finally {
        setIsSaving(false);
      }
    },
    [projectId, projectNameFromMessages]
  );

  const saveCurrentRevision = useCallback(async () => {
    setError(null);
    setIsSaving(true);
    try {
      const validationResponse = await fetch(`${BACKEND_URL}/inspect-model`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code }),
      });
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

  const handleChatSend = useCallback(
    async (text: string, imageUrls?: string[]) => {
      if (!text.trim()) return;

      setIsLoading(true);
      setError(null);

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

      try {
        const res = await fetch("/api/generate-code", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            messages: newMessages,
            code,
            modelId,
            selection: selectedFace,
            supportsStructuredOutputs:
              modelConfig?.supportsStructuredOutputs ?? false,
          }),
        });

        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "Failed to generate code");

        const generatedCode = data.code;
        const assistantMessage: ChatMessage = {
          role: "assistant",
          content: generatedCode,
          agent: {
            runId: data.runId,
            plan: data.plan,
            trace: data.trace,
            inspection: data.inspection,
            usage: data.usage,
          },
        };
        const completedMessages = [...newMessages, assistantMessage];
        setCode(generatedCode);
        setMessages(completedMessages);
        setLastRunId(data.runId ?? null);
        setInspection(data.inspection ?? null);
        setIsDirty(true);
        await generateMesh(generatedCode);
        try {
          await persistSnapshot(
            {
              code: generatedCode,
              messages: completedMessages,
              modelId,
              selection: null,
              lastRunId: data.runId ?? null,
            },
            text.trim().slice(0, 60)
          );
        } catch (saveError) {
          setError(
            `Model generated, but revision save failed: ${
              saveError instanceof Error ? saveError.message : "Unknown error"
            }`
          );
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : "Generation failed");
        setMessages((prev) => prev.slice(0, -1));
      } finally {
        setIsLoading(false);
      }
    },
    [
      messages,
      code,
      modelId,
      modelConfig,
      selectedFace,
      generateMesh,
      persistSnapshot,
    ]
  );

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
      try {
        const res = await fetch(`${BACKEND_URL}/export-model`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ code, format }),
        });

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
        setError(e instanceof Error ? e.message : "Export failed");
      }
    },
    [code]
  );

  useEffect(() => {
    let active = true;
    listProjects(BACKEND_URL)
      .then(async (items) => {
        if (!active) return;
        setProjects(items);
        const storedProjectId = window.localStorage.getItem(LAST_PROJECT_KEY);
        const latest =
          items.find((project) => project.id === storedProjectId) ?? items[0];
        if (!latest) return;
        setIsProjectLoading(true);
        const [project, history] = await Promise.all([
          getProject(BACKEND_URL, latest.id),
          listRevisions(BACKEND_URL, latest.id),
        ]);
        if (!active) return;
        setProjectId(project.id);
        window.localStorage.setItem(LAST_PROJECT_KEY, project.id);
        setRevisions(history);
        if (project.latestRevision) {
          await applyRevision(project.latestRevision);
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
  }, [applyRevision]);

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

  return (
    <div className="theme-page flex h-dvh flex-col overflow-hidden">
      <CommandBar
        onExport={handleExport}
        projects={projects}
        projectId={projectId}
        isDirty={isDirty}
        isSaving={isSaving}
        advancedOpen={advancedOpen}
        onAdvancedChange={setAdvancedOpen}
        onProjectChange={loadProject}
        onNewProject={startNewProject}
        onSave={saveCurrentRevision}
      />

      {!hasInitialized ? (
        <div className="flex min-h-0 flex-1 items-center justify-center">
          <div className="size-8 animate-spin rounded-full border-2 border-zinc-800 border-t-violet-400" />
        </div>
      ) : showWelcome ? (
        <main className="relative min-h-0 flex-1 overflow-y-auto">
          <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_50%_20%,rgba(124,58,237,0.16),transparent_36%),radial-gradient(circle_at_80%_80%,rgba(37,99,235,0.09),transparent_30%)]" />
          <div className="relative mx-auto flex min-h-full max-w-5xl flex-col items-center justify-center px-4 py-10 sm:px-8">
            <div className="mb-8 max-w-2xl text-center">
              <div className="mx-auto mb-5 flex size-12 items-center justify-center rounded-2xl border border-violet-300/20 bg-violet-400/10 text-violet-300 shadow-xl shadow-violet-500/10">
                <Sparkles className="size-5" />
              </div>
              <h1 className="text-balance text-3xl font-semibold tracking-[-0.035em] sm:text-5xl">
                What do you want to make?
              </h1>
              <p className="mx-auto mt-4 max-w-xl text-sm leading-6 text-zinc-500 sm:text-base">
                Describe a single part in plain language. Add dimensions if you have
                them—we’ll turn it into editable, export-ready CAD.
              </p>
            </div>
            <div className="h-[340px] w-full max-w-3xl">
              <ChatPane
                messages={messages}
                onSend={handleChatSend}
                isLoading={isLoading || isProjectLoading}
                lastError={error}
                supportsVision={modelConfig?.supportsVision ?? false}
                selection={selectedFace}
                variant="welcome"
              />
            </div>
            <p className="mt-5 text-center text-[11px] text-zinc-600">
              Valid geometry is saved automatically as an immutable revision.
            </p>
          </div>
        </main>
      ) : (
        <main className="theme-viewport-frame relative min-h-0 flex-1 overflow-hidden p-2">
          <div className="h-full overflow-hidden rounded-2xl border border-black/10 bg-[#e7e8eb] shadow-2xl shadow-black/30">
            <ViewportPane
              glbUrl={glbUrl}
              code={code}
              isLoading={isLoading || isProjectLoading}
              showSelectionCard={false}
              onSelectionChange={(selection) => {
                setSelectedFace(selection);
                setIsDirty(true);
              }}
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
              <div className="selection-surface pointer-events-auto rounded-2xl border border-violet-300/25 p-4 shadow-2xl shadow-violet-950/10 backdrop-blur-xl">
                <div className="flex items-start gap-3">
                  <span className="flex size-8 shrink-0 items-center justify-center rounded-xl bg-violet-400/12 text-violet-300">
                    <MousePointer2 className="size-4" />
                  </span>
                  <div className="min-w-0">
                    <p className="text-xs font-semibold text-violet-700 dark:text-violet-100">
                      {selectedFace.surfaceType
                        ? `${selectedFace.surfaceType[0].toUpperCase()}${selectedFace.surfaceType.slice(1)} face`
                        : "Selected face"}
                    </p>
                    <p className="mt-1 font-mono text-[9px] text-violet-300/50">
                      {selectedFace.entityId?.slice(0, 18) ??
                        selectedFace.point.join(", ")}
                    </p>
                    <p className="mt-2 text-[11px] leading-4 text-zinc-400">
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
                            active ? "bg-violet-500" : "bg-zinc-700"
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
                onSend={handleChatSend}
                isLoading={isLoading || isProjectLoading}
                lastError={error}
                supportsVision={modelConfig?.supportsVision ?? false}
                selection={selectedFace}
              />
            </div>
          </div>
        </main>
      )}

      {error && (
        <div className="fixed left-1/2 top-20 z-[70] flex w-[calc(100%-2rem)] max-w-xl -translate-x-1/2 items-start gap-3 rounded-xl border border-red-400/20 bg-red-950/90 px-4 py-3 text-sm text-red-100 shadow-2xl backdrop-blur">
          <span className="min-w-0 flex-1">{error}</span>
          <button
            type="button"
            onClick={() => setError(null)}
            aria-label="Dismiss error"
            className="rounded-md p-1 text-red-300 hover:bg-white/10"
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
              <Code2 className="size-4 text-violet-400" />
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
