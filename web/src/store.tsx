import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api } from "./api";
import { celebrate } from "./celebrate";
import { DECISION_LABEL, plural } from "./lib";
import type { Achievement, AppState, BulkAction, Decision, MutationResult, Service, ServiceFields, UndoTarget } from "./types";

export interface Toast {
  id: number;
  kind: "achievement" | "level" | "error" | "info";
  title: string;
  text?: string;
  icon?: string;
}

interface Store {
  state: AppState | null;
  error: string | null;
  toasts: Toast[];
  canUndo: boolean;
  /** Что отменит следующее «Отменить» — по нему карточка возвращается сразу, не дожидаясь сервера. */
  undoTarget: UndoTarget | null;
  decide: (s: Service, decision: Decision | null) => void;
  update: (s: Service, fields: ServiceFields) => void;
  undo: (optimistic?: boolean) => Promise<string | null>;
  bulk: (action: BulkAction) => Promise<void>;
  add: (domain: string, name: string, decision: Decision | null) => Promise<boolean>;
  importProgress: (file: File) => Promise<void>;
  reload: () => Promise<void>;
  dismiss: (id: number) => void;
  notify: (t: Omit<Toast, "id">) => void;
}

const Ctx = createContext<Store | null>(null);

export function useStore(): Store {
  const s = useContext(Ctx);
  if (!s) throw new Error("Store is not ready");
  return s;
}

let toastId = 0;

