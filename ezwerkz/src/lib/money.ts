const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const usdWhole = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

/** Format integer cents as "$1,234.56". */
export function formatCents(cents: number): string {
  return usd.format(cents / 100);
}

/** Format integer cents as "$1,235" (no decimals) for headline numbers. */
export function formatCentsWhole(cents: number): string {
  return usdWhole.format(cents / 100);
}

export function dollarsToCents(dollars: number): number {
  return Math.round(dollars * 100);
}
