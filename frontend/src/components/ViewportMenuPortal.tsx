import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from "react";
import { createPortal } from "react-dom";

type ViewportMenuPortalProps = {
  anchorRef: RefObject<HTMLElement | null>;
  children: ReactNode;
  className?: string;
  ariaLabel?: string;
  id?: string;
  matchAnchorWidth?: boolean;
  onRequestClose: () => void;
  role?: "menu" | "listbox";
};

export function ViewportMenuPortal({
  anchorRef,
  children,
  className = "",
  ariaLabel,
  id,
  matchAnchorWidth = false,
  onRequestClose,
  role = "menu",
}: ViewportMenuPortalProps) {
  const menuRef = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState({
    left: 0,
    top: 0,
    ready: false,
    submenuSide: "right" as "left" | "right",
    width: undefined as number | undefined,
  });

  useLayoutEffect(() => {
    function updatePosition() {
      const anchor = anchorRef.current;
      const menu = menuRef.current;
      if (!anchor || !menu) return;

      const edge = 8;
      const gap = 5;
      const anchorRect = anchor.getBoundingClientRect();
      const targetWidth = matchAnchorWidth ? anchorRect.width : undefined;
      if (targetWidth) menu.style.width = `${targetWidth}px`;
      const menuRect = menu.getBoundingClientRect();
      let left = anchorRect.right - menuRect.width;
      let top = anchorRect.bottom + gap;

      left = Math.max(
        edge,
        Math.min(left, window.innerWidth - menuRect.width - edge),
      );
      if (top + menuRect.height > window.innerHeight - edge) {
        top = Math.max(edge, anchorRect.top - menuRect.height - gap);
      }

      const roomForSubmenuOnRight =
        left + menuRect.width * 2 + gap <= window.innerWidth - edge;
      setPosition({
        left,
        top,
        ready: true,
        submenuSide: roomForSubmenuOnRight ? "right" : "left",
        width: targetWidth,
      });
    }

    updatePosition();
    window.addEventListener("resize", updatePosition);
    window.addEventListener("scroll", updatePosition, true);
    return () => {
      window.removeEventListener("resize", updatePosition);
      window.removeEventListener("scroll", updatePosition, true);
    };
  }, [anchorRef, matchAnchorWidth]);

  useEffect(() => {
    function closeOutside(event: PointerEvent) {
      const target = event.target as Node;
      if (
        !anchorRef.current?.contains(target) &&
        !menuRef.current?.contains(target)
      ) {
        onRequestClose();
      }
    }

    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") onRequestClose();
    }

    document.addEventListener("pointerdown", closeOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [anchorRef, onRequestClose]);

  return createPortal(
    <div
      ref={menuRef}
      id={id}
      className={`viewport-menu ${className}`.trim()}
      role={role}
      aria-label={ariaLabel}
      data-submenu-side={position.submenuSide}
      style={{
        left: position.left,
        top: position.top,
        width: position.width,
        visibility: position.ready ? "visible" : "hidden",
      }}
    >
      {children}
    </div>,
    document.body,
  );
}
