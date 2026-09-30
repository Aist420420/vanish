import { AnimatePresence, motion } from "motion/react";
import { useStore } from "../store";

export function Toasts() {
  const { toasts, dismiss } = useStore();
  return (
    <div className="pointer-events-none fixed right-4 bottom-20 z-50 flex w-[min(360px,calc(100vw-32px))] flex-col gap-2" aria-live="polite">
      <AnimatePresence initial={false}>
        {toasts.map((t) => (
          <motion.button
            key={t.id}
            layout
            initial={{ opacity: 0, y: 16, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, x: 40, transition: { duration: 0.2 } }}
            onClick={() => dismiss(t.id)}
            className={`pointer-events-auto flex items-start gap-3 rounded-2xl border bg-bg-2 p-3.5 text-left shadow-card ${
              t.kind === "error" ? "border-del/60" : t.kind === "info" ? "border-line" : "border-mist/50"
            }`}
          >
            <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-bg-3 text-lg" aria-hidden>
              {t.kind === "error" ? "!" : t.icon}
            </span>
            <span className="min-w-0">
              {t.kind === "achievement" && <span className="block text-[12px] text-mist">Достижение</span>}
              <span className="block font-semibold leading-snug">{t.title}</span>
              {t.text && <span className="block text-[13px] text-muted">{t.text}</span>}
            </span>
          </motion.button>
        ))}
      </AnimatePresence>
    </div>
  );
}
