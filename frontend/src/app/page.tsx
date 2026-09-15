"use client";

import { ChatPane } from "@/components/ChatPane";
import { CommandBar, type ExportFormat } from "@/components/CommandBar";
import { EditorPane } from "@/components/EditorPane";
import { ViewportPane } from "@/components/ViewportPane";
import { DEFAULT_MODEL, getModelConfig } from "@/lib/constants";
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
} from "@/lib/types";
import { cn } from "@/lib/utils";
import { useCallback, useEffect, useMemo, useState } from "react";

const BACKEND_URL =
  process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";
const LAST_PROJECT_KEY = "nfinit:last-project-id";

export type LayoutMode = "default" | "code" | "mesh";

const DEFAULT_CODE = [
  "width, depth, height = 10.0, 10.0, 10.0",
  "",
  "with BuildPart() as part:",
  "    Box(width, depth, height)",
  "",
  "result = part.part",
].join("\n");

export default function Home() {
  const [layoutMode, setLayoutMode] = useState<LayoutMode>("default");
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

  const modelConfig = useMemo(() => getModelConfig(modelId), [modelId]);

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
      await generateMesh(state.code, false);
      setSelectedFace(state.selection);
    },
    [generateMesh]
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
      await generateMesh(code);
    } finally {
      setIsLoading(false);
    }
  }, [code, generateMesh]);

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
        if (active) setIsProjectLoading(false);
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

  return (
    <div className="flex h-screen flex-col bg-[#000000] text-zinc-200">
      <CommandBar
        modelId={modelId}
        onModelChange={(value) => {
          setModelId(value);
          setIsDirty(true);
        }}
        layoutMode={layoutMode}
        onLayoutChange={setLayoutMode}
        onExport={handleExport}
        projects={projects}
        projectId={projectId}
        revisions={revisions}
        currentRevision={currentRevision}
        isDirty={isDirty}
        isSaving={isSaving}
        onProjectChange={loadProject}
        onRevisionChange={loadRevision}
        onNewProject={startNewProject}
        onSave={saveCurrentRevision}
      />
      <div
        className={cn(
          "grid min-h-0 flex-1 overflow-hidden",
          layoutMode === "default" &&
            "grid-cols-1 md:grid-cols-[1fr_1.2fr_1fr]",
          layoutMode === "code" && "grid-cols-1 md:grid-cols-[2fr_1fr]",
          layoutMode === "mesh" && "grid-cols-1 md:grid-cols-[2fr_1fr]"
        )}
      >
        {layoutMode !== "mesh" && (
          <div className="flex min-h-[200px] flex-col overflow-hidden md:min-h-0">
            <EditorPane
              code={code}
              onCodeChange={(value) => {
                setCode(value);
                setIsDirty(true);
              }}
              onGenerate={handleGenerate}
            />
          </div>
        )}
        {layoutMode !== "code" && (
          <div className="relative min-h-[200px] overflow-hidden md:min-h-0">
            {error && (
              <div className="absolute left-4 right-4 top-4 z-20 flex items-start justify-between gap-3 rounded border border-red-500/50 bg-red-950/80 px-3 py-2 text-sm text-red-200">
                <span className="flex-1">{error}</span>
                <button
                  type="button"
                  onClick={() => {
                    navigator.clipboard.writeText(error);
                  }}
                  className="shrink-0 rounded px-2 py-1 text-xs hover:bg-red-900/50"
                >
                  Copy
                </button>
              </div>
            )}
            <ViewportPane
              glbUrl={glbUrl}
              code={code}
              isLoading={isLoading || isProjectLoading}
              onSelectionChange={(selection) => {
                setSelectedFace(selection);
                setIsDirty(true);
              }}
            />
          </div>
        )}
        <div className="flex min-h-[200px] flex-col overflow-hidden md:min-h-0">
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
    </div>
  );
}
