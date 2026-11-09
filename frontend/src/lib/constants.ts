export const MODELS = {
  CLAUDE_SONNET_5_5: "anthropic/claude-sonnet-5.5",
  CLAUDE_OPUS_5_5: "anthropic/claude-opus-5.5",
} as const;

export interface ModelConfig {
  id: string;
  label: string;
  description: string;
  supportsVision: boolean;
  supportsStructuredOutputs: boolean;
}

// Order and default from the live CAD50 comparison in docs/MODEL_EVALUATION.md.
export const MODEL_CONFIGS: ModelConfig[] = [
  {
    id: MODELS.CLAUDE_SONNET_5_5,
    label: "Claude Sonnet 5.5",
    description: "Recommended for everyday CAD work",
    supportsVision: true,
    supportsStructuredOutputs: true,
  },
  {
    id: MODELS.CLAUDE_OPUS_5_5,
    label: "Claude Opus 5.5",
    description: "An alternative for complex designs",
    supportsVision: true,
    supportsStructuredOutputs: true,
  },
];

export const LOCAL_MODEL_CONFIGS: ModelConfig[] = [
  { id: "local/claude", label: "Claude Code · local", description: "Uses your local Claude Code sign-in", supportsVision: true, supportsStructuredOutputs: false },
  { id: "local/codex", label: "Codex · local", description: "Uses your local Codex sign-in", supportsVision: true, supportsStructuredOutputs: false },
];

export const DEFAULT_MODEL = MODELS.CLAUDE_SONNET_5_5;

export function getModelConfig(modelId: string): ModelConfig | undefined {
  return [...MODEL_CONFIGS, ...LOCAL_MODEL_CONFIGS].find((m) => m.id === modelId);
}
