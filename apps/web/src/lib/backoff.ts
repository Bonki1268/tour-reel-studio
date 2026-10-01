// SSE 重連退避：1、2、4、8 秒，之後每 15 秒；連線成功後歸零（spec 0016 R-005）

const STEPS = [1, 2, 4, 8];
const MAX_SECONDS = 15;

export function createBackoff(): { next(): number; reset(): void } {
  let attempt = 0;
  return {
    next() {
      const delay = STEPS[attempt] ?? MAX_SECONDS;
      attempt += 1;
      return delay;
    },
    reset() {
      attempt = 0;
    },
  };
}
