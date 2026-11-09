"use client";

/** Adapted from Kokonut UI AI Model Selector (MIT). See LICENSE.md. */
import { Check, ChevronDown, Sparkles } from "lucide-react";
import { RadioGroup } from "radix-ui";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { getModelConfig, MODEL_CONFIGS, type ModelConfig } from "@/lib/constants";

export type ModelOption = ModelConfig & { disabled?: boolean };

/** Models come only from the app allowlist. The backend owns reasoning effort. */
export default function AIModelSelector({ value, options = MODEL_CONFIGS, onChange, disabled = false }: {
  value: string;
  options?: readonly ModelOption[];
  onChange: (modelId: string) => void;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const model = getModelConfig(value);
  return (
    <Popover open={open && !disabled} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="xs" disabled={disabled} aria-label={`Generation model: ${model?.label ?? "Choose model"}`}>
          <Sparkles data-icon="inline-start" />
          {model?.label ?? "Choose model"}
          <ChevronDown data-icon="inline-end" />
        </Button>
      </PopoverTrigger>
      <PopoverContent side="top" align="start" className="max-w-[calc(100vw-2rem)] p-1.5" aria-label="Choose generation model">
        <p className="px-2.5 pb-2 pt-1 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">Generation model</p>
        <RadioGroup.Root
          aria-label="Generation model"
          value={value}
          disabled={disabled}
          onValueChange={(id) => {
            const option = options.find((item) => item.id === id);
            if (!disabled && option && !option.disabled && getModelConfig(id)) onChange(id);
          }}
          className="flex flex-col gap-1"
        >
          {options.map((option) => (
            <RadioGroup.Item
              key={option.id}
              value={option.id}
              disabled={option.disabled}
              onClick={(event) => {
                // Radix also clicks a radio when arrow keys move focus. Keep
                // the picker open for keyboard exploration of both models.
                if (event.detail > 0) setOpen(false);
              }}
              className="flex min-h-14 w-full items-center gap-3 rounded-lg px-2.5 py-2 text-left outline-none hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring data-[state=checked]:bg-accent disabled:cursor-not-allowed disabled:opacity-40"
            >
              <span className="min-w-0 flex-1">
                <span className="block text-xs font-medium">{option.label}</span>
                <span className="mt-0.5 block text-[11px] leading-4 text-muted-foreground">{option.description}</span>
              </span>
              <RadioGroup.Indicator><Check aria-hidden="true" className="size-3.5" /></RadioGroup.Indicator>
            </RadioGroup.Item>
          ))}
        </RadioGroup.Root>
      </PopoverContent>
    </Popover>
  );
}
