import {
  AnimatePresence,
  animate,
  motion,
  useMotionValue,
  useTransform,
  type MotionValue,
  type PanInfo,
  type TargetAndTransition,
} from "motion/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Avatar } from "../components/Avatar";
import { ConfidenceBadge, DifficultyBadge, LeakBadge, RiskBadge } from "../components/Badges";
import { Chevron, Select } from "../components/Dropdown";
import { Popover } from "../components/Popover";
import { celebrate } from "../celebrate";
import {
  bulkTargets,
  DECISION_COLOR,
  DECISION_LABEL,
  fmt,
  fmtDateShort,
  isDeleteOpen,
  isTracked,
  plural,
  SORT_LABEL,
  sortServices,
  STATUS_LABEL,
  topServices,
  type SortOrder,
} from "../lib";
import { useStore } from "../store";
import type { BulkAction, Confidence, Decision, Service, UndoTarget } from "../types";

type ConfFilter = "all" | "high" | "breached" | Confidence;
export type SortMode = "all" | "top";

const FILTERS: [ConfFilter, string][] = [
  ["all", "Без фильтра"],
  ["high", "Только высокий риск"],
  ["breached", "Только из утечек"],
  ["sure", "Только точные аккаунты"],
  ["likely", "Только вероятные"],
  ["newsletter", "Только рассылки"],
];

function matchFilter(s: Service, f: ConfFilter): boolean {
  if (f === "all") return true;
  if (f === "high") return s.risk.level === "high";
  if (f === "breached") return s.risk.breached;
  return s.confidence === f;
}

/** Как карточка покидает колоду: решение (в его сторону), «в колоду» при отмене или просто растворение. */
type Motion = Decision | "stack" | "fade";

// Задние карточки выглядывают из-под передней на STACK_Y (масштаб от нижнего края).
// Новая карточка поднимается из положения первой задней, поэтому смена выглядит бесшовно.
const STACK_Y = 10;
const STACK_SCALE = 0.96;
const FROM_STACK_Y = 20; // та же нижняя кромка, но при масштабе от центра
const OUT_EASE = [0.45, 0, 0.9, 0.55] as const;
const SETTLE = { type: "spring", stiffness: 420, damping: 36, mass: 0.9 } as const;
const RETURN = { type: "spring", stiffness: 240, damping: 26, mass: 0.9 } as const;
const REST = { x: 0, y: 0, scale: 1, opacity: 1, filter: "blur(0px)" };

/** Откуда карточка появляется. При отмене — ровно оттуда, куда ушла. */
function enterFrom(dir: Motion | null): TargetAndTransition {
  switch (dir) {
    case "keep":
      return { x: 640, y: 0, scale: 1, opacity: 0, filter: "blur(0px)" };
    case "delete":
      return { x: -50, y: 0, scale: 0.86, opacity: 0, filter: "blur(18px)" };
    case "unsubscribe":
      return { x: 0, y: 520, scale: 1, opacity: 0, filter: "blur(0px)" };
    case "later":
      return { x: 0, y: -480, scale: 0.92, opacity: 0, filter: "blur(0px)" };
    case "fade":
    case "skip":
    case "stack":
      return { x: 0, y: 0, scale: 0.97, opacity: 0, filter: "blur(0px)" };
    default:
      return { x: 0, y: FROM_STACK_Y, scale: STACK_SCALE, opacity: 0.6, filter: "blur(0px)" };
  }
}

/** Куда карточка уходит. Продолжает движение с той точки, где её отпустили после перетаскивания. */
function exitTo(dir: Motion, x: number, y: number): TargetAndTransition {
  const top = { zIndex: { duration: 0 } };
  switch (dir) {
    case "keep":
      return { x: Math.max(x, 0) + 640, opacity: 0, zIndex: 20, transition: { duration: 0.36, ease: OUT_EASE, ...top } };
    case "delete":
      return {
        x: Math.min(x, 0) - 50, scale: 0.86, opacity: 0, filter: "blur(18px)", zIndex: 20,
        transition: { duration: 0.45, ease: [0.4, 0, 0.2, 1], ...top },
      };
    case "unsubscribe":
      return { y: Math.max(y, 0) + 520, opacity: 0, zIndex: 20, transition: { duration: 0.36, ease: OUT_EASE, ...top } };
    case "later":
      return { y: Math.min(y, 0) - 480, scale: 0.92, opacity: 0, zIndex: 20, transition: { duration: 0.36, ease: OUT_EASE, ...top } };
    case "stack":
      // Отмена: текущая карточка мягко «проседает» обратно в колоду, вернувшаяся ложится сверху.
      return { y: FROM_STACK_Y, scale: STACK_SCALE, opacity: 0, zIndex: 0, transition: { duration: 0.28, ease: "easeOut", ...top } };
    default:
      return { opacity: 0, scale: 0.97, zIndex: 0, transition: { duration: 0.16, ease: "easeOut", ...top } };
  }
}

