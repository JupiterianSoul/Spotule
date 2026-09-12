"use client";
import { cn } from "@/lib/utils";

/**
 * The whole row is one button.
 *
 * It used to be a <button> nested inside a <label>. A label forwards clicks to the labelable
 * control it contains, and <button> is labelable, so clicking the row fired onChange twice:
 * once from the forwarded click and once from the real one. The toggle flipped on and
 * immediately back off, which looked like nothing happening at all. Clicking the small switch
 * itself worked, so the failure depended on exactly where you clicked.
 *
 * One element with one handler cannot have that problem, and role="switch" keeps it announced
 * correctly to screen readers.
 */
export function Toggle({
  checked,
  onChange,
  label,
  disabled,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        "flex w-full items-center justify-between gap-4 py-2 text-left",
        disabled ? "cursor-not-allowed opacity-50" : "cursor-pointer",
      )}
    >
      <span className="text-sm">{label}</span>
      <span
        aria-hidden
        className={cn(
          "relative h-6 w-11 shrink-0 rounded-full transition-colors",
          checked ? "bg-accent" : "bg-surface-2",
        )}
      >
        <span
          className={cn(
            "absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform",
            checked ? "left-[22px]" : "left-0.5",
          )}
        />
      </span>
    </button>
  );
}
