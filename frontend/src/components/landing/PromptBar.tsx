"use client";

import { DEMO_ONLY, RUN_LOCALLY_URL } from "@/lib/site";
import { ArrowUp } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { useInView, usePrefersReducedMotion } from "./useInView";

const EXAMPLES = [
  "a wall mount for a 40 mm fan, M3 screws",
  "a snap-fit lid for a Raspberry Pi 5 case",
  "a cable clip for a 6 mm desk edge",
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

/**
 * The hero control (spec §6). Submitting opens the studio with the prompt.
 * On the public demo site there is no studio to build in, so it opens the
 * guide to running Nfinit locally.
 */
export function PromptBar({ className = "" }: { className?: string }) {
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

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (submitting) return;
    const prompt = value.trim();
    if (!prompt) {
      inputRef.current?.focus();
      return;
    }
    setSubmitting(true);
    if (DEMO_ONLY) {
      window.location.assign(RUN_LOCALLY_URL);
      return;
    }
    router.push(`/studio?prompt=${encodeURIComponent(prompt)}`);
  };

  return (
    <div className={className}>
      <form
        ref={formRef}
        className="wb-prompt"
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
      {DEMO_ONLY && (
        <p className="type-caption mt-3.5">
          This website is a demo. Nfinit runs on your computer with your Claude
          Code or Codex login, so your prompt opens the setup guide.{" "}
          <a href="/studio" className="underline underline-offset-4">
            Watch a demo part
          </a>
          .
        </p>
      )}
    </div>
  );
}