const ACTIONS: { decision: Decision; key: string; code: string[]; arrow: string; label: string; color: string }[] = [
  { decision: "delete", key: "D", code: ["ArrowLeft", "KeyD"], arrow: "←", label: "Удалить", color: "var(--del)" },
  { decision: "unsubscribe", key: "U", code: ["ArrowDown", "KeyU"], arrow: "↓", label: "Отписаться", color: "var(--unsub)" },
  { decision: "later", key: "S", code: ["ArrowUp", "KeyS"], arrow: "↑", label: "Отложить", color: "var(--later)" },
  { decision: "keep", key: "K", code: ["ArrowRight", "KeyK"], arrow: "→", label: "Оставить", color: "var(--keep)" },
];

function isTyping(e: KeyboardEvent): boolean {
  const t = e.target as HTMLElement | null;
  return !!t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable);
}

export function readPref<T extends string>(key: string, fallback: T): T {
  try {
    return (localStorage.getItem(key) as T) || fallback;
  } catch {
    return fallback;
  }
}

export function writePref(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* настройки вида — не критично */
  }
}

export function SortView({ onGo }: { onGo: (v: "delete" | "dash") => void }) {
  const { state, decide, undo, bulk, canUndo, undoTarget, notify } = useStore();
  const [order, setOrder] = useState<SortOrder>(() => readPref("vanish.order", "risk"));
  const [conf, setConf] = useState<ConfFilter>(() => readPref("vanish.filter", "all"));
  const [mode, setModeState] = useState<SortMode>(() => readPref("vanish.mode", "all"));
  const [laterMode, setLaterMode] = useState(false);
  const [skipped, setSkipped] = useState<Set<string>>(new Set());
  const [pinned, setPinned] = useState<string | null>(null);
  const [exitDir, setExitDir] = useState<Motion>("fade");
  // Как появится следующая карточка: domain = null — любая следующая (смена режима или фильтра).
  const [entry, setEntry] = useState<{ domain: string | null; dir: Motion } | null>(null);
  const reshuffle = () => {
    setExitDir("fade");
    setEntry({ domain: null, dir: "fade" });
  };
  const [dust, setDust] = useState(0);

  const services = state?.services ?? [];
  const tracked = useMemo(() => services.filter(isTracked), [services]);
  const topN = state?.meta.top_n ?? 30;
  const top = useMemo(() => topServices(services, topN), [services, topN]);
  const pool = mode === "top" ? top : tracked;
  const laterCount = pool.filter((s) => s.decision === "later").length;

  const setMode = (m: SortMode) => {
    if (m === mode) return;
    reshuffle();
    setModeState(m);
    writePref("vanish.mode", m);
    setLaterMode(false);
    setSkipped(new Set());
  };

  const queue = useMemo(() => {
    let list = laterMode
      ? pool.filter((s) => s.decision === "later" && !skipped.has(s.domain))
      : pool.filter((s) => s.decision === null);
    if (mode === "all" && conf !== "all") list = list.filter((s) => matchFilter(s, conf));
    list = sortServices(list, mode === "top" ? "risk" : order);
    if (pinned) {
      const i = list.findIndex((s) => s.domain === pinned);
      if (i > 0) list = [list[i], ...list.slice(0, i), ...list.slice(i + 1)];
    }
    return list;
  }, [pool, mode, laterMode, skipped, conf, order, pinned]);

  const current = queue[0];

  // Праздник при опустошении очереди (только если очередь опустела у меня на глазах).
  const prevLen = useRef(queue.length);
  useEffect(() => {
    if (prevLen.current > 0 && queue.length === 0 && pool.length > 0) celebrate("finish");
    prevLen.current = queue.length;
  }, [queue.length, pool.length]);

  const act = (s: Service, decision: Decision) => {
    setExitDir(decision);
    setEntry(null);
    setPinned(null);
    if (decision === "delete") setDust((n) => n + 1);
    if (laterMode && decision === "later") {
      setSkipped((prev) => new Set(prev).add(s.domain));
      return;
    }
    decide(s, decision);
  };

  const doUndo = async () => {
    const t = undoTarget;
    const unskip = (domain: string) =>
      setSkipped((prev) => {
        const next = new Set(prev);
        next.delete(domain);
        return next;
      });
    if (t?.domain && t.before) {
      const svc = services.find((x) => x.domain === t.domain);
      // Z отменяет последнее действие во всём приложении: это может быть «Удалено ✓» на экране удаления
      // или карточка из другого режима. Если после отмены карточки не будет в этой колоде — скажем, что отменили.
      const returns =
        !!svc &&
        pool.some((x) => x.domain === svc.domain) &&
        (laterMode ? t.before.decision === "later" : t.before.decision === null) &&
        (mode !== "all" || matchFilter(svc, conf));
      if (!returns) {
        await undo(true);
        notify({ kind: "info", icon: "↶", title: `Отменено: ${describeUndo(t, svc)}` });
        return;
      }
      // Карточка возвращается сразу и с той стороны, куда её отправили.
      const dir: Motion = svc.decision ?? "fade";
      setExitDir("stack");
      setEntry({ domain: t.domain, dir });
      setPinned(t.domain);
      unskip(t.domain);
      await undo(true);
      return;
    }
    const domain = await undo();
    if (domain) {
      setExitDir("stack");
      setEntry({ domain, dir: "fade" });
      setPinned(domain);
      unskip(domain);
    }
  };

  const actRef = useRef(act);
  actRef.current = act;
  const undoRef = useRef(doUndo);
  undoRef.current = doUndo;
  const currentRef = useRef(current);
  currentRef.current = current;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (isTyping(e) || e.altKey || e.repeat) return;
      if (e.code === "KeyZ") {
        e.preventDefault();
        undoRef.current();
        return;
      }
      if (e.ctrlKey || e.metaKey) return;
      const action = ACTIONS.find((a) => a.code.includes(e.code));
      if (action && currentRef.current) {
        e.preventDefault();
        actRef.current(currentRef.current, action.decision);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (!state) return null;

  if (services.length === 0) return <NoData />;

  const toDelete = services.filter(isDeleteOpen).length;
  const total = pool.length;
  const decided = pool.filter((s) => s.decision && s.decision !== "later").length;

  return (
    <main className="mx-auto flex min-h-[calc(100dvh-94px)] max-w-6xl flex-col px-4 pb-[72px] sm:px-6">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 pt-4 pb-4">
        <ModeSwitch mode={mode} onMode={setMode} topCount={top.length} />
        {laterMode && (
          <button className="text-[14px] text-mist hover:underline" onClick={() => { reshuffle(); setLaterMode(false); setSkipped(new Set()); }}>
            Вернуться к основной очереди
          </button>
        )}
        {mode === "all" && (
          <div className="flex w-full flex-wrap items-center gap-2 md:ml-auto md:w-auto md:justify-end">
            {!laterMode && <BulkMenu services={services} onBulk={bulk} />}
            <Select
              label={<SortIcon />}
              ariaLabel="Порядок"
              value={order}
              onChange={(v) => { reshuffle(); setOrder(v as SortOrder); writePref("vanish.order", v); }}
              options={Object.entries(SORT_LABEL)}
              align="right"
            />
            <Select
              label={<FilterIcon />}
              ariaLabel="Фильтр"
              value={conf}
              onChange={(v) => { reshuffle(); setConf(v as ConfFilter); writePref("vanish.filter", v); }}
              options={FILTERS}
              align="right"
            />
          </div>
        )}
      </div>

      <div className="flex flex-1 flex-col">
        {/* Колода чуть выше центра свободного места; сверху — не меньше 20px от панели. */}
        <div className="min-h-5 flex-[1]" />
        {/* Место под колоду фиксированной высоты: строка прогресса под ней не прыгает от карточки к карточке. */}
        <div className="mx-auto flex min-h-[480px] w-full max-w-[480px] flex-col short:min-h-[425px]">
          <div className={`relative grid grid-cols-[minmax(0,1fr)] items-start ${current ? "" : "my-auto"}`}>
            {queue.slice(1, 3).map((s, i) => {
              const depth = i + 1;
              return (
                <motion.div
                  key={s.domain}
                  aria-hidden
                  className="absolute inset-0 rounded-[26px] border border-line bg-bg-2"
                  style={{ zIndex: 3 - depth, transformOrigin: "50% 100%" }}
                  initial={{ y: (depth + 1) * STACK_Y, scale: 1 - (depth + 1) * 0.04, opacity: 0 }}
                  animate={{ y: depth * STACK_Y, scale: 1 - depth * 0.04, opacity: 1 - depth * 0.3 }}
                  transition={SETTLE}
                />
              );
            })}
            <AnimatePresence custom={exitDir} initial={false}>
              {current ? (
                <SwipeCard
                  key={current.domain}
                  service={current}
                  from={entry && (entry.domain === null || entry.domain === current.domain) ? entry.dir : null}
                  onDecide={(d) => act(current, d)}
                />
              ) : (
                <EmptyQueue
                  key="empty"
                  laterCount={laterMode ? 0 : laterCount}
                  toDelete={toDelete}
                  laterMode={laterMode}
                  topMode={mode === "top"}
                  restCount={tracked.filter((s) => s.decision === null).length}
                  onLater={() => { setLaterMode(true); setSkipped(new Set()); }}
                  onAll={() => setMode("all")}
                  onGo={onGo}
                />
              )}
            </AnimatePresence>
            <Dust trigger={dust} />
          </div>
        </div>

        <div className="mx-auto mt-7 w-full max-w-[480px]">
          {mode === "top" ? (
            <TopProgress services={top} />
          ) : laterMode ? (
            <DeckStatus done={0} total={0} text={<>отложенных осталось <span className="text-muted">{fmt(queue.length)}</span></>} />
          ) : (
            <DeckStatus
              done={decided}
              total={total}
              text={<><span className="text-muted">{fmt(decided)}</span> из {fmt(total)} разобрано</>}
            />
          )}
        </div>
        <div className="flex-[1.6]" />
      </div>

      <HintsBar
        disabled={!current}
        canUndo={canUndo}
        onAction={(d) => current && act(current, d)}
        onUndo={doUndo}
      />
    </main>
  );
}

function SwipeCard({ service, from, onDecide }: { service: Service; from: Motion | null; onDecide: (d: Decision) => void }) {
  const x = useMotionValue(0);
  const y = useMotionValue(0);
  const rotate = useTransform(x, [-320, 320], [-12, 12]);
  const del = useTransform(x, [-140, -30], [1, 0]);
  const keep = useTransform(x, [30, 140], [0, 1]);
  const unsub = useTransform(y, [30, 140], [0, 1]);
  const later = useTransform(y, [-140, -30], [1, 0]);

  const onDragEnd = (_: unknown, info: PanInfo) => {
    const { offset, velocity } = info;
    const horizontal = Math.abs(offset.x) > Math.abs(offset.y);
    const T = 110;
    const V = 650;
    if (horizontal && (offset.x < -T || velocity.x < -V)) return onDecide("delete");
    if (horizontal && (offset.x > T || velocity.x > V)) return onDecide("keep");
    if (!horizontal && (offset.y > T || velocity.y > V)) return onDecide("unsubscribe");
    if (!horizontal && (offset.y < -T || velocity.y < -V)) return onDecide("later");
    animate(x, 0, { type: "spring", stiffness: 500, damping: 30 });
    animate(y, 0, { type: "spring", stiffness: 500, damping: 30 });
  };

  return (
    <motion.article
      className="relative z-10 w-full cursor-grab touch-none rounded-[26px] border border-line bg-bg-2 p-5 shadow-card select-none short:py-4 [grid-area:1/1] active:cursor-grabbing sm:px-6"
      style={{ x, y, rotate }}
      drag
      dragElastic={0.9}
      dragMomentum={false}
      onDragEnd={onDragEnd}
      initial={enterFrom(from)}
      animate={{
        ...REST,
        transition: from && from !== "fade" && from !== "stack" ? RETURN : SETTLE,
        // Размытие нужно только на время анимации: в покое текст остаётся резким.
        transitionEnd: { filter: "none" },
      }}
      variants={{ exit: (dir: Motion) => exitTo(dir, x.get(), y.get()) }}
      exit="exit"
      aria-label={`${service.name}, ${service.domain}`}
    >
      <Stamp opacity={del} color="var(--del)" label="Удалить" className="top-6 right-6 rotate-6" />
      <Stamp opacity={keep} color="var(--keep)" label="Оставить" className="top-6 left-6 -rotate-6" />
      <Stamp opacity={unsub} color="var(--unsub)" label="Отписаться" className="top-6 left-1/2 -translate-x-1/2" />
      <Stamp opacity={later} color="var(--later)" label="Отложить" className="bottom-6 left-1/2 -translate-x-1/2" />
      <CardBody service={service} />
    </motion.article>
  );
}

function Stamp({ opacity, color, label, className }: { opacity: MotionValue<number>; color: string; label: string; className: string }) {
  return (
    <motion.div
      aria-hidden
      className={`pointer-events-none absolute z-20 rounded-xl border-2 px-3 py-1 font-display text-[15px] font-semibold ${className}`}
      style={{ opacity, color, borderColor: color, background: "var(--bg-2)" }}
    >
      {label}
    </motion.div>
  );
}

function CardBody({ service: s }: { service: Service }) {
  const years = s.first_year ? new Date().getFullYear() - s.first_year : null;
  const leak = s.risk.breaches[0];
  return (
    <div className="flex flex-col gap-4 short:gap-3">
      <div className="flex items-center gap-3.5">
        <Avatar service={s} size={52} />
        <div className="min-w-0">
          <h2 className="truncate font-display text-[21px] leading-tight font-semibold">{s.name}</h2>
          <p className="truncate text-muted">
            {s.domain} · {s.risk.category_label}
          </p>
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <RiskBadge risk={s.risk} />
          <LeakBadge risk={s.risk} />
          {/* Про утечку говорит значок рядом — в причинах её не повторяем. */}
          <span className="text-[13px] text-faint">{s.risk.reasons.filter((r) => !r.startsWith("утечка")).join(" · ")}</span>
        </div>
        {leak && (
          <p className="line-clamp-2 text-[13px] leading-snug text-muted">
            Утечка «{leak.title}», {leak.date.slice(0, 4)}: {fmt(leak.pwn_count)} аккаунтов
            {leak.data_ru.length > 0 && ` — ${leak.data_ru.slice(0, 4).join(", ")}`}
            {s.risk.breaches.length > 1 && ` (и ещё ${s.risk.breaches.length - 1})`}.
            {!s.risk.breach_after_signup && " Случилась раньше ваших первых писем — возможно, не задела."}
          </p>
        )}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <ConfidenceBadge confidence={s.confidence} />
          <DifficultyBadge service={s} />
        </div>
      </div>

      <dl className="grid grid-cols-3 gap-3 rounded-2xl bg-bg-3/60 px-4 py-3 short:py-2">
        <div>
          <dt className="text-[13px] text-faint">Писем</dt>
          <dd className="font-display text-[18px] font-semibold tabular">{fmt(s.count)}</dd>
        </div>
        <div>
          <dt className="text-[13px] text-faint">Первое</dt>
          <dd className="flex items-baseline gap-1.5 whitespace-nowrap">
            <span className="font-display text-[18px] font-semibold tabular">{s.first_year ?? "—"}</span>
            {years !== null && years > 0 && (
              <span className="hidden text-[12px] text-muted sm:inline">{years} {plural(years, "год", "года", "лет")}</span>
            )}
          </dd>
        </div>
        <div>
          <dt className="text-[13px] text-faint">Последнее</dt>
          <dd className="pt-1 text-[14px] font-medium whitespace-nowrap">{fmtDateShort(s.last)}</dd>
        </div>
      </dl>

      {s.samples.length > 0 && (
        <div>
          <h3 className="mb-1 text-[13px] text-faint">Темы писем</h3>
          <ul className="flex flex-col gap-0.5">
            {s.samples.slice(0, 3).map((subject, i) => (
              <li key={i} className={`truncate text-[14px] text-muted ${i === 2 ? "short:hidden" : ""}`}>«{subject}»</li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex flex-col gap-1 text-[13px] text-muted">
        <span>{s.has_unsub ? "В письмах есть ссылка «Отписаться»" : "Рассылки без ссылки отписки"}</span>
        {s.google_linked && (
          <a href={s.links.google_connections} target="_blank" rel="noreferrer noopener" className="text-mist hover:underline" onPointerDown={(e) => e.stopPropagation()}>
            Похоже, вход через Google — проверить доступы
          </a>
        )}
      </div>

      <div className="flex flex-wrap gap-2" onPointerDown={(e) => e.stopPropagation()}>
        <ExtLink href={s.links.site}>Сайт</ExtLink>
        <ExtLink href={s.links.gmail}>Письма в Gmail</ExtLink>
        {s.links.delete && <ExtLink href={s.links.delete}>Страница удаления</ExtLink>}
      </div>
    </div>
  );
}

export function ExtLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer noopener"
      className="rounded-lg border border-line px-2.5 py-1 text-[13px] text-muted transition-colors hover:border-mist/60 hover:text-text"
    >
      {children} <span aria-hidden>↗</span>
    </a>
  );
}

/** Карточка «растворяется» — несколько частиц разлетаются из центра колоды. */
function Dust({ trigger }: { trigger: number }) {
  const particles = useMemo(
    () =>
      Array.from({ length: 22 }, (_, i) => ({
        id: `${trigger}-${i}`,
        x: (Math.random() - 0.75) * 420,
        y: (Math.random() - 0.5) * 360,
        size: 3 + Math.random() * 6,
        delay: Math.random() * 0.12,
        mist: i % 3 === 0,
      })),
    [trigger],
  );
  if (!trigger) return null;
  return (
    <div className="pointer-events-none absolute top-[240px] left-1/2 z-20" aria-hidden key={trigger}>
      {particles.map((p) => (
        <motion.span
          key={p.id}
          className="absolute rounded-full"
          style={{ width: p.size, height: p.size, background: p.mist ? "var(--mist)" : "var(--del)" }}
          initial={{ x: 0, y: 0, opacity: 0.9, scale: 1 }}
          animate={{ x: p.x, y: p.y, opacity: 0, scale: 0.2 }}
          transition={{ duration: 0.9, delay: p.delay, ease: [0.2, 0.7, 0.3, 1] }}
        />
      ))}
    </div>
  );
}

function EmptyQueue({ laterCount, toDelete, laterMode, topMode, restCount, onLater, onAll, onGo }: {
  laterCount: number;
  toDelete: number;
  laterMode: boolean;
  topMode: boolean;
  restCount: number;
  onLater: () => void;
  onAll: () => void;
  onGo: (v: "delete" | "dash") => void;
}) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.96 }}
      animate={{ opacity: 1, scale: 1 }}
      className="z-10 flex w-full flex-col items-center gap-4 rounded-[26px] border border-dashed border-line p-10 text-center [grid-area:1/1]"
    >
      <div className="font-display text-[40px]" aria-hidden>👻</div>
      <h2 className="font-display text-[22px] font-semibold">
        {laterMode ? "Отложенные разобраны" : topMode ? "Главное сделано" : "Очередь пуста"}
      </h2>
      <p className="max-w-sm text-muted">
        {toDelete > 0
          ? `Дальше — удаление: ${fmt(toDelete)} ${plural(toDelete, "аккаунт ждёт", "аккаунта ждут", "аккаунтов ждут")}. Начните с лёгких.`
          : "Все сервисы из этой выборки разобраны."}
      </p>
      <div className="flex flex-wrap justify-center gap-2">
        {toDelete > 0 && (
          <button onClick={() => onGo("delete")} className="rounded-xl bg-del px-4 py-2 font-medium text-bg">
            Перейти к удалению
          </button>
        )}
        {laterCount > 0 && (
          <button onClick={onLater} className="rounded-xl border border-line px-4 py-2 hover:border-later">
            Разобрать отложенные ({fmt(laterCount)})
          </button>
        )}
        {topMode && restCount > 0 && (
          <button onClick={onAll} className="rounded-xl border border-line px-4 py-2 hover:border-mist">
            Остальные сервисы ({fmt(restCount)})
          </button>
        )}
        <button onClick={() => onGo("dash")} className="rounded-xl border border-line px-4 py-2 hover:border-mist">
          Открыть обзор
        </button>
      </div>
    </motion.div>
  );
}

