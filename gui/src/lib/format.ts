// Display helpers. Dates arrive as YYYY-MM-DD and times as 24-hour HH:MM.

function parseDate(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}

const monthDay = new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric" });
const monthDayYear = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
  year: "numeric",
});
const weekdayShort = new Intl.DateTimeFormat(undefined, { weekday: "short" });
const money = new Intl.NumberFormat(undefined, { style: "currency", currency: "USD" });

/** "Nov 15 – Nov 28, 2026" */
export function periodRange(start: string, end: string): string {
  return `${monthDay.format(parseDate(start))} – ${monthDayYear.format(parseDate(end))}`;
}

/** "Mon" */
export function weekday(iso: string): string {
  return weekdayShort.format(parseDate(iso));
}

/** "Nov 16" */
export function shortDate(iso: string): string {
  return monthDay.format(parseDate(iso));
}

/** "14:00" -> "2:00 PM" */
export function clock(hhmm: string): string {
  const [h, m] = hhmm.split(":").map(Number);
  const suffix = h < 12 ? "AM" : "PM";
  return `${h % 12 || 12}:${String(m).padStart(2, "0")} ${suffix}`;
}

export function usd(amount: number): string {
  return money.format(amount);
}

/** 1.25 -> "1.25 h", 2 -> "2 h" */
export function hours(value: number): string {
  return `${Number(value.toFixed(2))} h`;
}

/** 71 -> "1h 11m" */
export function minutes(total: number): string {
  const h = Math.floor(total / 60);
  const m = total % 60;
  if (!h) return `${m}m`;
  return m ? `${h}h ${m}m` : `${h}h`;
}

/** Last path component, for showing a long path compactly. */
export function basename(path: string): string {
  return path.split(/[\\/]/).pop() || path;
}
