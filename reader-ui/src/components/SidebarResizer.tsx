import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import {
  browserStore,
  clampWidth,
  CSS_VARIABLE,
  DEFAULT_WIDTH,
  desktopStore,
  loadWidth,
  maxWidthFor,
  MIN_WIDTH,
  saveWidth,
  widthForKey,
  type DesktopWidthBridge,
  type WidthStore,
} from "../lib/sidebarWidth";

// The drag handle on the sidebar's right edge. The width lives in a CSS
// variable on the root element, so a drag writes that variable once per
// animation frame and nothing else re-renders; only the handle's own
// state (its aria-valuenow) updates when a drag or key press ends.

/** The desktop app's settings come first when the reader runs inside it:
 * its core listens on a new port each launch, and browser storage is kept
 * per origin, so it would forget the width on every restart. */
function stores(): WidthStore[] {
  const list: WidthStore[] = [];
  const bridge = (window as { kosDesktop?: Partial<DesktopWidthBridge> }).kosDesktop;
  if (typeof bridge?.getSidebarWidth === "function" && typeof bridge.setSidebarWidth === "function") {
    list.push(desktopStore(bridge as DesktopWidthBridge));
  }
  list.push(browserStore(() => window.localStorage));
  return list;
}

/** The width the person chose; what shows can be narrower in a small window. */
let preferred = DEFAULT_WIDTH;

function apply(width: number): void {
  document.documentElement.style.setProperty(CSS_VARIABLE, `${width}px`);
}

/** Before the first render, so the sidebar never jumps from the default. */
export function applyStoredSidebarWidth(): void {
  preferred = loadWidth(stores()) ?? DEFAULT_WIDTH;
  apply(clampWidth(preferred, window.innerWidth));
}

export function SidebarResizer({ label, hint }: { label: string | undefined; hint: string | undefined }) {
  const [width, setWidth] = useState(() => clampWidth(preferred, window.innerWidth));
  const [viewport, setViewport] = useState(() => window.innerWidth);
  const handleRef = useRef<HTMLDivElement>(null);
  const drag = useRef<{ pointer: number; startX: number; startWidth: number; width: number; frame: number } | null>(null);
  const saveTimer = useRef<number | undefined>(undefined);

  useEffect(() => {
    // A narrower window squeezes the sidebar, and a wider one gives back
    // the width the person chose.
    function onResize() {
      const next = clampWidth(preferred, window.innerWidth);
      apply(next);
      setViewport(window.innerWidth);
      setWidth(next);
    }
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      window.clearTimeout(saveTimer.current);
    };
  }, []);

  function commit(next: number) {
    preferred = next;
    apply(next);
    setWidth(next);
    // Written once the person stops, not for every key press.
    window.clearTimeout(saveTimer.current);
    saveTimer.current = window.setTimeout(() => saveWidth(stores(), next), 250);
  }

  function onPointerDown(event: PointerEvent<HTMLDivElement>) {
    if (event.button !== 0) return;
    // No preventDefault: the press itself focuses the handle (so the arrow
    // keys work right after a drag) without the keyboard focus ring, and
    // the root's user-select: none keeps the drag from selecting text.
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = { pointer: event.pointerId, startX: event.clientX, startWidth: width, width, frame: 0 };
    document.documentElement.setAttribute("data-sidebar-resizing", "");
  }

  function onPointerMove(event: PointerEvent<HTMLDivElement>) {
    const state = drag.current;
    if (state === null || state.pointer !== event.pointerId) return;
    const next = clampWidth(state.startWidth + event.clientX - state.startX, window.innerWidth);
    if (next === state.width) return;
    state.width = next;
    if (state.frame) return;
    state.frame = window.requestAnimationFrame(() => {
      state.frame = 0;
      apply(state.width);
      handleRef.current?.setAttribute("aria-valuenow", String(state.width));
    });
  }

  function endDrag() {
    const state = drag.current;
    if (state === null) return;
    drag.current = null;
    window.cancelAnimationFrame(state.frame);
    document.documentElement.removeAttribute("data-sidebar-resizing");
    if (state.width !== state.startWidth) commit(state.width);
    else apply(state.width);
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const next = widthForKey(width, event.key, event.shiftKey, window.innerWidth);
    if (next === null) return;
    event.preventDefault();
    commit(next);
  }

  return (
    <div
      ref={handleRef}
      role="separator"
      aria-orientation="vertical"
      aria-label={label}
      aria-valuenow={width}
      aria-valuemin={MIN_WIDTH}
      aria-valuemax={maxWidthFor(viewport)}
      title={hint}
      tabIndex={0}
      className="kos-resize-handle"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
      onLostPointerCapture={endDrag}
      onDoubleClick={() => commit(clampWidth(DEFAULT_WIDTH, window.innerWidth))}
      onKeyDown={onKeyDown}
      data-testid="sidebar-resizer"
    />
  );
}
