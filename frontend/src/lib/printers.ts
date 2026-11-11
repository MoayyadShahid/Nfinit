/**
 * Printers the printability check knows. The backend holds each one's build
 * volume (PRINTER_PRESETS in backend/execution/runner.py); a test keeps the
 * two lists in step.
 */
export const PRINTERS = [
  { id: "generic", label: "Generic FDM printer" },
  { id: "flashforge_adventurer_3", label: "Flashforge Adventurer 3" },
  { id: "bambu_a1", label: "Bambu Lab A1" },
  { id: "bambu_a1_mini", label: "Bambu Lab A1 mini" },
  { id: "bambu_p1s", label: "Bambu Lab P1S / X1C" },
  { id: "prusa_mk4", label: "Prusa MK4" },
  { id: "prusa_mini", label: "Prusa MINI" },
  { id: "creality_ender_3", label: "Creality Ender-3 V2" },
] as const;

export type PrinterId = (typeof PRINTERS)[number]["id"];

export const PRINTER_KEY = "nfinit:printer";

export function readPrinter(): PrinterId {
  try {
    const saved = window.localStorage.getItem(PRINTER_KEY);
    if (PRINTERS.some((printer) => printer.id === saved)) return saved as PrinterId;
  } catch {
    /* storage can be unavailable; use the generic profile */
  }
  return "generic";
}