function HintsBar({ disabled, canUndo, onAction, onUndo }: {
  disabled: boolean;
  canUndo: boolean;
  onAction: (d: Decision) => void;
  onUndo: () => void;
}) {
  return (
    <div className="fixed inset-x-0 bottom-0 z-30 border-t border-line/70 bg-bg/90 backdrop-blur">
      <div className="mx-auto flex max-w-3xl items-stretch justify-center gap-1 px-2 py-2 sm:gap-2 sm:px-4">
        {ACTIONS.map((a) => (
          <button
            key={a.decision}
            disabled={disabled}
            onClick={() => onAction(a.decision)}
            className="group flex flex-1 flex-col items-center gap-1 rounded-xl px-1 py-1.5 transition-colors hover:bg-bg-3 disabled:opacity-40 sm:flex-row sm:justify-center sm:gap-2"
          >
            <span className="flex items-center gap-1">
              <kbd style={{ color: a.color }}>{a.arrow}</kbd>
              <kbd className="hidden sm:inline-flex">{a.key}</kbd>
            </span>
            <span className="text-[13px] sm:text-[14px]" style={{ color: a.color }}>{a.label}</span>
          </button>
        ))}
        <button
          disabled={!canUndo}
          onClick={onUndo}
          className="flex flex-col items-center gap-1 rounded-xl px-2 py-1.5 text-muted transition-colors hover:bg-bg-3 disabled:opacity-40 sm:flex-row sm:gap-2"
        >
          <kbd>Z</kbd>
          <span className="text-[13px] sm:text-[14px]">Отменить</span>
        </button>
      </div>
    </div>
  );
}

