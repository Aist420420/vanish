import { useMemo, useRef, useState, type FormEvent } from "react";
import { Avatar } from "../components/Avatar";
import { ConfidenceBadge, LeakBadge, RiskBadge } from "../components/Badges";
import {
  byRisk,
  CONFIDENCE_LABEL,
  DECISION_COLOR,
  DECISION_LABEL,
  DIFFICULTY_COLOR,
  DIFFICULTY_LABEL,
  fmt,
  fmtDate,
  isDeleteOpen,
  isRiskClosed,
  isTracked,
  plural,
  RISK_COLOR,
  RISK_SHORT,
  STATUS_LABEL,
  topServices,
} from "../lib";
import { useStore } from "../store";
import type { Decision, DeleteStatus, RiskLevel, Service } from "../types";
import { Dropdown, Select } from "../components/Dropdown";
import { writePref } from "./Sort";

type StatusFilter =
  | "all"
  | "undecided"
  | "delete_open"
  | "deleted"
  | "failed"
  | "keep"
  | "unsubscribe"
  | "later"
  | "skip"
  | "personal";

const STATUS_FILTERS: [StatusFilter, string][] = [
  ["all", "Все"],
  ["undecided", "Не разобраны"],
  ["delete_open", "Ждут удаления"],
  ["deleted", "Удалены"],
  ["failed", "Не получилось удалить"],
  ["keep", "Оставлены"],
  ["unsubscribe", "Отписаться"],
  ["later", "Отложены"],
  ["skip", "Пропущены"],
  ["personal", "Скрытая переписка"],
];

function matchStatus(s: Service, f: StatusFilter): boolean {
  switch (f) {
    case "all":
      return isTracked(s);
    case "undecided":
      return isTracked(s) && s.decision === null;
    case "delete_open":
      return isDeleteOpen(s);
    case "deleted":
    case "failed":
      return s.decision === "delete" && s.status === f;
    case "personal":
      return s.confidence === "personal" && s.decision === null && !s.manual;
    default:
      return s.decision === f;
  }
}

const PAGE = 50;

