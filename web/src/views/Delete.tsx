import { AnimatePresence, motion } from "motion/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Avatar } from "../components/Avatar";
import { DifficultyBadge, LeakBadge, RiskBadge } from "../components/Badges";
import { celebrate } from "../celebrate";
import { byRisk, DIFFICULTY_LABEL, DIFFICULTY_ORDER, fmt, isDeleteOpen, plural, STATUS_LABEL } from "../lib";
import { useStore } from "../store";
import type { Service } from "../types";
import { ExtLink } from "./Sort";

const GROUP_TITLE: Record<string, string> = {
  easy: "Лёгкие — быстрые победы",
  medium: "Средние",
  "": "Нет в базе JustDeleteMe",
  hard: "Сложные",
  limited: "Удаляются частично",
  impossible: "Удалить нельзя — только почистить данные",
};

function groupKey(s: Service): string {
  return s.jdm ? s.difficulty : "";
}

export function DeleteView({ onGo }: { onGo: (v: "sort") => void }) {
  const { state } = useStore();
  const [showDone, setShowDone] = useState(false);
  const services = state?.services ?? [];

  const open = useMemo(
    () =>
      services
        .filter(isDeleteOpen)
        // «Позже» — в конец своей группы, остальные — самые рискованные первыми.
        .sort((a, b) => Number(a.status === "later") - Number(b.status === "later") || byRisk(a, b)),
    [services],
  );
  const done = useMemo(
    () =>
      services
        .filter((s) => s.decision === "delete" && (s.status === "deleted" || s.status === "failed"))
        .sort((a, b) => (b.finished_at || "").localeCompare(a.finished_at || "")),
    [services],
  );

  const groups = useMemo(() => {
    const map = new Map<string, Service[]>();
    for (const key of DIFFICULTY_ORDER) map.set(key, []);
    for (const s of open) map.get(groupKey(s))?.push(s);
    return [...map.entries()].filter(([, list]) => list.length > 0);
  }, [open]);

  const prevOpen = useRef(open.length);
  useEffect(() => {
    if (prevOpen.current > 0 && open.length === 0) celebrate("finish");
    prevOpen.current = open.length;
  }, [open.length]);

  if (!state) return null;
  const deleted = done.filter((s) => s.status === "deleted").length;

  return (
    <main className="mx-auto max-w-3xl px-4 pb-24 sm:px-6">
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 py-6">
        <h1 className="font-display text-[26px] font-semibold">Удаление</h1>
        <p className="text-muted">
          {open.length > 0
            ? `${fmt(open.length)} ${plural(open.length, "аккаунт ждёт", "аккаунта ждут", "аккаунтов ждут")}`
            : "Очередь пуста"}
          {deleted > 0 && <> · удалено <span className="text-keep tabular">{fmt(deleted)}</span></>}
        </p>
      </div>

      {open.length === 0 && (
        <div className="flex flex-col items-center gap-3 rounded-[28px] border border-dashed border-line p-10 text-center">
          <div className="text-[40px]" aria-hidden>{done.length ? "🫥" : "🗂"}</div>
          <h2 className="font-display text-[20px] font-semibold">
            {done.length ? "Все аккаунты из очереди обработаны" : "Здесь появятся сервисы, помеченные «Удалить»"}
          </h2>
          <button onClick={() => onGo("sort")} className="rounded-xl border border-line px-4 py-2 hover:border-mist">
            К сортировке
          </button>
        </div>
      )}

      <div className="flex flex-col gap-10">
        {groups.map(([key, list]) => (
          <section key={key || "unknown"} aria-labelledby={`g-${key || "unknown"}`}>
            <h2 id={`g-${key || "unknown"}`} className="mb-3 flex items-baseline gap-2 text-[15px] font-semibold">
              {GROUP_TITLE[key] ?? DIFFICULTY_LABEL[key]}
              <span className="font-normal text-faint tabular">{fmt(list.length)}</span>
            </h2>
            <ul className="flex flex-col gap-3">
              <AnimatePresence initial={false}>
                {list.map((s) => (
                  <DeleteItem key={s.domain} service={s} />
                ))}
              </AnimatePresence>
            </ul>
          </section>
        ))}
      </div>

      {done.length > 0 && (
        <section className="mt-12">
          <button onClick={() => setShowDone((v) => !v)} className="text-[15px] text-muted hover:text-text" aria-expanded={showDone}>
            {showDone ? "▾" : "▸"} Завершённые ({fmt(done.length)})
          </button>
          {showDone && (
            <ul className="mt-3 flex flex-col divide-y divide-line/60 rounded-2xl border border-line">
              {done.map((s) => (
                <DoneItem key={s.domain} service={s} />
              ))}
            </ul>
          )}
        </section>
      )}
    </main>
  );
}

