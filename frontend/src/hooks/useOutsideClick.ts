import { useEffect, type RefObject } from "react";

export function useOutsideClick<T extends HTMLElement>(
  ref: RefObject<T | null>,
  active: boolean,
  onOutside: () => void,
): void {
  useEffect(() => {
    if (!active) return;
    const handlePointerDown = (event: PointerEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node))
        onOutside();
    };
    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, [active, onOutside, ref]);
}