function ModeSwitch({ mode, onMode, topCount }: { mode: SortMode; onMode: (m: SortMode) => void; topCount: number }) {
  const items: [SortMode, string][] = [
    ["all", "Все сервисы"],
    ["top", "Главное за 30 минут"],
  ];
  return (
    <div className="flex rounded-xl border border-line bg-bg-2 p-0.5 text-[14px]" role="tablist" aria-label="Режим">
      {items.map(([m, label]) => (
        <button
          key={m}
          role="tab"
          aria-selected={mode === m}
          onClick={() => onMode(m)}
          className={`relative rounded-[10px] px-3 py-1 transition-colors ${mode === m ? "text-text" : "text-muted hover:text-text"}`}
        >
          {mode === m && (
            <motion.span layoutId="sort-mode" className="absolute inset-0 rounded-[10px] bg-bg-3" transition={{ type: "spring", bounce: 0.2, duration: 0.35 }} />
          )}
          <span className="relative">
            {m === "top" && <span aria-hidden className="mr-1">⏱</span>}
            {label}
            {m === "top" && <span className="ml-1.5 text-faint tabular">{topCount}</span>}
          </span>
        </button>
      ))}
    </div>
  );
}

/** Что именно отменилось — для уведомления, когда карточка не возвращается на экран. */
function describeUndo(t: UndoTarget, svc: Service | undefined): string {
  const name = svc?.name ?? t.domain ?? "";
  if (!svc || !t.before) return name;
  if (svc.decision !== t.before.decision) {
    return svc.decision ? `«${DECISION_LABEL[svc.decision]}» для ${name}` : `решение для ${name}`;
  }
  if (svc.status !== t.before.status && svc.status) return `отметка «${STATUS_LABEL[svc.status]}» для ${name}`;
  if (svc.unsub_done !== t.before.unsub_done) return `отметка «отписка сделана» для ${name}`;
  return name;
}