function DeleteItem({ service: s }: { service: Service }) {
  const { update } = useStore();
  const [opened, setOpened] = useState(false);
  const later = s.status === "later";
  const href = s.links.delete ?? s.links.search_delete;

  return (
    <motion.li
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, x: -30, filter: "blur(8px)", transition: { duration: 0.3 } }}
      className={`rounded-2xl border bg-bg-2 p-4 sm:p-5 ${later ? "border-line/60 opacity-75" : "border-line"}`}
    >
      <div className="flex items-start gap-3.5">
        <Avatar service={s} size={44} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-3">
            <h3 className="truncate font-semibold">{s.name}</h3>
            <span className="truncate text-[13px] text-faint">{s.domain}</span>
            {later && <span className="text-[13px] text-later">отложено</span>}
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-[13px] text-muted">
            <span className="flex items-center gap-1.5">
              <RiskBadge risk={s.risk} compact />
              <LeakBadge risk={s.risk} />
            </span>
            <DifficultyBadge service={s} />
            {s.count > 0 && <span className="tabular">{fmt(s.count)} {plural(s.count, "письмо", "письма", "писем")}</span>}
            {s.google_linked && (
              <a href={s.links.google_connections} target="_blank" rel="noreferrer noopener" className="text-mist hover:underline">
                Отвязать вход через Google ↗
              </a>
            )}
          </div>
          {s.jdm?.notes && <p className="mt-2 text-[14px] leading-relaxed text-muted">{s.jdm.notes}</p>}
          {s.jdm?.email && (
            <p className="mt-1 text-[13px] text-muted">
              Удаление по письму: <span className="text-text select-all">{s.jdm.email}</span>
            </p>
          )}
        </div>
      </div>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <a
          href={href}
          target="_blank"
          rel="noreferrer noopener"
          onClick={() => setOpened(true)}
          className={`rounded-xl px-3.5 py-2 text-[14px] font-medium transition-colors ${
            opened ? "border border-line text-text hover:border-mist" : "bg-mist text-bg hover:bg-mist-strong"
          }`}
        >
          {s.links.delete ? "Открыть страницу удаления" : `Найти: как удалить аккаунт ${s.name}`} <span aria-hidden>↗</span>
        </a>
        <span className="mx-1 hidden h-6 w-px bg-line sm:block" aria-hidden />
        <button
          onClick={() => update(s, { status: "deleted" })}
          className="rounded-xl bg-keep/15 px-3.5 py-2 text-[14px] font-medium text-keep transition-colors hover:bg-keep/25"
        >
          Удалено ✓
        </button>
        <button
          onClick={() => update(s, { status: "failed" })}
          className="rounded-xl px-3 py-2 text-[14px] text-del transition-colors hover:bg-del/10"
        >
          Не получилось
        </button>
        <button
          onClick={() => update(s, { status: later ? "pending" : "later" })}
          className="rounded-xl px-3 py-2 text-[14px] text-later transition-colors hover:bg-later/10"
        >
          {later ? "Вернуть в очередь" : "Позже"}
        </button>
      </div>

      {(!s.links.delete || s.note) && <NoteField service={s} />}
      {s.links.delete && !s.note && (
        <details className="mt-2 text-[13px] text-faint">
          <summary className="cursor-pointer hover:text-muted">Заметка</summary>
          <NoteField service={s} />
        </details>
      )}
      {!s.links.delete && (
        <div className="mt-2 flex flex-wrap gap-2">
          <ExtLink href={s.links.site}>Сайт</ExtLink>
          <ExtLink href={s.links.gmail}>Письма в Gmail</ExtLink>
        </div>
      )}
    </motion.li>
  );
}

export function NoteField({ service: s }: { service: Service }) {
  const { update } = useStore();
  const [value, setValue] = useState(s.note);
  useEffect(() => setValue(s.note), [s.note]);
  const save = () => {
    if (value !== s.note) update(s, { note: value });
  };
  return (
    <label className="mt-3 block">
      <span className="sr-only">Заметка к {s.name}</span>
      <textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onBlur={save}
        rows={value.includes("\n") ? 3 : 1}
        placeholder="Заметка: как удалял, куда писал, номер обращения…"
        className="w-full resize-y rounded-xl border border-line bg-bg px-3 py-2 text-[14px] text-text placeholder:text-faint focus:border-mist/60 focus:outline-none"
      />
    </label>
  );
}

function DoneItem({ service: s }: { service: Service }) {
  const { update } = useStore();
  const ok = s.status === "deleted";
  return (
    <li className="flex items-center gap-3 px-4 py-3">
      <Avatar service={s} size={32} />
      <div className="min-w-0 flex-1">
        <div className="truncate text-[14px]">{s.name}</div>
        {s.note && <div className="truncate text-[13px] text-faint">{s.note}</div>}
      </div>
      <span className={`text-[13px] ${ok ? "text-keep" : "text-del"}`}>{s.status && STATUS_LABEL[s.status]}</span>
      <button onClick={() => update(s, { status: "pending" })} className="text-[13px] text-faint hover:text-text">
        Вернуть
      </button>
    </li>
  );
}