export function Dashboard({ onGo }: { onGo: (v: "sort") => void }) {
  const { state } = useStore();
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<StatusFilter>("all");
  const [riskFilter, setRiskFilter] = useState("all");
  const [conf, setConf] = useState("all");
  const [diff, setDiff] = useState("all");
  const [year, setYear] = useState<number | null>(null);
  const [limit, setLimit] = useState(PAGE);
  const tableRef = useRef<HTMLElement>(null);

  const services = state?.services ?? [];
  const tracked = useMemo(() => services.filter(isTracked), [services]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return services.filter(
      (s) =>
        matchStatus(s, status) &&
        (riskFilter === "all" || (riskFilter === "breached" ? s.risk.breached : s.risk.level === riskFilter)) &&
        (conf === "all" || s.confidence === conf) &&
        (diff === "all" || (diff === "none" ? !s.jdm : s.jdm && s.difficulty === diff)) &&
        (year === null || s.first_year === year) &&
        (!q || s.name.toLowerCase().includes(q) || s.domain.includes(q) || s.note.toLowerCase().includes(q)),
    );
  }, [services, query, status, riskFilter, conf, diff, year]);

  if (!state) return null;
  const { game, meta } = state;

  const decided = tracked.filter((s) => s.decision && s.decision !== "later").length;
  const deleted = tracked.filter((s) => s.decision === "delete" && s.status === "deleted").length;
  const left = tracked.filter((s) => s.decision === null || s.decision === "later").length;

  const pickYear = (y: number | null) => {
    setYear(y);
    setLimit(PAGE);
    if (y !== null) tableRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <main className="mx-auto max-w-6xl px-4 pb-24 sm:px-6">
      <h1 className="py-6 font-display text-[26px] font-semibold">Обзор</h1>

      {meta.demo && (
        <p className="mb-6 rounded-2xl border border-unsub/40 bg-unsub/10 px-4 py-3 text-[14px]">
          Это демо на синтетических письмах. Свой архив: положите mbox в <code>data/</code> и запустите{" "}
          <code>python -m vanish</code>.
        </p>
      )}

      <RiskIndex services={tracked} topN={meta.top_n} onTop={() => { writePref("vanish.mode", "top"); onGo("sort"); }} />

      <section className="mt-8 grid grid-cols-2 gap-3 lg:grid-cols-4" aria-label="Итоги">
        <Stat label="Найдено сервисов" value={tracked.length} />
        <Stat label="Разобрано" value={decided} sub={tracked.length ? `${Math.round((decided / tracked.length) * 100)}%` : undefined} />
        <Stat label="Удалено аккаунтов" value={deleted} accent="var(--keep)" />
        <Stat label="Осталось разобрать" value={left} />
      </section>

      <div className="mt-8 grid gap-8 lg:grid-cols-[3fr_2fr]">
        <YearChart services={tracked} selected={year} onPick={pickYear} />
        <TopNoisy services={tracked} />
      </div>

      <Achievements />

      <section ref={tableRef} className="mt-12 scroll-mt-40" aria-labelledby="all-services">
        <div className="mb-4 flex flex-wrap items-baseline gap-x-3">
          <h2 id="all-services" className="font-display text-[20px] font-semibold">Все сервисы</h2>
          <span className="text-muted tabular">
            {fmt(filtered.length)} {plural(filtered.length, "сервис", "сервиса", "сервисов")}
          </span>
        </div>
        <div className="mb-4 flex flex-wrap gap-2">
          <input
            type="search"
            value={query}
            onChange={(e) => { setQuery(e.target.value); setLimit(PAGE); }}
            placeholder="Поиск: название, домен, заметка"
            className="min-w-[220px] flex-1 rounded-xl border border-line bg-bg-2 px-3 py-1.5 text-[14px] placeholder:text-faint focus:border-mist/60 focus:outline-none"
          />
          <Select label="Статус" value={status} onChange={(v) => { setStatus(v as StatusFilter); setLimit(PAGE); }} options={STATUS_FILTERS} />
          <Select
            label="Риск"
            value={riskFilter}
            onChange={(v) => { setRiskFilter(v); setLimit(PAGE); }}
            options={[["all", "Любой"], ["high", "Высокий"], ["medium", "Средний"], ["low", "Низкий"], ["breached", "Были в утечке"]]}
          />
          <Select
            label="Уверенность"
            value={conf}
            onChange={(v) => { setConf(v); setLimit(PAGE); }}
            options={[["all", "Любая"], ...(Object.entries(CONFIDENCE_LABEL) as [string, string][])]}
          />
          <Select
            label="Удаление"
            value={diff}
            onChange={(v) => { setDiff(v); setLimit(PAGE); }}
            options={[
              ["all", "Любое"],
              ["easy", "Легко"],
              ["medium", "Средне"],
              ["hard", "Сложно"],
              ["limited", "Частично"],
              ["impossible", "Невозможно"],
              ["none", "Нет в JustDeleteMe"],
            ]}
          />
          {year !== null && (
            <button onClick={() => pickYear(null)} className="rounded-xl border border-mist/50 px-3 py-1 text-[14px] text-mist-strong">
              С {year} года ✕
            </button>
          )}
        </div>

        <div className="overflow-hidden rounded-2xl border border-line">
          <ul className="divide-y divide-line/60">
            {filtered.slice(0, limit).map((s) => (
              <ServiceRow key={s.domain} service={s} />
            ))}
          </ul>
          {filtered.length === 0 && <p className="p-8 text-center text-muted">Ничего не найдено</p>}
        </div>
        {filtered.length > limit && (
          <button onClick={() => setLimit((n) => n + PAGE * 2)} className="mt-3 w-full rounded-xl border border-line py-2 text-muted hover:text-text">
            Показать ещё ({fmt(filtered.length - limit)})
          </button>
        )}
      </section>

      <div className="mt-12 grid gap-8 lg:grid-cols-2">
        <AddService />
        <DataPanel />
      </div>

      <p className="mt-10 text-[13px] text-faint">
        {meta.last_import ? `Последний импорт почты: ${fmtDate(meta.last_import)}` : "Почта ещё не импортирована"}
        {" · "}База JustDeleteMe: {fmt(meta.jdm_count)} сервисов · Утечки:{" "}
        <a href="https://haveibeenpwned.com" target="_blank" rel="noreferrer noopener" className="hover:underline">
          Have I Been Pwned
        </a>{" "}
        (CC BY 4.0), {fmt(meta.breaches_count)} · {fmt(game.xp)} XP
      </p>
    </main>
  );
}

