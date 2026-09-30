import { CONFIDENCE_LABEL, DIFFICULTY_COLOR, DIFFICULTY_LABEL, fmt, RISK_COLOR, RISK_LABEL } from "../lib";
import type { Confidence, Risk, RiskLevel, Service } from "../types";

const RISK_BARS: Record<RiskLevel, number> = { high: 3, medium: 2, low: 1 };

export function RiskBadge({ risk, compact = false }: { risk: Risk; compact?: boolean }) {
  const color = RISK_COLOR[risk.level];
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[13px] font-medium"
      style={{ color, borderColor: `color-mix(in oklab, ${color} 55%, transparent)`, background: `color-mix(in oklab, ${color} 10%, transparent)` }}
      title={`Балл риска ${risk.score} из 100: ${risk.reasons.join(", ")}`}
    >
      <span className="flex items-end gap-[2px]" aria-hidden>
        {[1, 2, 3].map((i) => (
          <span
            key={i}
            className="w-[3px] rounded-full"
            style={{ height: 3 + i * 3, background: i <= RISK_BARS[risk.level] ? "currentColor" : "var(--line)" }}
          />
        ))}
      </span>
      {compact ? RISK_LABEL[risk.level].split(" ")[0] : RISK_LABEL[risk.level]}
    </span>
  );
}

function breachTitle(risk: Risk): string {
  return risk.breaches
    .map((b) => {
      const what = b.data_ru.slice(0, 5).join(", ");
      return `${b.title}, ${b.date.slice(0, 4)}: ${fmt(b.pwn_count)} аккаунтов${what ? ` — ${what}` : ""}`;
    })
    .join("\n");
}

export function LeakBadge({ risk }: { risk: Risk }) {
  if (!risk.breached) return null;
  const latest = risk.breaches[0];
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full bg-del px-2.5 py-0.5 text-[13px] font-semibold text-bg"
      title={`${breachTitle(risk)}\n${risk.breach_after_signup ? "Утечка случилась, когда вы уже, вероятно, были зарегистрированы." : "Утечка раньше вашего первого письма от сервиса — возможно, вас не задела."}\nИсточник: Have I Been Pwned`}
    >
      <span aria-hidden>⚠</span> утечка{latest?.date ? ` ${latest.date.slice(0, 4)}` : ""}
    </span>
  );
}

const CONF_STYLE: Record<Confidence, string> = {
  sure: "border-mist/50 text-mist-strong",
  likely: "border-line text-text",
  newsletter: "border-line text-muted",
  personal: "border-line text-faint",
};

const CONF_DOTS: Record<Confidence, number> = { sure: 3, likely: 2, newsletter: 1, personal: 0 };

export function ConfidenceBadge({ confidence }: { confidence: Confidence }) {
  const dots = CONF_DOTS[confidence];
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[13px] ${CONF_STYLE[confidence]}`}>
      <span className="flex gap-0.5" aria-hidden>
        {[0, 1, 2].map((i) => (
          <span key={i} className={`h-1.5 w-1.5 rounded-full ${i < dots ? "bg-current" : "bg-line"}`} />
        ))}
      </span>
      {CONFIDENCE_LABEL[confidence]}
    </span>
  );
}

export function DifficultyBadge({ service }: { service: Service }) {
  if (!service.jdm) {
    return <span className="text-[13px] text-faint">Нет в базе JustDeleteMe</span>;
  }
  const d = service.difficulty;
  const level = { easy: 1, medium: 2, hard: 3, limited: 3, impossible: 4 }[d] ?? 0;
  return (
    <span className={`inline-flex items-center gap-1.5 text-[13px] ${DIFFICULTY_COLOR[d]}`}>
      <span className="flex items-end gap-[2px]" aria-hidden>
        {[1, 2, 3, 4].map((i) => (
          <span
            key={i}
            className={`w-[3px] rounded-full ${i <= level ? "bg-current" : "bg-line"}`}
            style={{ height: 4 + i * 2.5 }}
          />
        ))}
      </span>
      {DIFFICULTY_LABEL[d]}
    </span>
  );
}
