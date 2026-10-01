// 點數顯示：千分位、最多 2 位小數（spec 0015 R-003）

const formatter = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });

export function formatCredits(value: string | number): string {
  const n = typeof value === "number" ? value : Number(value);
  return `${Number.isFinite(n) ? formatter.format(n) : "—"} 點`;
}