const LEVELS: RiskLevel[] = ["high", "medium", "low"];

/** Индекс риска: доля «рискового веса», которая ещё не закрыта (100 — ничего не сделано, 0 — всё). */
function RiskIndex({ services, topN, onTop }: { services: Service[]; topN: number; onTop: () => void }) {
  const data = useMemo(() => {
    const total = services.reduce((n, s) => n + s.risk.score, 0);
    const open = services.reduce((n, s) => n + (isRiskClosed(s) ? 0 : s.risk.score), 0);
    const levels = LEVELS.map((level) => {
      const items = services.filter((s) => s.risk.level === level);
      return { level, total: items.length, open: items.filter((s) => !isRiskClosed(s)).length };
    });
    const top = topServices(services, topN);
    return {
      index: total ? Math.round((100 * open) / total) : 0,
      levels,
      leaksOpen: services.filter((s) => s.risk.breached && !isRiskClosed(s)).sort(byRisk),
      top,
      topDone: top.filter((s) => s.decision && s.decision !== "later").length,
    };
  }, [services, topN]);

  const high = data.levels[0];
  const tone = data.index >= 66 ? "high" : data.index >= 33 ? "medium" : "low";
  const maxLevel = Math.max(1, ...data.levels.map((l) => l.total));

  return (
    <section aria-labelledby="risk-title" className="grid gap-6 rounded-3xl border border-line bg-bg-2 p-5 sm:p-6 lg:grid-cols-[1fr_1.2fr_1.2fr]">
      <div className="flex flex-col gap-3">
        <h2 id="risk-title" className="text-[14px] text-muted">Индекс риска</h2>
        <div className="flex items-baseline gap-2">
          <span className="font-display text-[56px] leading-none font-semibold tabular" style={{ color: RISK_COLOR[tone] }}>
            {data.index}
          </span>
          <span className="text-faint">/ 100</span>
        </div>
        <div className="h-1.5 overflow-hidden rounded-full bg-line/70" aria-hidden>
          <div className="h-full rounded-full transition-[width] duration-700" style={{ width: `${data.index}%`, background: RISK_COLOR[tone] }} />
        </div>
        <p className="text-[14px] text-muted">
          Высокого риска осталось{" "}
          <span className="font-semibold text-text tabular">{fmt(high.open)}</span> из {fmt(high.total)}
          {data.leaksOpen.length > 0 && (
            <>
              <br />
              Из утечек не закрыто: <span className="font-semibold text-del tabular">{fmt(data.leaksOpen.length)}</span>
            </>
          )}
        </p>
        <p className="text-[12px] text-faint">100 — ничего не сделано, 0 — все риски закрыты. Рискованные аккаунты весят больше.</p>
      </div>

      <div className="flex flex-col gap-3">
        <h3 className="text-[14px] text-muted">Открытые аккаунты по уровню риска</h3>
        <ul className="flex flex-col gap-3">
          {data.levels.map((l) => (
            <li key={l.level} className="grid grid-cols-[5.5rem_1fr_auto] items-center gap-3 text-[14px]">
              <span style={{ color: RISK_COLOR[l.level] }}>{RISK_SHORT[l.level]}</span>
              <span className="relative h-2.5 overflow-hidden rounded-full bg-line/50" style={{ width: `${Math.max(8, (l.total / maxLevel) * 100)}%` }}>
                <span
                  className="absolute inset-y-0 left-0 rounded-full transition-[width] duration-700"
                  style={{ width: l.total ? `${(l.open / l.total) * 100}%` : 0, background: RISK_COLOR[l.level] }}
                />
              </span>
              <span className="text-right text-muted tabular">
                {fmt(l.open)} <span className="text-faint">/ {fmt(l.total)}</span>
              </span>
            </li>
          ))}
        </ul>
        {data.leaksOpen.length > 0 && (
          <p className="text-[13px] text-muted">
            <span className="text-del">⚠</span> {data.leaksOpen.slice(0, 5).map((s) => s.name).join(", ")}
            {data.leaksOpen.length > 5 && ` и ещё ${data.leaksOpen.length - 5}`}
          </p>
        )}
      </div>

      <div className="flex flex-col gap-3 rounded-2xl bg-bg-3/60 p-4">
        <h3 className="flex items-baseline justify-between gap-2 text-[14px]">
          <span className="font-medium">⏱ Главное за 30 минут</span>
          <span className="text-muted tabular">{data.topDone} из {data.top.length}</span>
        </h3>
        <div className="flex h-2.5 gap-[2px]" aria-hidden>
          {data.top.map((s) => {
            const d = s.decision && s.decision !== "later" ? s.decision : null;
            return <span key={s.domain} className="flex-1 rounded-[2px]" style={{ background: d ? DECISION_COLOR[d] : "var(--line)" }} />;
          })}
        </div>
        <p className="text-[13px] text-muted">
          {data.topDone >= data.top.length && data.top.length > 0
            ? "Самые рискованные сервисы разобраны. Дальше — очередь удаления."
            : `${data.top.length} самых рискованных сервисов — по минуте на каждый.`}
        </p>
        {data.topDone < data.top.length && (
          <button onClick={onTop} className="mt-auto self-start rounded-xl bg-mist px-4 py-2 text-[14px] font-medium text-bg hover:bg-mist-strong">
            {data.topDone > 0 ? "Продолжить" : "Начать"}
          </button>
        )}
      </div>
    </section>
  );
}

