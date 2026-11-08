export const EXPORT_FORMATS = [
  { id: "step", label: "STEP", ext: ".step", desc: "CAD (Fusion, SolidWorks, Onshape)" },
  { id: "brep", label: "BREP", ext: ".brep", desc: "OpenCASCADE tools" },
  { id: "stl", label: "STL", ext: ".stl", desc: "3D printing" },
] as const;

export type ExportFormat = (typeof EXPORT_FORMATS)[number]["id"];
