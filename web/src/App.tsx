import { AnimatePresence, motion } from "motion/react";
import { useEffect, useState } from "react";
import { Toasts } from "./components/Toasts";
import { TopBar, type View } from "./components/TopBar";
import { useStore } from "./store";
import { Dashboard } from "./views/Dashboard";
import { DeleteView } from "./views/Delete";
import { SortView } from "./views/Sort";
import { UnsubView } from "./views/Unsub";

const VIEWS: View[] = ["sort", "delete", "unsub", "dash"];

function viewFromHash(): View {
  const h = window.location.hash.slice(1) as View;
  return VIEWS.includes(h) ? h : "sort";
}

type Theme = "dark" | "light";

function initialTheme(): Theme {
  try {
    return localStorage.getItem("vanish.theme") === "light" ? "light" : "dark";
  } catch {
    return "dark";
  }
}

export function App() {
  const { state, error, reload } = useStore();
  const [view, setView] = useState<View>(viewFromHash);
  const [theme, setTheme] = useState<Theme>(initialTheme);

  useEffect(() => {
    const onHash = () => setView(viewFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    try {
      localStorage.setItem("vanish.theme", theme);
    } catch {
      /* тема — не критично */
    }
  }, [theme]);

  const go = (v: View) => {
    if (window.location.hash !== `#${v}`) window.location.hash = v;
    setView(v);
    window.scrollTo({ top: 0 });
  };

  if (!state) {
    return (
      <div className="grid min-h-dvh place-items-center p-6 text-center">
        {error ? (
          <div className="flex max-w-md flex-col items-center gap-3">
            <p className="font-display text-[20px] font-semibold">Нет связи с Vanish</p>
            <p className="text-muted">{error}. Проверьте, что сервер запущен: <code>python -m vanish</code></p>
            <button onClick={reload} className="rounded-xl border border-line px-4 py-2 hover:border-mist">Повторить</button>
          </div>
        ) : (
          <p className="animate-pulse font-display text-[20px] text-muted">Vanish</p>
        )}
      </div>
    );
  }

  return (
    <>
      <TopBar view={view} onView={go} theme={theme} onTheme={() => setTheme((t) => (t === "dark" ? "light" : "dark"))} />
      <AnimatePresence mode="wait" initial={false}>
        <motion.div
          key={view}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0, transition: { duration: 0.12 } }}
          transition={{ duration: 0.2 }}
        >
          {view === "sort" && <SortView onGo={go} />}
          {view === "delete" && <DeleteView onGo={go} />}
          {view === "unsub" && <UnsubView onGo={go} />}
          {view === "dash" && <Dashboard onGo={go} />}
        </motion.div>
      </AnimatePresence>
      <Toasts />
    </>
  );
}