function Stat({ label, value, sub, accent }: { label: string; value: number; sub?: string; accent?: string }) {
  return (
    <div className="rounded-2xl border border-line bg-bg-2 p-4">
      <div className="text-[13px] text-muted">{label}</div>
      <div className="mt-1 flex items-baseline gap-2">
        <span className="font-display text-[28px] leading-tight font-semibold tabular" style={accent ? { color: accent } : undefined}>
          {fmt(value)}
        </span>
        {sub && <span className="text-[14px] text-faint tabular">{sub}</span>}
      </div>
    </div>
  );
}

/** Регистрации по годам: год первого письма от сервиса, где у меня (вероятно) аккаунт. */
function YearChart({ services, selected, onPick }: { services: Service[]; selected: number | null; onPick: (y: number | null) => void }) {
  const [hover, setHover] = useState<number | null>(null);
  const data = useMemo(() => {
    const counts = new Map<number, { all: number; deleted: number }>();
    for (const s of services) {
      if (!s.first_year || (s.confidence !== "sure" && s.confidence !== "likely")) continue;
      const c = counts.get(s.first_year) ?? { all: 0, deleted: 0 };
      c.all++;
      if (s.decision === "delete" && s.status === "deleted") c.deleted++;
      counts.set(s.first_year, c);
    }
    if (counts.size === 0) return [];
    const years = [...counts.keys()];
    const from = Math.min(...years);
    const to = Math.max(...years);
    return Array.from({ length: to - from + 1 }, (_, i) => ({ year: from + i, ...(counts.get(from + i) ?? { all: 0, deleted: 0 }) }));
  }, [services]);

  const max = Math.max(1, ...data.map((d) => d.all));
  const shown = hover !== null ? data.find((d) => d.year === hover) : null;
  const labelEvery = data.length > 16 ? 4 : data.length > 8 ? 2 : 1;

  return (
    <section aria-labelledby="years-title">
      <div className="mb-3 flex items-baseline justify-between gap-3">
        <h2 id="years-title" className="font-semibold">Регистрации по годам</h2>
        <span className="text-[13px] text-faint">
          {shown
            ? `${shown.year}: ${fmt(shown.all)} ${plural(shown.all, "аккаунт", "аккаунта", "аккаунтов")}${shown.deleted ? `, удалено ${fmt(shown.deleted)}` : ""}`
            : "по первому письму · нажмите на год"}
        </span>
      </div>
      {data.length === 0 ? (
        <p className="rounded-2xl border border-line p-6 text-muted">Нет данных о регистрациях</p>
      ) : (
        <div className="rounded-2xl border border-line bg-bg-2 p-4">
          <div className="flex h-44 items-end gap-[2px]" onMouseLeave={() => setHover(null)}>
            {data.map((d) => {
              const active = selected === d.year;
              const dim = selected !== null && !active;
              return (
                <button
                  key={d.year}
                  onMouseEnter={() => setHover(d.year)}
                  onFocus={() => setHover(d.year)}
                  onBlur={() => setHover(null)}
                  onClick={() => onPick(active ? null : d.year)}
                  disabled={d.all === 0}
                  aria-label={`${d.year}: ${d.all}`}
                  aria-pressed={active}
                  className="group flex h-full flex-1 flex-col justify-end rounded-t-[4px] focus-visible:outline-offset-0"
                >
                  <span
                    className="relative block w-full overflow-hidden rounded-t-[4px] transition-[height,opacity] duration-500"
                    style={{
                      height: `${(d.all / max) * 100}%`,
                      minHeight: d.all ? 3 : 0,
                      background: "var(--mist)",
                      opacity: dim ? 0.3 : hover === d.year || active ? 1 : 0.75,
                    }}
                  >
                    {d.deleted > 0 && (
                      <span className="absolute inset-x-0 bottom-0 block bg-keep" style={{ height: `${(d.deleted / d.all) * 100}%` }} />
                    )}
                  </span>
                </button>
              );
            })}
          </div>
          <div className="mt-1.5 flex gap-[2px] text-[11px] text-faint tabular">
            {data.map((d, i) => (
              <span key={d.year} className="flex-1 text-center">
                {i % labelEvery === 0 ? `’${String(d.year).slice(2)}` : ""}
              </span>
            ))}
          </div>
          <div className="mt-3 flex gap-4 text-[12px] text-muted">
            <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-mist" /> аккаунты</span>
            <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-keep" /> удалены</span>
          </div>
        </div>
      )}
    </section>
  );
}

