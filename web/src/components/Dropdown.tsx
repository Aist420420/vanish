import { useCallback, useEffect, useId, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { Popover } from "./Popover";

export function Chevron({ open }: { open: boolean }) {
  return (
    <svg
      aria-hidden
      viewBox="0 0 12 12"
      className={`size-3 shrink-0 text-faint transition-transform duration-150 ${open ? "rotate-180" : ""}`}
    >
      <path d="M2.5 4.5 6 8l3.5-3.5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/**
 * Выпадающий список в стиле приложения вместо системного <select>.
 * Стрелки/Enter/Escape работают внутри меню и не долетают до горячих клавиш сортировки.
 */
export function Dropdown({ value, options, onChange, label, ariaLabel, colors, variant = "field", align = "left" }: {
  value: string;
  options: [string, string][];
  onChange: (v: string) => void;
  label?: ReactNode;
  ariaLabel?: string;
  colors?: Record<string, string>;
  variant?: "field" | "chip";
  align?: "left" | "right";
}) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const uid = useId();
  const button = useRef<HTMLButtonElement>(null);
  const list = useRef<HTMLUListElement>(null);
  const current = options.find(([v]) => v === value);
  const close = useCallback(() => setOpen(false), []);

  useEffect(() => {
    if (!open) return;
    setActive(Math.max(0, options.findIndex(([v]) => v === value)));
    // Фокус в меню — чтобы стрелки листали пункты, а не карточки.
    requestAnimationFrame(() => list.current?.focus());
  }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  const pick = (v: string) => {
    setOpen(false);
    if (v !== value) onChange(v);
    button.current?.focus();
  };

  const onListKey = (e: KeyboardEvent) => {
    e.stopPropagation();
    if (e.key === "ArrowDown") setActive((i) => (i + 1) % options.length);
    else if (e.key === "ArrowUp") setActive((i) => (i - 1 + options.length) % options.length);
    else if (e.key === "Home") setActive(0);
    else if (e.key === "End") setActive(options.length - 1);
    else if (e.key === "Enter" || e.key === " ") pick(options[active][0]);
    else if (e.key === "Tab") setOpen(false);
    else return;
    e.preventDefault();
  };

  const valueColor = colors?.[value];
  const trigger =
    variant === "field"
      ? "gap-2 rounded-xl border border-line bg-bg-2 px-3 py-1.5 hover:border-mist/50"
      : "gap-1.5 rounded-lg border border-line bg-bg-2 px-2.5 py-1 hover:border-mist/50";

  return (
    <>
      <button
        ref={button}
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={ariaLabel}
        className={`inline-flex items-center text-[14px] whitespace-nowrap transition-colors ${trigger} ${open ? "border-mist/60" : ""}`}
      >
        {label && <span className="text-faint">{label}</span>}
        <span style={{ color: valueColor ?? "var(--text)" }}>{current?.[1] ?? "—"}</span>
        <Chevron open={open} />
      </button>
      <Popover anchor={button} open={open} onClose={close} align={align} className="min-w-44">
        <ul
          ref={list}
          role="listbox"
          tabIndex={-1}
          aria-label={ariaLabel}
          aria-activedescendant={`${uid}-${active}`}
          onKeyDown={onListKey}
          className="max-h-80 overflow-y-auto outline-none"
        >
          {options.map(([v, l], i) => (
            <li
              key={v}
              id={`${uid}-${i}`}
              role="option"
              aria-selected={v === value}
              onPointerEnter={() => setActive(i)}
              onClick={() => pick(v)}
              className={`flex cursor-pointer items-center gap-2 rounded-lg px-2.5 py-1.5 text-[14px] whitespace-nowrap ${
                i === active ? "bg-bg-3" : ""
              }`}
            >
              <span className="w-3.5 shrink-0 text-mist" aria-hidden>{v === value ? "✓" : ""}</span>
              <span style={{ color: colors?.[v] ?? (v === value ? "var(--text)" : "var(--muted)") }}>{l}</span>
            </li>
          ))}
        </ul>
      </Popover>
    </>
  );
}

/** Поле-фильтр с подписью или значком: «Статус  Все ▾». */
export function Select({ label, ariaLabel, value, onChange, options, align }: {
  label: ReactNode;
  ariaLabel?: string;
  value: string;
  onChange: (v: string) => void;
  options: [string, string][];
  align?: "left" | "right";
}) {
  return (
    <Dropdown
      label={label}
      ariaLabel={ariaLabel ?? (typeof label === "string" ? label : undefined)}
      value={value}
      onChange={onChange}
      options={options}
      align={align}
    />
  );
}
