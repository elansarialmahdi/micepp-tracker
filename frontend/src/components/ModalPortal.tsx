import { createPortal } from "react-dom";

export function ModalPortal({ children }: { children: React.ReactNode }) {
  return createPortal(children, document.body);
}