function TopNoisy({ services }: { services: Service[] }) {
  const top = useMemo(() => [...services].sort((a, b) => b.count - a.count).slice(0, 8), [services]);
  const max = Math.max(1, top[0]?.count ?? 1);
  return (
    <section aria-labelledby="noisy-title">
      <h2 id="noisy-title" className="mb-3 font-semibold">Самые шумные</h2>
      <ol className="flex flex-col gap-2.5 rounded-2xl border border-line bg-bg-2 p-4">
        {top.map((s) => (
          <li key={s.domain} className="grid grid-cols-[minmax(0,9rem)_1fr_auto] items-center gap-3 text-[14px]">
            <span className="truncate" title={s.domain}>{s.name}</span>
            <span className="h-2 overflow-hidden rounded-full bg-line/60">
              <span
                className="block h-full rounded-full"
                style={{ width: `${(s.count / max) * 100}%`, background: s.decision ? DECISION_COLOR[s.decision] : "var(--faint)" }}
              />
            </span>
            <span className="text-right text-muted tabular">{fmt(s.count)}</span>
          </li>
        ))}
        {top.length === 0 && <li className="text-muted">Пока пусто</li>}
      </ol>
      <p className="mt-2 text-[12px] text-faint">Цвет — ваше решение, серый — ещё не разобран</p>
    </section>
  );
}

