import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

type TooltipPlacement = "top" | "bottom" | "left" | "right";

type ActiveTooltip = {
  target: HTMLElement;
  text: string;
  placement: TooltipPlacement;
};

function tooltipTarget(eventTarget: EventTarget | null): HTMLElement | null {
  return eventTarget instanceof Element
    ? eventTarget.closest<HTMLElement>("[data-tooltip]")
    : null;
}

export function ViewportTooltip() {
  const tooltipRef = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState<ActiveTooltip | null>(null);
  const [position, setPosition] = useState({ left: 0, top: 0 });

  useEffect(() => {
    function show(target: HTMLElement | null) {
      const text = target?.dataset.tooltip?.trim();
      if (!target || !text) return;
      const placement = (target.dataset.tooltipPlacement ?? "top") as TooltipPlacement;
      setActive({ target, text, placement });
    }

    function onPointerOver(event: PointerEvent) {
      show(tooltipTarget(event.target));
    }

    function onPointerOut(event: PointerEvent) {
      const current = tooltipTarget(event.target);
      const next = tooltipTarget(event.relatedTarget);
      if (current && current !== next) setActive(null);
    }

    function onFocusIn(event: FocusEvent) {
      show(tooltipTarget(event.target));
    }

    function onFocusOut(event: FocusEvent) {
      const current = tooltipTarget(event.target);
      const next = tooltipTarget(event.relatedTarget);
      if (current && current !== next) setActive(null);
    }

    document.addEventListener("pointerover", onPointerOver);
    document.addEventListener("pointerout", onPointerOut);
    document.addEventListener("focusin", onFocusIn);
    document.addEventListener("focusout", onFocusOut);
    return () => {
      document.removeEventListener("pointerover", onPointerOver);
      document.removeEventListener("pointerout", onPointerOut);
      document.removeEventListener("focusin", onFocusIn);
      document.removeEventListener("focusout", onFocusOut);
    };
  }, []);

  useLayoutEffect(() => {
    if (!active || !tooltipRef.current) return;

    function updatePosition() {
      if (!active || !tooltipRef.current || !active.target.isConnected) {
        setActive(null);
        return;
      }

      const targetRect = active.target.getBoundingClientRect();
      const tooltipRect = tooltipRef.current.getBoundingClientRect();
      const gap = 8;
      const edge = 8;
      let left = targetRect.left + (targetRect.width - tooltipRect.width) / 2;
      let top = targetRect.top - tooltipRect.height - gap;

      if (active.placement === "bottom") top = targetRect.bottom + gap;
      if (active.placement === "left") {
        left = targetRect.left - tooltipRect.width - gap;
        top = targetRect.top + (targetRect.height - tooltipRect.height) / 2;
      }
      if (active.placement === "right") {
        left = targetRect.right + gap;
        top = targetRect.top + (targetRect.height - tooltipRect.height) / 2;
      }

      if (top < edge && active.placement === "top") top = targetRect.bottom + gap;
      if (top + tooltipRect.height > window.innerHeight - edge && active.placement === "bottom") {
        top = targetRect.top - tooltipRect.height - gap;
      }
      if (left < edge && active.placement === "left") left = targetRect.right + gap;
      if (left + tooltipRect.width > window.innerWidth - edge && active.placement === "right") {
        left = targetRect.left - tooltipRect.width - gap;
      }

      setPosition({
        left: Math.max(edge, Math.min(left, window.innerWidth - tooltipRect.width - edge)),
        top: Math.max(edge, Math.min(top, window.innerHeight - tooltipRect.height - edge)),
      });
    }

    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [active]);

  if (!active) return null;

  return createPortal(
    <div
      ref={tooltipRef}
      className="viewport-tooltip"
      role="tooltip"
      style={{ left: position.left, top: position.top }}
    >
      {active.text}
    </div>,
    document.body,
  );
}
