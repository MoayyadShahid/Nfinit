/**
 * Export choices. The "for printing" entries are turned to the orientation
 * with the least overhang and set on the bed, ready to slice.
 */
export const EXPORT_FORMATS = [
  { id: "stl-print", format: "stl", printReady: true, label: "STL for printing", ext: ".stl", desc: "Laid flat on the bed, for any slicer" },
  { id: "3mf-print", format: "3mf", printReady: true, label: "3MF for printing", ext: ".3mf", desc: "Laid flat, with units: Bambu Studio, PrusaSlicer, Orca" },
  { id: "step", format: "step", printReady: false, label: "STEP", ext: ".step", desc: "CAD (Fusion, SolidWorks, Onshape)" },
  { id: "stl", format: "stl", printReady: false, label: "STL as modelled", ext: ".stl", desc: "Mesh in the model's own position" },
  { id: "obj", format: "obj", printReady: false, label: "OBJ", ext: ".obj", desc: "Rendering and game engines" },
  { id: "brep", format: "brep", printReady: false, label: "BREP", ext: ".brep", desc: "OpenCASCADE tools" },
] as const;

export type ExportFormat = (typeof EXPORT_FORMATS)[number]["id"];

/** A download name from the part's name, e.g. "cable-bracket-print.stl". */
export function exportFileName(partName: string, id: ExportFormat): string {
  const choice = EXPORT_FORMATS.find((item) => item.id === id)!;
  const slug = partName
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 60);
  return `${slug || "part"}${choice.printReady ? "-print" : ""}${choice.ext}`;
}
