import { useCallback, useEffect, useRef, type RefObject } from "react";

const FOCUSABLE = [
  "a[href]",
  "button:not(:disabled)",
  "input:not(:disabled)",
  "select:not(:disabled)",
  "textarea:not(:disabled)",
  "[tabindex]",
  "[contenteditable='true']",
].join(",");

function focusableIn(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE)).filter(
    (element) => element.tabIndex >= 0 && !element.hidden && !element.closest("[inert]"),
  );
}

function currentFocus(): HTMLElement | null {
  return document.activeElement instanceof HTMLElement && document.activeElement !== document.body
    ? document.activeElement
    : null;
}

/** Keep keyboard focus inside a modal dialog while it is open, and give it
 * back to whatever had it (the button that opened the dialog) on close.
 *
 * Tab and Shift+Tab cycle through the dialog's focusable elements, and
 * anything that moves focus outside (a click on the page behind, a script)
 * hands it back to the dialog. The dialog decides where focus starts.
 *
 * Focus is returned when `open` turns false or the dialog unmounts, unless
 * something outside the dialog has taken focus by then (a page that
 * focuses its own heading after a navigation, say). `restoreFocus` returns
 * it early, for a dialog that must hand focus back before it acts (closing,
 * then navigating). */
export function useDialogFocus(ref: RefObject<HTMLElement | null>, open = true): { restoreFocus: () => void } {
  const openerRef = useRef<HTMLElement | null>(null);
  const wasOpenRef = useRef(false);
  const restoredRef = useRef(false);

  // Read during render, before the dialog's own fields can take focus (an
  // autoFocus input is focused while React commits, ahead of any effect).
  if (open && !wasOpenRef.current) {
    openerRef.current = currentFocus();
    restoredRef.current = false;
  }
  wasOpenRef.current = open;

  const restoreFocus = useCallback(() => {
    if (restoredRef.current) return;
    restoredRef.current = true;
    const opener = openerRef.current;
    openerRef.current = null;
    if (opener?.isConnected) opener.focus();
  }, []);

  useEffect(() => {
    if (!open) return;
    const dialog = ref.current;

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key !== "Tab" || event.defaultPrevented || restoredRef.current || !dialog) return;
      const items = focusableIn(dialog);
      if (items.length === 0) {
        event.preventDefault();
        return;
      }
      const index = items.indexOf(document.activeElement as HTMLElement);
      if (event.shiftKey && index <= 0) {
        event.preventDefault();
        items[items.length - 1].focus();
      } else if (!event.shiftKey && (index === -1 || index === items.length - 1)) {
        event.preventDefault();
        items[0].focus();
      }
    }

    function handleFocusIn(event: FocusEvent) {
      if (restoredRef.current || !dialog || dialog.contains(event.target as Node)) return;
      focusableIn(dialog)[0]?.focus();
    }

    document.addEventListener("keydown", handleKeyDown);
    document.addEventListener("focusin", handleFocusIn);
    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.removeEventListener("focusin", handleFocusIn);
      // Focus was in the dialog (or went to the body as it was removed):
      // hand it back. Anything else took focus on purpose; leave it there.
      const active = currentFocus();
      if (active === null || dialog?.contains(active)) restoreFocus();
      else restoredRef.current = true;
    };
  }, [open, ref, restoreFocus]);

  return { restoreFocus };
}
