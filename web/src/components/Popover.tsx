import { AnimatePresence, motion } from "motion/react";
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import { createPortal } from "react-dom";

const GAP = 6;
const MARGIN = 8;

/**
 * Всплывающее окно у кнопки: рисуется в body (не обрезается контейнерами с overflow),
 * открывается вверх, если снизу нет места, при прокрутке и ресайзе едет вместе с кнопкой,
 * закрывается кликом мимо и Escape.
 */
export function Popover({ anchor, open, onClose, align = "left", children, className = "" }: {
  anchor: RefObject<HTMLElement | null>;
  open: boolean;
  onClose: () => void;
  align?: "left" | "right";
  children: ReactNode;
  className?: string;
}) {
  const panel = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ top: number; left: number; up: boolean } | null>(null);

  const place = useCallback(() => {
    const a = anchor.current?.getBoundingClientRect();
    const p = panel.current;
    if (!a || !p) return;
    const w = p.offsetWidth;
    const h = p.offsetHeight;
    const up = a.bottom + GAP + h > window.innerHeight - MARGIN && a.top - GAP - h > MARGIN;
    let left = align === "right" ? a.right - w : a.left;
    left = Math.max(MARGIN, Math.min(left, window.innerWidth - w - MARGIN));
    setPos({ top: up ? a.top - GAP - h : a.bottom + GAP, left, up });
  }, [anchor, align]);

  useLayoutEffect(() => {
    if (open) place();
    else setPos(null);
  }, [open, place]);

  useEffect(() => {
    if (!open) return;
    const outside = (e: PointerEvent) => {
      const t = e.target as Node;
      if (panel.current?.contains(t) || anchor.current?.contains(t)) return;
      onClose();
    };
    // Не закрываемся от прокрутки: после колёсика браузер ещё долю секунды шлёт события плавной
    // прокрутки, и меню, открытое сразу после неё, тут же закрылось бы.
    let frame = 0;
    const follow = (e: Event) => {
      if (panel.current?.contains(e.target as Node)) return;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(place);
    };
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
        anchor.current?.focus();
      }
    };
    document.addEventListener("pointerdown", outside, true);
    window.addEventListener("scroll", follow, true);
    window.addEventListener("resize", follow);
    window.addEventListener("keydown", key, true);
    return () => {
      document.removeEventListener("pointerdown", outside, true);
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", follow, true);
      window.removeEventListener("resize", follow);
      window.removeEventListener("keydown", key, true);
    };
  }, [open, onClose, anchor, place]);

  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          ref={panel}
          initial={{ opacity: 0, y: pos?.up ? 4 : -4, scale: 0.98 }}
          animate={{ opacity: pos ? 1 : 0, y: 0, scale: 1 }}
          exit={{ opacity: 0, scale: 0.98, transition: { duration: 0.1 } }}
          transition={{ duration: 0.14, ease: "easeOut" }}
          className={`fixed z-[60] rounded-xl border border-line bg-bg-2 p-1 shadow-card ${className}`}
          style={{ top: pos?.top ?? -9999, left: pos?.left ?? -9999, transformOrigin: pos?.up ? "bottom" : "top" }}
        >
          {children}
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
