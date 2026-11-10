import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Shared UI hooks. Extracted so each behavior has exactly one implementation:
 * - useDialogFocus: focus trap + initial focus + focus restore for modal dialogs
 *   (PermissionDialog was the reference implementation; the other dialogs reuse it).
 * - useCopyToClipboard: clipboard write with auto-reset "copied" flag; the reset
 *   timer is cleaned up on unmount.
 * - useDismissable: outside pointerdown + Escape close for pickers/drawers.
 *   onClose is kept in a ref so callers may pass inline closures.
 */

type RefLike<T extends HTMLElement = HTMLElement> = { current: T | null };

export function useDialogFocus(
  dialogRef: RefLike<HTMLElement>,
  active: boolean,
  initialFocus?: RefLike<HTMLElement>
) {
  const restoreRef = useRef<HTMLElement | null>(null);
  useEffect(() => {
    if (!active) return;
    restoreRef.current = document.activeElement as HTMLElement | null;
    (initialFocus?.current ?? dialogRef.current)?.focus();
    const dialog = dialogRef.current;
    if (!dialog) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Tab") return;
      const focusables = dialog.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      );
      if (!focusables.length) return;
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };
    dialog.addEventListener("keydown", onKeyDown);
    return () => {
      dialog.removeEventListener("keydown", onKeyDown);
      restoreRef.current?.focus?.();
    };
  }, [active, dialogRef, initialFocus]);
}

export function useCopyToClipboard(resetMs = 1400) {
  const [copied, setCopied] = useState(false);
  const timerRef = useRef<number | null>(null);
  useEffect(
    () => () => {
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    },
    []
  );
  const copy = useCallback(
    async (text: string) => {
      try {
        await navigator.clipboard.writeText(text);
      } catch {
        return false;
      }
      setCopied(true);
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
      timerRef.current = window.setTimeout(() => setCopied(false), resetMs);
      return true;
    },
    [resetMs]
  );
  return [copied, copy] as const;
}

export function useDismissable(
  ref: RefLike<HTMLElement>,
  open: boolean,
  onClose: () => void
) {
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target as Node | null;
      if (ref.current && target && !ref.current.contains(target)) {
        onCloseRef.current();
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCloseRef.current();
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [ref, open]);
}