export function StoreProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AppState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [canUndo, setCanUndo] = useState(false);
  const [undoTarget, setUndoTarget] = useState<UndoTarget | null>(null);
  // Запросы идут строго по очереди: быстрые нажатия не обгоняют друг друга.
  const queue = useRef<Promise<unknown>>(Promise.resolve());
  const levelRef = useRef(0);

  const notify = useCallback((t: Omit<Toast, "id">) => {
    const id = ++toastId;
    setToasts((list) => [...list.slice(-3), { ...t, id }]);
    window.setTimeout(() => setToasts((list) => list.filter((x) => x.id !== id)), t.kind === "error" ? 6000 : 4500);
  }, []);

  const dismiss = useCallback((id: number) => setToasts((list) => list.filter((x) => x.id !== id)), []);

  const reload = useCallback(async () => {
    try {
      const s = await api.state();
      setState(s);
      levelRef.current = s.game.level;
      setCanUndo(s.meta.can_undo);
      setUndoTarget(s.meta.undo_target);
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const applyResult = useCallback(
    (r: MutationResult, removed?: string) => {
      if (levelRef.current && r.game.level > levelRef.current) {
        notify({ kind: "level", icon: "✦", title: `Уровень ${r.game.level}: ${r.game.name}`, text: "Новый уровень" });
        celebrate("level");
      }
      levelRef.current = r.game.level;
      setState((prev) => {
        if (!prev) return prev;
        let services = prev.services;
        if (removed) services = services.filter((s) => s.domain !== removed);
        if (r.service) {
          const svc = r.service;
          const exists = services.some((s) => s.domain === svc.domain);
          services = exists ? services.map((s) => (s.domain === svc.domain ? svc : s)) : [...services, svc];
        }
        return { ...prev, services, game: r.game };
      });
      setCanUndo(r.can_undo);
      setUndoTarget(r.undo_target);
      r.new_achievements.forEach((a: Achievement, i) => {
        window.setTimeout(() => {
          notify({ kind: "achievement", icon: a.icon, title: a.title, text: a.description });
          celebrate("achievement");
        }, i * 400);
      });
    },
    [notify],
  );

  const run = useCallback(
    (fn: () => Promise<MutationResult>, removed?: string) => {
      const p = queue.current.then(fn).then(
        (r) => {
          applyResult(r, removed);
          return r;
        },
        (e: Error) => {
          notify({ kind: "error", title: "Не удалось сохранить", text: e.message });
          reload();
          return null;
        },
      );
      queue.current = p;
      return p;
    },
    [applyResult, notify, reload],
  );

  const patchLocal = useCallback((domain: string, patch: Partial<Service>) => {
    setState((prev) =>
      prev ? { ...prev, services: prev.services.map((s) => (s.domain === domain ? { ...s, ...patch } : s)) } : prev,
    );
  }, []);

  const decide = useCallback(
    (s: Service, decision: Decision | null) => {
      patchLocal(s.domain, {
        decision,
        status: decision === "delete" ? "pending" : null,
        unsub_done: decision === "unsubscribe" ? s.unsub_done : false,
      });
      setCanUndo(true);
      setUndoTarget({
        kind: "decide",
        domain: s.domain,
        before: { decision: s.decision, status: s.status, unsub_done: s.unsub_done },
      });
      run(() => api.decide(s.domain, decision));
    },
    [patchLocal, run],
  );

  const update = useCallback(
    (s: Service, fields: ServiceFields) => {
      patchLocal(s.domain, fields as Partial<Service>);
      // Заметка и название не отменяются через Z — цель отмены не меняется.
      if (Object.keys(fields).some((k) => k !== "note" && k !== "name")) {
        setCanUndo(true);
        setUndoTarget({
          kind: "update",
          domain: s.domain,
          before: { decision: s.decision, status: s.status, unsub_done: s.unsub_done },
        });
      }
      run(() => api.update(s.domain, fields));
    },
    [patchLocal, run],
  );

  const undo = useCallback(async (optimistic = false) => {
    const t = undoTarget;
    if (optimistic && t?.domain && t.before) {
      // Откат сразу на экране; ответ сервера потом лишь подтвердит его.
      patchLocal(t.domain, t.before);
      setUndoTarget(null);
    }
    const r = await run(() => api.undo());
    if (!r) return null;
    if (r.undone?.kind === "add") {
      setState((prev) =>
        prev ? { ...prev, services: prev.services.filter((x) => x.domain !== r.undone!.domain) } : prev,
      );
      notify({ kind: "info", icon: "↶", title: `Отменено добавление ${r.undone.domain}` });
      return null;
    }
    if (r.undone?.kind === "bulk") {
      await reload();
      const n = r.undone.count;
      notify({ kind: "info", icon: "↶", title: `Отменено для ${n} ${plural(n, "сервиса", "сервисов", "сервисов")}` });
      return null;
    }
    return r.undone?.domain ?? null;
  }, [run, reload, notify, undoTarget, patchLocal]);

  const bulk = useCallback(
    async (action: BulkAction) => {
      const r = await run(() => api.bulk(action));
      if (!r?.bulk) return;
      await reload();
      const { count, decision } = r.bulk;
      notify({
        kind: "info",
        icon: decision === "unsubscribe" ? "↓" : "→",
        title: `${DECISION_LABEL[decision]}: ${count} ${plural(count, "сервис", "сервиса", "сервисов")}`,
        text: "Передумали — нажмите Z, отменится всё разом",
      });
    },
    [run, reload, notify],
  );

  const add = useCallback(
    async (domain: string, name: string, decision: Decision | null) => {
      const r = await run(() => api.add(domain, name, decision));
      if (r?.service) notify({ kind: "info", icon: "＋", title: `Добавлено: ${r.service.name}` });
      return !!r;
    },
    [run, notify],
  );

  const importProgress = useCallback(
    async (file: File) => {
      try {
        const data = JSON.parse(await file.text());
        const r = await api.importProgress(data);
        await reload();
        notify({ kind: "info", icon: "⇅", title: "Прогресс загружен", text: `Решений: ${r.imported}` });
      } catch (e) {
        notify({ kind: "error", title: "Не удалось загрузить прогресс", text: (e as Error).message });
      }
    },
    [reload, notify],
  );

  const value = useMemo(
    () => ({ state, error, toasts, canUndo, undoTarget, decide, update, undo, bulk, add, importProgress, reload, dismiss, notify }),
    [state, error, toasts, canUndo, undoTarget, decide, update, undo, bulk, add, importProgress, reload, dismiss, notify],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
