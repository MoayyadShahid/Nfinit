"use client";

/** Adapted from Kokonut UI Command Palette (MIT). See LICENSE.md.
 * Radix/cmdk own focus trapping, keyboard navigation, filtering and dismissal.
 */
import type { LucideIcon } from "lucide-react";
import { useEffect } from "react";
import { CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";

export interface StudioCommand {
  id: string;
  label: string;
  group: string;
  icon: LucideIcon;
  keywords?: string[];
  disabled?: boolean;
  onSelect: () => void | Promise<void>;
}

export default function ActionSearchBar({ open, onOpenChange, commands, onError }: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  commands: StudioCommand[];
  onError: (message: string) => void;
}) {
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented || event.isComposing || event.repeat || event.altKey || event.shiftKey || !(event.metaKey || event.ctrlKey) || event.key.toLowerCase() !== "k") return;
      // Let the editor and other open dialogs keep their own shortcuts.
      if (!open && (document.activeElement?.closest(".monaco-editor") || document.querySelector('[role="dialog"], [role="alertdialog"]'))) return;
      event.preventDefault();
      onOpenChange(!open);
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [open, onOpenChange]);

  const groups = Array.from(new Set(commands.map((item) => item.group)));
  return (
    <CommandDialog open={open} onOpenChange={onOpenChange} title="Studio commands" description="Search actions, saved parts, and versions. Use arrow keys to select and Enter to run.">
      <CommandInput placeholder="Search actions, parts, or versions…" />
      <CommandList>
        <CommandEmpty>No matching commands.</CommandEmpty>
        {groups.map((group) => (
          <CommandGroup key={group} heading={group}>
            {commands.filter((item) => item.group === group).map((item) => (
              <CommandItem
                key={item.id}
                value={item.id}
                keywords={[item.label, ...(item.keywords ?? [])]}
                disabled={item.disabled}
                onSelect={() => {
                  if (item.disabled) return;
                  onOpenChange(false);
                  // Existing handlers retain paywalls and discard confirmations.
                  Promise.resolve().then(item.onSelect).catch(() => onError("The action could not be completed. Please try again."));
                }}
              >
                <item.icon aria-hidden="true" />
                <span className="min-w-0 truncate">{item.label}</span>
              </CommandItem>
            ))}
          </CommandGroup>
        ))}
      </CommandList>
    </CommandDialog>
  );
}
