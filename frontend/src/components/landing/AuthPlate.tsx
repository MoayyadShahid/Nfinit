"use client";

import { AUTH_ERROR_EVENT } from "@/components/LoginButtons";
import { useEffect, useState, type ComponentProps } from "react";
import { Plate } from "./Plate";

/** The auth page's plate. A failed sign-in leaves the part half-printed. */
export function AuthPlate({
  halted: initiallyHalted = false,
  ...props
}: ComponentProps<typeof Plate>) {
  const [halted, setHalted] = useState(initiallyHalted);

  useEffect(() => {
    const halt = () => setHalted(true);
    window.addEventListener(AUTH_ERROR_EVENT, halt);
    return () => window.removeEventListener(AUTH_ERROR_EVENT, halt);
  }, []);

  return <Plate {...props} halted={halted} />;
}
