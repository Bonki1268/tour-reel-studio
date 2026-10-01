// SSE 重連退避：1、2、4、8 秒，之後每 15 秒；連線成功後歸零（spec 0016 R-005）

export function createBackoff(): { next(): number; reset(): void } {
  throw new Error("not implemented");
}
