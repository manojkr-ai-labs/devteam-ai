const MONTHS = [
  "Jan",
  "Feb",
  "Mar",
  "Apr",
  "May",
  "Jun",
  "Jul",
  "Aug",
  "Sep",
  "Oct",
  "Nov",
  "Dec",
] as const;

const MINUTE_MS = 60_000;
const DAY_MS = 86_400_000;

export function shortId(id: string): string {
  return id.slice(0, 6);
}

export function relativeTime(isoUtc: string, now: Date = new Date()): string {
  const then = new Date(isoUtc);
  if (Number.isNaN(then.getTime())) return "";

  const delta = now.getTime() - then.getTime();
  if (delta >= 0 && delta < 60 * MINUTE_MS) {
    return `${Math.floor(delta / MINUTE_MS)}m`;
  }

  if (isUtcYesterday(then, now)) return "yesterday";
  return shortDate(then, now);
}

function isUtcYesterday(then: Date, now: Date): boolean {
  const startToday = Date.UTC(
    now.getUTCFullYear(),
    now.getUTCMonth(),
    now.getUTCDate(),
  );
  const startThen = Date.UTC(
    then.getUTCFullYear(),
    then.getUTCMonth(),
    then.getUTCDate(),
  );
  return startToday - startThen === DAY_MS;
}

function shortDate(then: Date, now: Date): string {
  const day = then.getUTCDate();
  const month = MONTHS[then.getUTCMonth()];
  const year = then.getUTCFullYear();
  if (year === now.getUTCFullYear()) return `${day} ${month}`;
  return `${day} ${month} ${year}`;
}
