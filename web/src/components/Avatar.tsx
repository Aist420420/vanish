import { avatarColor, initial } from "../lib";
import type { Service } from "../types";

export function Avatar({ service, size = 44 }: { service: Service; size?: number }) {
  const { bg, fg } = avatarColor(service.domain);
  return (
    <div
      aria-hidden
      className="grid shrink-0 place-items-center font-display font-semibold select-none"
      style={{
        width: size,
        height: size,
        borderRadius: size * 0.3,
        background: bg,
        color: fg,
        fontSize: size * 0.44,
      }}
    >
      {initial(service)}
    </div>
  );
}
