import { useEffect, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";

const STORAGE_KEY = "rocketry-rail-width";
const MIN_WIDTH = 58;
const MAX_WIDTH = 118;
const DEFAULT_WIDTH = 72;

// Pointer-drag resize for the global navigation rail, with its width
// persisted across restarts.
export function useResizableRail() {
  const [railWidth, setRailWidth] = useState(() => Number(localStorage.getItem(STORAGE_KEY)) || DEFAULT_WIDTH);

  useEffect(() => { localStorage.setItem(STORAGE_KEY, String(railWidth)); }, [railWidth]);

  function beginRailResize(event: ReactPointerEvent<HTMLDivElement>) {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = railWidth;
    const move = (next: PointerEvent) => {
      setRailWidth(Math.max(MIN_WIDTH, Math.min(MAX_WIDTH, startWidth + next.clientX - startX)));
    };
    const stop = () => {
      document.removeEventListener("pointermove", move);
      document.removeEventListener("pointerup", stop);
      document.body.classList.remove("resizing-rail");
    };
    document.body.classList.add("resizing-rail");
    document.addEventListener("pointermove", move);
    document.addEventListener("pointerup", stop);
  }

  return { railWidth, setRailWidth, beginRailResize, minWidth: MIN_WIDTH, maxWidth: MAX_WIDTH, defaultWidth: DEFAULT_WIDTH };
}
