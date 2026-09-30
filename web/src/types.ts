export type Decision = "delete" | "keep" | "unsubscribe" | "later" | "skip";
export type DeleteStatus = "pending" | "deleted" | "failed" | "later";
export type Confidence = "sure" | "likely" | "newsletter" | "personal";
export type RiskLevel = "high" | "medium" | "low";
export type BulkAction = "unsub_low" | "skip_low";

export interface Breach {
  name: string;
  title: string;
  date: string;
  pwn_count: number;
  data: string[];
  data_ru: string[];
  verified: boolean;
}

export interface Risk {
  level: RiskLevel;
  score: number;
  category: string;
  category_label: string;
  category_source: "domain" | "topic" | "default";
  purchases: number;
  breached: boolean;
  breach_after_signup: boolean;
  breaches: Breach[];
  reasons: string[];
}

export interface RiskSummary {
  index: number;
  high_total: number;
  high_open: number;
  breached_open: number;
  top_total: number;
  top_open: number;
}

export interface Service {
  domain: string;
  name: string;
  manual: boolean;
  decision: Decision | null;
  status: DeleteStatus | null;
  unsub_done: boolean;
  note: string;
  decided_at: string | null;
  finished_at: string | null;
  count: number;
  first: string | null;
  last: string | null;
  first_year: number | null;
  has_unsub: boolean;
  strong: number;
  weak: number;
  sent_to: number;
  confidence: Confidence;
  samples: string[];
  google_linked: boolean;
  /** Прямая отписка: url есть, только если нажимать безопасно (аккаунт подтверждён, спама не было). */
  unsubscribe: {
    url: string | null;
    host: string | null;
    date: string | null;
    warning: "spam" | "unconfirmed" | null;
    spam: number;
  };
  difficulty: string;
  risk: Risk;
  jdm: { name: string; url: string; notes: string; email: string } | null;
  links: {
    site: string;
    delete: string | null;
    gmail: string;
    google_connections: string;
    search_delete: string;
  };
}

export interface Achievement {
  id: string;
  title: string;
  description: string;
  icon: string;
  unlocked_at?: string | null;
}

export interface Game {
  xp: number;
  level: number;
  name: string;
  xp_start: number;
  xp_next: number | null;
  next_name: string | null;
  streak: number;
  today: number;
  progress: number;
  risk: RiskSummary;
  achievements: Achievement[];
}

export interface Meta {
  last_import: string | null;
  last_import_file: string | null;
  jdm_count: number;
  breaches_count: number;
  top_n: number;
  can_undo: boolean;
  undo_target: UndoTarget | null;
  demo: boolean;
}

/** Что отменит следующее «Отменить» (domain и before — только для одиночных действий). */
export interface UndoTarget {
  kind: string;
  domain: string | null;
  before: { decision: Decision | null; status: DeleteStatus | null; unsub_done: boolean } | null;
}

export interface AppState {
  services: Service[];
  game: Game;
  meta: Meta;
}

export interface MutationResult {
  service: Service | null;
  game: Game;
  new_achievements: Achievement[];
  can_undo: boolean;
  undo_target: UndoTarget | null;
  undone?:{ kind: string; domain: string; count: number };
  bulk?: { action: BulkAction; decision: Decision; count: number };
}

export type ServiceFields = Partial<{
  decision: Decision | null;
  status: DeleteStatus | null;
  unsub_done: boolean;
  note: string;
  name: string;
}>;
