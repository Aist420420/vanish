import { AnimatePresence, motion } from "motion/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Avatar } from "../components/Avatar";
import { celebrate } from "../celebrate";
import { fmt, fmtDate, plural } from "../lib";
import { useStore } from "../store";
import type { Service } from "../types";

// После массовой отписки список бывает на тысячи строк — показываю порциями.
const PAGE = 50;

export function UnsubView({ onGo }: { onGo: (v: "sort") => void }) {
  const { state } = useStore();
  const services = state?.services ?? [];
  const list = useMemo(
    () => services.filter((s) => s.decision === "unsubscribe").sort((a, b) => b.count - a.count),
    [services],
  );
  const open = list.filter((s) => !s.unsub_done);
  const done = list.filter((s) => s.unsub_done);
  const [limit, setLimit] = useState(PAGE);
  const shown = [...open, ...done].slice(0, limit);

  const prevOpen = useRef(open.length);
  useEffect(() => {
    if (prevOpen.current > 0 && open.length === 0) celebrate("finish");
    prevOpen.current = open.length;
  }, [open.length]);

  if (!state) return null;

  return (
    <main className="mx-auto max-w-3xl px-4 pb-24 sm:px-6">
      <div className="flex flex-wrap items-baseline gap-x-4 gap-y-1 py-6">
        <h1 className="font-display text-[26px] font-semibold">Отписка</h1>
        <p className="text-muted">
          {list.length > 0 ? (
            <>
              Готово <span className="text-text tabular">{fmt(done.length)}</span> из <span className="tabular">{fmt(list.length)}</span>
            </>
          ) : (
            "Пока пусто"
          )}
        </p>
      </div>

      {list.length > 0 && (
        <p className="mb-5 max-w-prose text-[14px] text-muted">
          «Отписаться» открывает ссылку отписки из самого свежего письма сервиса — без захода в Gmail. Такая кнопка есть
          только у сервисов, где аккаунт точно ваш: переход по ссылке сообщает отправителю, что адрес живой. После отписки
          отметьте сервис как готовый.
        </p>
      )}

      {list.length === 0 && (
        <div className="flex flex-col items-center gap-3 rounded-[28px] border border-dashed border-line p-10 text-center">
          <div className="text-[40px]" aria-hidden>📭</div>
          <h2 className="font-display text-[20px] font-semibold">Здесь появятся сервисы, помеченные «Отписаться»</h2>
          <button onClick={() => onGo("sort")} className="rounded-xl border border-line px-4 py-2 hover:border-mist">
            К сортировке
          </button>
        </div>
      )}

      <ul className="flex flex-col gap-2">
        <AnimatePresence initial={false}>
          {shown.map((s) => (
            <UnsubItem key={s.domain} service={s} />
          ))}
        </AnimatePresence>
      </ul>
      {list.length > limit && (
        <button onClick={() => setLimit((n) => n + PAGE * 2)} className="mt-3 w-full rounded-xl border border-line py-2 text-muted hover:text-text">
          Показать ещё ({fmt(list.length - limit)})
        </button>
      )}
    </main>
  );
}

const WARNING_TITLE: Record<"spam" | "unconfirmed", string> = {
  spam: "Письма этого отправителя попадали в «Спам». Переход по ссылке отписки подтвердит, что адрес живой, — писем станет больше. Лучше пометить письма как спам в Gmail.",
  unconfirmed: "Аккаунт здесь не подтверждён. Переход по ссылке отписки может подтвердить адрес спамерам. Надёжнее пометить письма как спам или настроить фильтр в Gmail.",
};

function UnsubItem({ service: s }: { service: Service }) {
  const { update } = useStore();
  const [opened, setOpened] = useState(false);
  const done = s.unsub_done;
  const u = s.unsubscribe;
  return (
    <motion.li
      layout
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      className={`flex flex-wrap items-center gap-x-4 gap-y-2 rounded-2xl border px-4 py-3 transition-colors ${
        done ? "border-line/50 bg-transparent" : "border-line bg-bg-2"
      }`}
    >
      <label className="flex min-w-0 flex-1 cursor-pointer items-center gap-3.5">
        <input
          type="checkbox"
          checked={done}
          onChange={(e) => update(s, { unsub_done: e.target.checked })}
          className="h-5 w-5 shrink-0 cursor-pointer accent-[var(--keep)]"
        />
        <span className={done ? "opacity-50" : undefined}>
          <Avatar service={s} size={36} />
        </span>
        <span className="min-w-0">
          <span className={`block truncate font-medium ${done ? "text-muted line-through decoration-faint" : ""}`}>{s.name}</span>
          <span className="block truncate text-[13px] text-faint">
            {s.domain}
            {s.count > 0 && <> · {fmt(s.count)} {plural(s.count, "письмо", "письма", "писем")} · последнее {fmtDate(s.last)}</>}
          </span>
        </span>
      </label>
      {!done && (
        <div className="flex flex-wrap items-center justify-end gap-2 pl-8 text-[13px] sm:pl-0">
          {u.url ? (
            opened ? (
              <button
                onClick={() => update(s, { unsub_done: true })}
                className="rounded-xl bg-keep px-3 py-1.5 text-[14px] font-medium text-bg"
              >
                Готово ✓
              </button>
            ) : (
              <a
                href={u.url}
                target="_blank"
                rel="noreferrer noopener"
                onClick={() => setOpened(true)}
                title={`Откроется ${u.host}${u.date ? ` — ссылка из письма от ${fmtDate(u.date)}` : ""}`}
                className="rounded-xl bg-unsub px-3 py-1.5 text-[14px] font-medium text-bg transition-opacity hover:opacity-90"
              >
                Отписаться <span aria-hidden>↗</span>
              </a>
            )
          ) : u.warning ? (
            <span className="max-w-[16rem] text-del" title={WARNING_TITLE[u.warning]}>
              <span aria-hidden>⚠</span> не нажимать — может подтвердить адрес спамерам
            </span>
          ) : s.has_unsub ? (
            <span className="text-faint" title="В заголовке List-Unsubscribe только адрес mailto:">отписка только письмом</span>
          ) : (
            <span className="text-faint" title="В письмах нет заголовка List-Unsubscribe">без ссылки отписки</span>
          )}
          <a
            href={s.links.gmail}
            target="_blank"
            rel="noreferrer noopener"
            className="rounded-xl border border-line px-3 py-1.5 text-[14px] text-text transition-colors hover:border-unsub"
          >
            Письма в Gmail <span aria-hidden>↗</span>
          </a>
        </div>
      )}
      {!done && u.warning && (
        <p className="w-full pl-[3.35rem] text-[12px] text-faint">
          {u.warning === "spam"
            ? `Письма этого отправителя попадали в «Спам» (${fmt(u.spam)}). Надёжнее пометить их как спам в Gmail.`
            : "Аккаунт здесь не подтверждён. Надёжнее пометить письма как спам или настроить фильтр в Gmail."}
        </p>
      )}
      {!done && u.url && (
        <p className="w-full pl-[3.35rem] text-[12px] text-faint">
          {opened ? "Подтвердили отписку на странице сервиса? Нажмите «Готово». " : ""}
          Ссылка ведёт на {u.host}
          {u.date && `, из письма от ${fmtDate(u.date)}`}
        </p>
      )}
    </motion.li>
  );
}