/** Тихая строка под колодой: тонкая шкала и счётчик, без акцента. */
function DeckStatus({ done, total, text }: { done: number; total: number; text: React.ReactNode }) {
  const pct = total ? (done / total) * 100 : 0;
  return (
    <div className="flex items-center justify-center gap-3 text-[13px] text-faint">
      {total > 0 && (
        <span className="h-[3px] w-20 overflow-hidden rounded-full bg-line" aria-hidden>
          <motion.span className="block h-full rounded-full bg-mist/60" initial={false} animate={{ width: `${pct}%` }} transition={SETTLE} />
        </span>
      )}
      <span className="tabular">{text}</span>
    </div>
  );
}

/** Прогресс по «Главному» под колодой: ячейка на сервис, цвет — моё решение. */
function TopProgress({ services }: { services: Service[] }) {
  const done = services.filter((s) => s.decision && s.decision !== "later").length;
  const left = services.length - done;
  const pct = services.length ? Math.round((done / services.length) * 100) : 0;
  return (
    <section aria-label="Прогресс по главному" title="Слева — самые рискованные; красная черта — был в утечке. Цвет ячейки — ваше решение.">
      <div className="flex h-2 gap-[3px]" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
        {services.map((s) => {
          const decision = s.decision && s.decision !== "later" ? s.decision : null;
          return (
            <span
              key={s.domain}
              title={`${s.name}${s.risk.breached ? " · утечка" : ""}${decision ? "" : " · не разобран"}`}
              className="flex-1 rounded-[3px] transition-colors duration-300"
              style={{
                background: decision ? DECISION_COLOR[decision] : "var(--line)",
                boxShadow: s.risk.breached && !decision ? "inset 0 -2px 0 var(--del)" : undefined,
              }}
            />
          );
        })}
      </div>
      <p className="mt-2.5 text-center text-[13px] text-faint tabular">
        <span className="text-muted">{done}</span> из {services.length} самых рискованных
        {left > 0 ? ` · осталось ≈ ${left} мин` : " · готово"}
      </p>
    </section>
  );
}

