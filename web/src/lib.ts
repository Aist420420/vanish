import type { BulkAction, Confidence, Decision, DeleteStatus, RiskLevel, Service } from "./types";

export const CONFIDENCE_LABEL: Record<Confidence, string> = {
  sure: "Точно аккаунт",
  likely: "Вероятно аккаунт",
  newsletter: "Только рассылка",
  personal: "Переписка",
};

export const CONFIDENCE_ORDER: Record<Confidence, number> = { sure: 0, likely: 1, newsletter: 2, personal: 3 };

export const DIFFICULTY_LABEL: Record<string, string> = {
  easy: "Удалить легко",
  medium: "Средне",
  hard: "Сложно",
  limited: "Частично",
  impossible: "Невозможно",
  "": "Сложность неизвестна",
};

export const DIFFICULTY_ORDER = ["easy", "medium", "", "hard", "limited", "impossible"];

export const DIFFICULTY_COLOR: Record<string, string> = {
  easy: "text-keep",
  medium: "text-unsub",
  hard: "text-del",
  limited: "text-del",
  impossible: "text-del",
  "": "text-faint",
};

export const DECISION_LABEL: Record<Decision, string> = {
  delete: "Удалить",
  keep: "Оставить",
  unsubscribe: "Отписаться",
  later: "Отложено",
  skip: "Пропущено",
};

export const DECISION_COLOR: Record<Decision, string> = {
  delete: "var(--del)",
  keep: "var(--keep)",
  unsubscribe: "var(--unsub)",
  later: "var(--later)",
  skip: "var(--faint)",
};

export const RISK_LABEL: Record<RiskLevel, string> = {
  high: "Высокий риск",
  medium: "Средний риск",
  low: "Низкий риск",
};

export const RISK_SHORT: Record<RiskLevel, string> = { high: "Высокий", medium: "Средний", low: "Низкий" };

export const RISK_COLOR: Record<RiskLevel, string> = {
  high: "var(--risk-high)",
  medium: "var(--risk-mid)",
  low: "var(--risk-low)",
};

export const RISK_ORDER: Record<RiskLevel, number> = { high: 0, medium: 1, low: 2 };

/** Тот же порядок, что на сервере: высокий риск первым, внутри — утечки, затем балл и число писем. */
export function byRisk(a: Service, b: Service): number {
  return (
    RISK_ORDER[a.risk.level] - RISK_ORDER[b.risk.level] ||
    Number(b.risk.breached) - Number(a.risk.breached) ||
    b.risk.score - a.risk.score ||
    b.count - a.count ||
    a.domain.localeCompare(b.domain)
  );
}

/** «Главное за 30 минут»: самые рискованные сервисы. Набор не меняется от моих решений. */
export function topServices(services: Service[], n: number): Service[] {
  return services.filter(isTracked).sort(byRisk).slice(0, n);
}

/** Риск снят: удалён, оставлен/пропущен осознанно или отписка выполнена. */
export function isRiskClosed(s: Service): boolean {
  if (s.decision === "keep" || s.decision === "skip") return true;
  if (s.decision === "delete") return s.status === "deleted";
  if (s.decision === "unsubscribe") return s.unsub_done;
  return false;
}

export function isOpen(s: Service): boolean {
  return s.decision === null || s.decision === "later";
}

/** Кого затронет массовое действие — то же правило, что на сервере. */
export function bulkTargets(services: Service[], action: BulkAction): Service[] {
  return services.filter(
    (s) =>
      isTracked(s) &&
      isOpen(s) &&
      s.risk.level === "low" &&
      (action === "skip_low" || s.has_unsub || s.confidence === "newsletter"),
  );
}

export const STATUS_LABEL: Record<DeleteStatus, string> = {
  pending: "В очереди",
  deleted: "Удалено",
  failed: "Не получилось",
  later: "Позже",
};

export function plural(n: number, one: string, few: string, many: string): string {
  const mod10 = n % 10;
  const mod100 = n % 100;
  if (mod10 === 1 && mod100 !== 11) return one;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return few;
  return many;
}

export function fmt(n: number): string {
  return n.toLocaleString("ru-RU");
}

export function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  // Дата без времени — местный день; полная метка (UTC) — переводим в местное время.
  const d = new Date(iso + (iso.length === 10 ? "T00:00:00" : ""));
  return d.toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" });
}

/** Короткая дата для тесных мест: «13 февр. 2019». */
export function fmtDateShort(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso + (iso.length === 10 ? "T00:00:00" : ""));
  return d.toLocaleDateString("ru-RU", { day: "numeric", month: "short", year: "numeric" }).replace(/\s*г\.$/, "");
}

function hash(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

/** Цвет аватара-заглушки из домена: стабильный, спокойный, читаемый в обеих темах. */
export function avatarColor(domain: string): { bg: string; fg: string } {
  const hue = hash(domain) % 360;
  return {
    bg: `oklch(0.42 0.11 ${hue})`,
    fg: `oklch(0.95 0.04 ${hue})`,
  };
}

export function initial(s: Service): string {
  const src = s.name || s.domain;
  const ch = [...src].find((c) => /[\p{L}\p{N}]/u.test(c));
  return (ch || "?").toUpperCase();
}

/** Сервис участвует в игре (личная переписка — нет, пока её не разобрали вручную). */
export function isTracked(s: Service): boolean {
  return s.confidence !== "personal" || s.decision !== null || s.manual;
}

export function isDeleteOpen(s: Service): boolean {
  return s.decision === "delete" && s.status !== "deleted" && s.status !== "failed";
}

export type SortOrder = "risk" | "confidence" | "count" | "oldest" | "newest" | "name" | "easy";

export const SORT_LABEL: Record<SortOrder, string> = {
  risk: "Сначала рискованные",
  confidence: "Сначала точные аккаунты",
  count: "Больше писем",
  oldest: "Сначала старые",
  newest: "Сначала свежие",
  name: "По алфавиту",
  easy: "Легко удалить — первыми",
};

export function sortServices(list: Service[], order: SortOrder): Service[] {
  const arr = [...list];
  const byCount = (a: Service, b: Service) => b.count - a.count || a.domain.localeCompare(b.domain);
  switch (order) {
    case "risk":
      return arr.sort(byRisk);
    case "confidence":
      return arr.sort((a, b) => CONFIDENCE_ORDER[a.confidence] - CONFIDENCE_ORDER[b.confidence] || byCount(a, b));
    case "count":
      return arr.sort(byCount);
    case "oldest":
      return arr.sort((a, b) => (a.first || "9999").localeCompare(b.first || "9999") || byCount(a, b));
    case "newest":
      return arr.sort((a, b) => (b.last || "").localeCompare(a.last || "") || byCount(a, b));
    case "name":
      return arr.sort((a, b) => a.name.localeCompare(b.name, "ru"));
    case "easy": {
      const rank = (s: Service) => (s.jdm ? DIFFICULTY_ORDER.indexOf(s.difficulty) : 99);
      return arr.sort((a, b) => rank(a) - rank(b) || byCount(a, b));
    }
  }
}