function Achievements() {
  const { state } = useStore();
  if (!state) return null;
  const list = state.game.achievements;
  const got = list.filter((a) => a.unlocked_at).length;
  return (
    <section className="mt-12" aria-labelledby="ach-title">
      <div className="mb-4 flex items-baseline gap-3">
        <h2 id="ach-title" className="font-display text-[20px] font-semibold">Достижения</h2>
        <span className="text-muted tabular">{got} из {list.length}</span>
      </div>
      <ul className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:grid-cols-3">
        {list.map((a) => {
          const on = !!a.unlocked_at;
          return (
            <li
              key={a.id}
              className={`flex items-center gap-3 rounded-2xl border p-3.5 ${on ? "border-mist/40 bg-bg-2" : "border-line/60 border-dashed"}`}
            >
              <span className={`grid h-10 w-10 shrink-0 place-items-center rounded-xl text-xl ${on ? "bg-bg-3" : "bg-bg-2 grayscale opacity-40"}`} aria-hidden>
                {a.icon}
              </span>
              <span className="min-w-0">
                <span className={`block font-medium leading-snug ${on ? "" : "text-muted"}`}>{a.title}</span>
                <span className="block text-[13px] text-faint">
                  {a.description}
                  {on && a.unlocked_at && ` · ${fmtDate(a.unlocked_at)}`}
                </span>
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

const DECISION_OPTIONS: [string, string][] = [["", "Не разобран"], ...(Object.entries(DECISION_LABEL) as [string, string][])];
const STATUS_OPTIONS = Object.entries(STATUS_LABEL) as [DeleteStatus, string][];
const DECISION_COLORS: Record<string, string> = { "": "var(--muted)", ...DECISION_COLOR };

function ServiceRow({ service: s }: { service: Service }) {
  const { update } = useStore();
  const [open, setOpen] = useState(false);
  return (
    <li className="bg-bg-2/40">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 px-4 py-3">
        <button onClick={() => setOpen((v) => !v)} className="flex min-w-0 flex-1 items-center gap-3 text-left" aria-expanded={open}>
          <Avatar service={s} size={34} />
          <span className="min-w-0">
            <span className="block truncate font-medium">
              {s.name}
              {s.manual && <span className="ml-2 text-[12px] font-normal text-faint">добавлен вручную</span>}
            </span>
            <span className="block truncate text-[13px] text-faint">
              {s.domain} · {s.risk.category_label}
              {s.count > 0 && ` · ${fmt(s.count)} ${plural(s.count, "письмо", "письма", "писем")}`}
              {s.first_year && ` · с ${s.first_year}`}
            </span>
          </span>
        </button>
        <span className="flex items-center gap-1.5">
          <RiskBadge risk={s.risk} compact />
          <LeakBadge risk={s.risk} />
        </span>
        <span className={`hidden w-28 text-[13px] md:block ${DIFFICULTY_COLOR[s.jdm ? s.difficulty : ""]}`}>
          {s.jdm ? DIFFICULTY_LABEL[s.difficulty] : "—"}
        </span>
        <div className="flex items-center gap-2">
          <Dropdown
            variant="chip"
            align="right"
            value={s.decision ?? ""}
            onChange={(v) => update(s, { decision: (v || null) as Decision | null })}
            ariaLabel={`Решение для ${s.name}`}
            options={DECISION_OPTIONS}
            colors={DECISION_COLORS}
          />
          {s.decision === "delete" && (
            <Dropdown
              variant="chip"
              align="right"
              value={s.status ?? "pending"}
              onChange={(v) => update(s, { status: v as DeleteStatus })}
              ariaLabel={`Статус удаления ${s.name}`}
              options={STATUS_OPTIONS}
            />
          )}
          {s.decision === "unsubscribe" && (
            <label className="flex items-center gap-1.5 text-[13px] text-muted">
              <input type="checkbox" checked={s.unsub_done} onChange={(e) => update(s, { unsub_done: e.target.checked })} className="accent-[var(--keep)]" />
              готово
            </label>
          )}
        </div>
      </div>
      {open && <RowDetails service={s} />}
    </li>
  );
}

function RowDetails({ service: s }: { service: Service }) {
  const { update } = useStore();
  const [note, setNote] = useState(s.note);
  return (
    <div className="grid gap-4 border-t border-line/60 px-4 py-4 text-[14px] md:grid-cols-2">
      <div className="flex flex-col gap-2">
        <ConfidenceBadge confidence={s.confidence} />
        <p className="text-muted">
          Риск {s.risk.score} из 100: {s.risk.reasons.join(", ")}
        </p>
        {s.risk.breaches.map((b) => (
          <p key={b.name} className="text-muted">
            <span className="text-del">Утечка «{b.title}»</span>, {fmtDate(b.date)}: {fmt(b.pwn_count)} аккаунтов
            {b.data_ru.length > 0 && ` — ${b.data_ru.join(", ")}`}
          </p>
        ))}
        <p className="text-muted">
          Письма: {fmtDate(s.first)} — {fmtDate(s.last)}
          {s.has_unsub && " · есть ссылка отписки"}
        </p>
        {s.samples.length > 0 && (
          <ul className="text-muted">
            {s.samples.map((t, i) => (
              <li key={i} className="truncate">«{t}»</li>
            ))}
          </ul>
        )}
        <div className="flex flex-wrap gap-x-4 gap-y-1">
          {[
            ["Сайт", s.links.site],
            ["Письма в Gmail", s.links.gmail],
            [s.links.delete ? "Страница удаления" : "Как удалить", s.links.delete ?? s.links.search_delete],
            ...(s.google_linked ? [["Доступы Google", s.links.google_connections]] : []),
          ].map(([label, href]) => (
            <a key={label} href={href} target="_blank" rel="noreferrer noopener" className="text-mist hover:underline">
              {label} ↗
            </a>
          ))}
        </div>
      </div>
      <label className="flex flex-col gap-1">
        <span className="text-[13px] text-faint">Заметка</span>
        <textarea
          value={note}
          onChange={(e) => setNote(e.target.value)}
          onBlur={() => note !== s.note && update(s, { note })}
          rows={3}
          className="w-full resize-y rounded-xl border border-line bg-bg px-3 py-2 text-text focus:border-mist/60 focus:outline-none"
        />
      </label>
    </div>
  );
}

function AddService() {
  const { add } = useStore();
  const [domain, setDomain] = useState("");
  const [name, setName] = useState("");
  const [decision, setDecision] = useState<string>("delete");
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (!domain.trim()) return;
    setBusy(true);
    const ok = await add(domain.trim(), name.trim(), (decision || null) as Decision | null);
    setBusy(false);
    if (ok) {
      setDomain("");
      setName("");
    }
  };

  return (
    <section aria-labelledby="add-title">
      <h2 id="add-title" className="mb-1 font-semibold">Добавить сервис вручную</h2>
      <p className="mb-3 text-[14px] text-muted">Если аккаунт был заведён на другую почту или письма давно удалены.</p>
      <form onSubmit={submit} className="flex flex-col gap-2 rounded-2xl border border-line bg-bg-2 p-4">
        <input
          value={domain}
          onChange={(e) => setDomain(e.target.value)}
          placeholder="Домен или ссылка: example.com"
          required
          className="rounded-xl border border-line bg-bg px-3 py-2 text-[14px] placeholder:text-faint focus:border-mist/60 focus:outline-none"
        />
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Название (необязательно)"
          className="rounded-xl border border-line bg-bg px-3 py-2 text-[14px] placeholder:text-faint focus:border-mist/60 focus:outline-none"
        />
        <div className="flex flex-wrap items-center gap-2">
          <Select label="Решение" value={decision} onChange={setDecision} options={DECISION_OPTIONS} />
          <button disabled={busy || !domain.trim()} className="ml-auto rounded-xl bg-mist px-4 py-2 text-[14px] font-medium text-bg hover:bg-mist-strong disabled:opacity-50">
            Добавить
          </button>
        </div>
      </form>
    </section>
  );
}

function DataPanel() {
  const { importProgress } = useStore();
  const fileRef = useRef<HTMLInputElement>(null);
  const btn = "rounded-xl border border-line px-3.5 py-2 text-[14px] transition-colors hover:border-mist/60";
  return (
    <section aria-labelledby="data-title">
      <h2 id="data-title" className="mb-1 font-semibold">Отчёт и прогресс</h2>
      <p className="mb-3 text-[14px] text-muted">
        Прогресс хранится в файле <code>state/vanish.db</code> в папке проекта. Резервная копия решений — в JSON.
      </p>
      <div className="flex flex-wrap gap-2 rounded-2xl border border-line bg-bg-2 p-4">
        <a href="/api/export.csv" download className={btn}>Скачать отчёт CSV</a>
        <a href="/api/progress.json" download className={btn}>Экспорт прогресса JSON</a>
        <button onClick={() => fileRef.current?.click()} className={btn}>Импорт прогресса…</button>
        <input
          ref={fileRef}
          type="file"
          accept="application/json,.json"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f && confirm("Загрузить решения из файла? Совпадающие сервисы будут перезаписаны.")) importProgress(f);
            e.target.value = "";
          }}
        />
      </div>
    </section>
  );
}
