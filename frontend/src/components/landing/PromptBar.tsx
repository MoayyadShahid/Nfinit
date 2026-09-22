"use client";

import { getSupabaseBrowserClient } from "@/lib/supabase/browser";
import { ArrowUp } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { useInView, usePrefersReducedMotion } from "./useInView";

const EXAMPLES = [
  "a wall mount for a 40 mm fan, M3 screws",
  "a snap-fit lid for a Raspberry Pi 5 case",
  "a cable clip for a 6 mm desk edge",
];

const CHIPS: { label: string; prompt: string }[] = [
  { label: "fan mount", prompt: EXAMPLES[0] },
  { label: "cable clip", prompt: EXAMPLES[2] },
  { label: "pi case", prompt: EXAMPLES[1] },
];

const TYPE_MS = 38;
const HOLD_MS = 2200;
const DELETE_MS = 16;

/** Types, holds and deletes the example prompts (spec §9.4). */
function useTypewriter(running: boolean) {
  const [text, setText] = useState("");
  const [index, setIndex] = useState(0);
  const phase = useRef<"typing" | "holding" | "deleting">("typing");

  useEffect(() => {
    if (!running) return;
    const target = EXAMPLES[index];
    let delay = TYPE_MS;
    let step: () => void;

    if (phase.current === "typing") {
      if (text.length < target.length) {
        step = () => setText(target.slice(0, text.length + 1));
      } else {
        delay = HOLD_MS;
        step = () => {
          phase.current = "deleting";
          setText(target.slice(0, -1));
        };
      }
    } else if (text.length > 0) {
      delay = DELETE_MS;
      step = () => setText(text.slice(0, -1));
    } else {
      step = () => {
        phase.current = "typing";
        setIndex((index + 1) % EXAMPLES.length);
      };
    }

    const timer = window.setTimeout(step, delay);
    return () => window.clearTimeout(timer);
  }, [running, text, index]);

  return text;
}

async function isSignedOut(): Promise<boolean> {
  const supabase = getSupabaseBrowserClient();
  if (!supabase) return false; // Auth disabled: the studio is open.
  const { data } = await supabase.auth.getSession();
  return !data.session;
}

/**
 * The hero control (spec §6). Submitting opens the studio with the prompt,
 * or sends a signed-out visitor through /login with the prompt kept in `next`.
 */
export function PromptBar({
  className = "",
  centered = false,
}: {
  className?: string;
  centered?: boolean;
}) {
  const router = useRouter();
  const inputId = useId();
  const formRef = useRef<HTMLFormElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const onScreen = useInView(formRef, { threshold: 0, once: false });
  const reducedMotion = usePrefersReducedMotion();
  const [value, setValue] = useState("");
  const [focused, setFocused] = useState(false);
  const [hovered, setHovered] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const animate = onScreen && !reducedMotion && !focused && !hovered && !value;
  const typed = useTypewriter(animate);
  const ghost = reducedMotion || !typed ? EXAMPLES[0] : typed;
  const showGhost = !value && !focused;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (submitting) return;
    const prompt = value.trim();
    if (!prompt) {
      inputRef.current?.focus();
      return;
    }
    setSubmitting(true);
    const studioPath = `/studio?prompt=${encodeURIComponent(prompt)}`;
    const destination = (await isSignedOut())
      ? `/login?next=${encodeURIComponent(studioPath)}`
      : studioPath;
    router.push(destination);
  };

  return (
    <div className={className}>
      <form
        ref={formRef}
        className={`wb-prompt ${centered ? "mx-auto" : ""}`}
        onSubmit={submit}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
      >
        <label htmlFor={inputId} className="sr-only">
          Describe a part
        </label>
        <div className="wb-prompt-field">
          <input
            ref={inputRef}
            id={inputId}
            type="text"
            value={value}
            autoComplete="off"
            enterKeyHint="go"
            maxLength={500}
            placeholder={focused ? EXAMPLES[0] : ""}
            onChange={(event) => setValue(event.target.value)}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
          />
          {showGhost && (
            <span className="wb-prompt-ghost" aria-hidden="true">
              <span className="wb-prompt-ghost-text">{ghost}</span>
              <span className="wb-caret" />
            </span>
          )}
        </div>
        <button
          type="submit"
          className="wb-submit"
          aria-label="Start this part"
          aria-busy={submitting}
        >
          <ArrowUp className="size-4" strokeWidth={2.4} />
        </button>
      </form>
      <div
        className={`mt-3.5 flex flex-wrap gap-2 ${centered ? "justify-center" : ""}`}
      >
        {CHIPS.map((chip) => (
          <button
            key={chip.label}
            type="button"
            className="wb-chip"
            aria-pressed={value === chip.prompt}
            onClick={() => {
              setValue(chip.prompt);
              inputRef.current?.focus();
            }}
          >
            {chip.label}
          </button>
        ))}
      </div>
    </div>
  );
}
