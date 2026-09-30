import confetti from "canvas-confetti";

const reduced = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

function palette(): string[] {
  const css = getComputedStyle(document.documentElement);
  return ["--mist", "--keep", "--unsub", "--later", "--del"].map((v) => css.getPropertyValue(v).trim());
}

/** Небольшой праздничный эффект — без перебора. */
export function celebrate(kind: "achievement" | "level" | "finish"): void {
  if (reduced()) return;
  const colors = palette();
  if (kind === "achievement") {
    confetti({ particleCount: 40, spread: 55, startVelocity: 28, origin: { x: 0.85, y: 0.9 }, colors, scalar: 0.8 });
    return;
  }
  if (kind === "level") {
    confetti({ particleCount: 70, spread: 80, origin: { y: 0.2 }, colors, scalar: 0.9 });
    return;
  }
  const end = Date.now() + 700;
  const frame = () => {
    confetti({ particleCount: 5, angle: 60, spread: 50, origin: { x: 0, y: 0.8 }, colors, scalar: 0.9 });
    confetti({ particleCount: 5, angle: 120, spread: 50, origin: { x: 1, y: 0.8 }, colors, scalar: 0.9 });
    if (Date.now() < end) requestAnimationFrame(frame);
  };
  frame();
}
