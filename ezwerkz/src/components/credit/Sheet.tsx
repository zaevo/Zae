"use client";

import { useEffect, useId, useRef, type ReactNode } from "react";
import { X } from "lucide-react";

/**
 * Bottom sheet on mobile, centered dialog on larger screens. Built on the
 * native <dialog> so focus trapping, Escape and the inert background come
 * from the browser.
 */
export function Sheet({
  open,
  onClose,
  title,
  description,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: ReactNode;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const descId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      aria-describedby={description ? descId : undefined}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      onClick={(e) => {
        // A click on the dialog element itself (not its content) is a click on the backdrop.
        if (e.target === e.currentTarget) onClose();
      }}
      className="fixed inset-x-0 bottom-0 top-auto m-0 w-full max-w-none rounded-t-[var(--radius-card)] border border-line bg-surface p-0 text-ink shadow-2xl backdrop:bg-canvas/70 backdrop:backdrop-blur-sm open:animate-sheet-up md:inset-0 md:m-auto md:h-fit md:max-w-md md:rounded-[var(--radius-card)]"
    >
      {open ? (
        <div className="max-h-[85dvh] overflow-y-auto px-5 pb-[max(env(safe-area-inset-bottom),1.25rem)] pt-3">
          <div className="mx-auto mb-3 h-1 w-10 rounded-full bg-line md:hidden" aria-hidden />
          <div className="flex items-start justify-between gap-4">
            <div>
              <h2 id={titleId} className="text-lg font-semibold tracking-tight">
                {title}
              </h2>
              {description ? (
                <div id={descId} className="mt-0.5 text-sm text-muted">
                  {description}
                </div>
              ) : null}
            </div>
            <button
              type="button"
              onClick={onClose}
              className="-mr-1 rounded-full p-1.5 text-muted transition hover:bg-surface-2 hover:text-ink focus-visible:outline-2 focus-visible:outline-accent"
              aria-label="Close"
            >
              <X size={18} aria-hidden />
            </button>
          </div>
          <div className="mt-4">{children}</div>
        </div>
      ) : null}
    </dialog>
  );
}