const SortIcon = () => (
  <svg aria-hidden viewBox="0 0 16 16" className="size-4">
    <path d="M5 3v10M5 13l-2.5-2.5M5 13l2.5-2.5M11 13V3M11 3 8.5 5.5M11 3l2.5 2.5" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const FilterIcon = () => (
  <svg aria-hidden viewBox="0 0 16 16" className="size-4">
    <path d="M2.5 3.5h11L9.5 8.5v4l-3 1.5v-5.5z" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinejoin="round" />
  </svg>
);

/** Массовые решения для низкого риска: кнопка в панели, меню с подтверждением, отменяется одним Z. */
function BulkMenu({ services, onBulk }: { services: Service[]; onBulk: (a: BulkAction) => Promise<void> }) {
  const [open, setOpen] = useState(false);
  const [confirming, setConfirming] = useState<BulkAction | null>(null);
  const [busy, setBusy] = useState(false);
  const anchor = useRef<HTMLButtonElement>(null);
  const close = useCallback(() => {
    setOpen(false);
    setConfirming(null);
  }, []);
  const unsub = bulkTargets(services, "unsub_low");
  const skip = bulkTargets(services, "skip_low");
  if (skip.length === 0) return null;

  const run = async (action: BulkAction) => {
    setBusy(true);
    await onBulk(action);
    setBusy(false);
    close();
  };

  const items: { action: BulkAction; list: Service[]; title: string; text: string; color: string }[] = [
    { action: "unsub_low", list: unsub, title: "Рассылки → отписаться", text: "Попадут в список «Отписка»", color: "var(--unsub)" },
    { action: "skip_low", list: skip, title: "Все оставшиеся → пропустить", text: "Уйдут из очереди, риск снят", color: "var(--text)" },
  ];
  const pending = items.find((i) => i.action === confirming);

  return (
    <>
      <button
        ref={anchor}
        type="button"
        onClick={() => (open ? close() : setOpen(true))}
        aria-expanded={open}
        aria-haspopup="menu"
        title="Разобрать сервисы с низким риском одной кнопкой"
        className={`inline-flex items-center gap-2 rounded-xl border border-dashed px-3 py-1.5 text-[14px] whitespace-nowrap transition-colors hover:border-mist/60 ${
          open ? "border-mist/60" : "border-line"
        }`}
      >
        <span className="text-muted">Низкий риск</span>
        <span className="text-text tabular">{fmt(skip.length)}</span>
        <Chevron open={open} />
      </button>
      <Popover anchor={anchor} open={open} onClose={close} align="right" className="w-[310px]">
        {pending ? (
          <div className="flex flex-col gap-2.5 p-2.5">
            <p className="text-[14px]">
              {pending.title}: <span className="font-semibold tabular">{fmt(pending.list.length)}</span>{" "}
              {plural(pending.list.length, "сервис", "сервиса", "сервисов")}?
            </p>
            <p className="line-clamp-3 text-[13px] text-muted">
              {pending.list.slice(0, 8).map((s) => s.name).join(", ")}
              {pending.list.length > 8 && ` и ещё ${fmt(pending.list.length - 8)}`}
            </p>
            <p className="text-[12px] text-faint">Передумаете — Z отменит всё разом.</p>
            <div className="flex gap-2">
              <button
                disabled={busy}
                onClick={() => run(pending.action)}
                className="flex-1 rounded-lg bg-mist px-3 py-1.5 text-[14px] font-medium text-bg hover:bg-mist-strong disabled:opacity-50"
              >
                Да, применить
              </button>
              <button
                onClick={() => setConfirming(null)}
                className="rounded-lg border border-line px-3 py-1.5 text-[14px] text-muted hover:text-text"
              >
                Назад
              </button>
            </div>
          </div>
        ) : (
          <div className="flex flex-col" role="menu">
            <p className="px-2.5 pt-2 pb-1 text-[12px] text-faint">Разобрать низкий риск одной кнопкой</p>
            {items.map((i) =>
              i.list.length > 0 ? (
                <button
                  key={i.action}
                  role="menuitem"
                  onClick={() => setConfirming(i.action)}
                  className="flex items-center gap-3 rounded-lg px-2.5 py-2 text-left hover:bg-bg-3"
                >
                  <span className="min-w-0 flex-1">
                    <span className="block text-[14px]" style={{ color: i.color }}>{i.title}</span>
                    <span className="block text-[12px] text-faint">{i.text}</span>
                  </span>
                  <span className="text-[14px] text-muted tabular">{fmt(i.list.length)}</span>
                </button>
              ) : null,
            )}
          </div>
        )}
      </Popover>
    </>
  );
}

function NoData() {
  return (
    <main className="mx-auto max-w-xl px-4 py-16 sm:px-6">
      <h1 className="font-display text-[28px] font-semibold">Почта ещё не загружена</h1>
      <ol className="mt-6 flex list-decimal flex-col gap-3 pl-5 text-muted">
        <li>Закажите архив «Почта» в Google Takeout (формат mbox).</li>
        <li>Положите файл в папку <code className="text-text">data/</code> проекта.</li>
        <li>Запустите <code className="text-text">python -m vanish analyze</code> и обновите страницу.</li>
      </ol>
      <p className="mt-6 text-muted">
        Хотите сначала попробовать? Запустите <code className="text-text">python -m vanish demo</code> — там синтетические письма.
      </p>
    </main>
  );
}
