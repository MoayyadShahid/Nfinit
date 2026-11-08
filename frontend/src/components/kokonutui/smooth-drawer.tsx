"use client";

/** Adapted from Kokonut UI Smooth Drawer (MIT). See LICENSE.md.
 * Export sheet: no checkout demo, payment calls, or simulated confirmation.
 */
import { Download } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Drawer, DrawerClose, DrawerContent, DrawerDescription, DrawerFooter, DrawerHeader, DrawerTitle, DrawerTrigger } from "@/components/ui/drawer";
import { EXPORT_FORMATS, type ExportFormat } from "@/lib/exports";

export default function SmoothDrawer({ onExport, disabled }: {
  onExport: (format: ExportFormat) => void;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  return (
    <Drawer open={open} onOpenChange={setOpen} shouldScaleBackground={false}>
      <DrawerTrigger asChild>
        <Button size="icon" disabled={disabled} aria-label="Export part"><Download /></Button>
      </DrawerTrigger>
      <DrawerContent>
        <DrawerHeader>
          <DrawerTitle>Export your part</DrawerTitle>
          <DrawerDescription>Choose a format for your next step.</DrawerDescription>
        </DrawerHeader>
        <div className="flex flex-col gap-2 overflow-y-auto overscroll-contain px-4">
          {EXPORT_FORMATS.map(({ id, label, ext, desc }) => (
            <Button key={id} variant="outline" className="h-auto min-h-16 justify-start px-4 py-3" disabled={disabled} onClick={() => {
              setOpen(false);
              onExport(id);
            }}>
              <Download data-icon="inline-start" />
              <span className="flex flex-col items-start gap-1">
                <span>{label} <span className="font-mono text-xs text-muted-foreground">{ext}</span></span>
                <span className="text-xs font-normal text-muted-foreground">{desc}</span>
              </span>
            </Button>
          ))}
        </div>
        <DrawerFooter className="pb-[max(1rem,env(safe-area-inset-bottom))]">
          <DrawerClose asChild><Button variant="ghost">Cancel</Button></DrawerClose>
        </DrawerFooter>
      </DrawerContent>
    </Drawer>
  );
}
