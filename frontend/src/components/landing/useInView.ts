"use client";

import { useEffect, useState, type RefObject } from "react";

/** True while the element is at least `threshold` visible. */
export function useInView(
  ref: RefObject<Element | null>,
  {
    threshold = 0.35,
    once = true,
    rootMargin = "0px",
  }: { threshold?: number; once?: boolean; rootMargin?: string } = {},
) {
  const [inView, setInView] = useState(false);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setInView(true);
          if (once) observer.disconnect();
        } else if (!once) {
          setInView(false);
        }
      },
      { threshold, rootMargin },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, [ref, threshold, once, rootMargin]);

  return inView;
}

/** Live `prefers-reduced-motion: reduce` flag. */
export function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReduced(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  return reduced;
}
