// 重生預算判斷（spec 0016 R-004）；點數以字串傳遞（後端 Decimal）

export function remaining(costCap: string | null, spent: string): number | null {
  throw new Error("not implemented");
}

export function needsConfirmation(cost: string, remainingBudget: number | null): boolean {
  throw new Error("not implemented");
}

export function newCap(spent: string, cost: string): string {
  throw new Error("not implemented");
}
