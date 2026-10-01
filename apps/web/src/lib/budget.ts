// 重生預算判斷（spec 0016 R-004）；點數以字串傳遞（後端 Decimal），以百分之一點計算避免浮點誤差

const cents = (value: string) => Math.round(Number(value) * 100);

export function remaining(costCap: string | null, spent: string): number | null {
  if (costCap === null) return null;
  return (cents(costCap) - cents(spent)) / 100;
}

/** 所需點數超過剩餘預算（或沒有上限資訊）時需要使用者再次確認。 */
export function needsConfirmation(cost: string, remainingBudget: number | null): boolean {
  if (remainingBudget === null) return true;
  return cents(cost) > Math.round(remainingBudget * 100);
}

export function newCap(spent: string, cost: string): string {
  return String((cents(spent) + cents(cost)) / 100);
}
