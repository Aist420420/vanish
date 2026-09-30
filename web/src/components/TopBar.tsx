import { motion } from "motion/react";
import { fmt, isDeleteOpen, isTracked, plural } from "../lib";
import { useStore } from "../store";

export type View = "sort" | "delete" | "unsub" | "dash";

const TICKS = 48;

export function TopBar({ view, onView, theme, onTheme }: {
  view: View;
  onView: (v: View) => void;
  theme: "dark" | "light";
  onTheme: () => void;
}) {
  const { state } = useStore();
  if (!state) return null;
  const { game, services } = state;
  const tracked = services.filter(isTracked);
  const counts: Record<View, number> = {
    sort: tracked.filter((s) => s.decision === null).length,
    delete: services.filter(isDeleteOpen).length,
    unsub: services.filter((s) => s.decision === "unsubscribe" && !s.unsub_done).length,
    dash: 0,
  };
  const tabs: [View, string][] = [
    ["sort", "Сортировка"],
    ["delete", "Удаление"],
    ["unsub", "Отписка"],
    ["dash", "Обзор"],
  ];
  const span = game.xp_next ? game.xp_next - game.xp_start : 1;
  const levelPct = game.xp_next ? Math.min(100, ((game.xp - game.xp_start) / span) * 100) : 100;
  const filled = Math.round((game.progress / 100) * TICKS);

  return (
    <header className="border-b border-line/70 bg-bg/90 backdrop-blur supports-[backdrop-filter]:bg-bg/75 sticky top-0 z-30">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-3 px-4 pt-3 sm:px-6">
        <a href="#sort" onClick={() => onView("sort")} className="font-display text-lg font-semibold tracking-tight">
          <span className="text-mist">V</span>anish
        </a>
        <nav className="no-scrollbar order-3 -mx-1 flex w-full gap-1 overflow-x-auto sm:order-none sm:w-auto sm:overflow-visible" aria-label="Режимы">
          {tabs.map(([id, label]) => (
            <a
              key={id}
              href={`#${id}`}
              onClick={() => onView(id)}
              aria-current={view === id ? "page" : undefined}
              className={`relative whitespace-nowrap rounded-lg px-3 py-1.5 text-[14px] transition-colors ${
                view === id ? "text-text" : "text-muted hover:text-text"
              }`}
            >
              {view === id && (
                <motion.span layoutId="tab" className="absolute inset-0 rounded-lg bg-bg-3" transition={{ type: "spring", bounce: 0.2, duration: 0.4 }} />
              )}
              <span className="relative">
                {label}
                {counts[id] > 0 && <span className="ml-1.5 text-faint tabular">{fmt(counts[id])}</span>}
              </span>
            </a>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-4">
          <div className="hidden text-right sm:block" title={`${fmt(game.xp)} XP${game.next_name ? ` · до уровня «${game.next_name}» ${fmt((game.xp_next ?? 0) - game.xp)} XP` : ""}`}>
            <div className="flex items-center justify-end gap-2 text-[13px] leading-tight">
              <span className="rounded-md border border-line px-1.5 py-px text-[11px] text-faint tabular">ур. {game.level}</span>
              <span className="font-medium">{game.name}</span>
            </div>
            <div className="mt-1 ml-auto h-1 w-40 overflow-hidden rounded-full bg-line">
              <motion.div className="h-full rounded-full bg-mist" animate={{ width: `${levelPct}%` }} transition={{ type: "spring", bounce: 0, duration: 0.6 }} />
            </div>
          </div>
          <div className="flex items-center gap-3 text-[13px] text-muted tabular">
            <span title="Дней подряд">
              <span aria-hidden>🔥</span> {game.streak}
            </span>
            <span title="Действий сегодня">
              <span aria-hidden>☀</span> {game.today}
            </span>
          </div>
          <button
            onClick={onTheme}
            className="rounded-lg px-2 py-1 text-muted hover:text-text"
            aria-label={theme === "dark" ? "Светлая тема" : "Тёмная тема"}
            title={theme === "dark" ? "Светлая тема" : "Тёмная тема"}
          >
            {theme === "dark" ? "☾" : "☀"}
          </button>
        </div>
      </div>
      <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-4 gap-y-2 px-4 pt-3 pb-3 sm:px-6">
        <p className="shrink-0 text-[14px] text-muted">
          Цифровой след очищен на{" "}
          <span className="font-display text-[17px] font-semibold text-text tabular">{String(game.progress).replace(".", ",")}%</span>
        </p>
        <div
          className="flex h-2.5 min-w-40 flex-1 items-center gap-[2px] sm:gap-[3px]"
          role="progressbar"
          aria-valuenow={game.progress}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="Цифровой след очищен"
        >
          {Array.from({ length: TICKS }, (_, i) => (
            <span
              key={i}
              className="h-full flex-1 rounded-full transition-[background-color,opacity] duration-500"
              style={{
                background: i < filled ? "var(--mist)" : "var(--line)",
                opacity: i < filled ? 0.35 + 0.65 * ((i + 1) / Math.max(filled, 1)) : 1,
                transitionDelay: `${(i % 12) * 12}ms`,
              }}
            />
          ))}
        </div>
        {game.risk.high_total > 0 && (
          <a
            href="#dash"
            onClick={() => onView("dash")}
            className="shrink-0 text-[13px] tabular hover:underline"
            style={{ color: game.risk.high_open ? "var(--risk-high)" : "var(--keep)" }}
            title={`Индекс риска ${game.risk.index} из 100`}
          >
            {game.risk.high_open
              ? `Высокий риск: ${fmt(game.risk.high_open)} ${plural(game.risk.high_open, "аккаунт", "аккаунта", "аккаунтов")}`
              : "Высокий риск закрыт ✓"}
          </a>
        )}
      </div>
    </header>
  );
}
