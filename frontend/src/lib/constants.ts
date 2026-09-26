export const MODELS = {
  CLAUDE_OPUS_5_5: "anthropic/claude-opus-5.5",
  GPT_5_6_SOL: "openai/gpt-5.6-sol",
} as const;

export interface ModelConfig {
  id: string;
  label: string;
  supportsVision: boolean;
  supportsStructuredOutputs: boolean;
}

export const MODEL_CONFIGS: ModelConfig[] = [
  {
    id: MODELS.CLAUDE_OPUS_5_5,
    label: "Claude Opus 5.5",
    supportsVision: true,
    supportsStructuredOutputs: true,
  },
  {
    id: MODELS.GPT_5_6_SOL,
    label: "GPT-5.6 Sol",
    supportsVision: true,
    supportsStructuredOutputs: true,
  },
];

export const DEFAULT_MODEL = MODELS.CLAUDE_OPUS_5_5;

export function getModelConfig(modelId: string): ModelConfig | undefined {
  return MODEL_CONFIGS.find((m) => m.id === modelId);
}
