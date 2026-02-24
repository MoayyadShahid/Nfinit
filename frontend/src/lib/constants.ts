export const MODELS = {
  DEEPSEEK_V3_2: "deepseek/deepseek-v3.2",
  CLAUDE_OPUS_4_6: "anthropic/claude-opus-4.6",
  MINIMAX_M2_5: "minimax/minimax-2.5",
} as const;

export interface ModelConfig {
  id: string;
  label: string;
  supportsVision: boolean;
  supportsStructuredOutputs: boolean;
}

export const MODEL_CONFIGS: ModelConfig[] = [
  {
    id: MODELS.DEEPSEEK_V3_2,
    label: "DeepSeek V3.2",
    supportsVision: false,
    supportsStructuredOutputs: true,
  },
  {
    id: MODELS.CLAUDE_OPUS_4_6,
    label: "Claude Opus 4.6",
    supportsVision: true,
    supportsStructuredOutputs: true,
  },
  {
    id: MODELS.MINIMAX_M2_5,
    label: "Minimax 2.5",
    supportsVision: false,
    supportsStructuredOutputs: false,
  },
];

export const DEFAULT_MODEL = MODELS.CLAUDE_OPUS_4_6;

export function getModelConfig(modelId: string): ModelConfig | undefined {
  return MODEL_CONFIGS.find((m) => m.id === modelId);
}
