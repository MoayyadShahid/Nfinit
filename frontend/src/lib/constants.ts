export const MODELS = {
  CLAUDE_OPUS_5: "anthropic/claude-opus-5",
  GPT_6_ASTRA_PRO: "openai/gpt-6-astra-pro",
} as const;

export interface ModelConfig {
  id: string;
  label: string;
  supportsVision: boolean;
  supportsStructuredOutputs: boolean;
}

export const MODEL_CONFIGS: ModelConfig[] = [
  {
    id: MODELS.CLAUDE_OPUS_5,
    label: "Claude Opus 5",
    supportsVision: true,
    supportsStructuredOutputs: true,
  },
  {
    id: MODELS.GPT_6_ASTRA_PRO,
    label: "GPT-6 Astra Pro",
    supportsVision: true,
    supportsStructuredOutputs: true,
  },
];

export const DEFAULT_MODEL = MODELS.CLAUDE_OPUS_5;

export function getModelConfig(modelId: string): ModelConfig | undefined {
  return MODEL_CONFIGS.find((m) => m.id === modelId);
}
