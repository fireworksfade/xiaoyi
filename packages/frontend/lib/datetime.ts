const EXPLICIT_TIMEZONE = /(Z|[+-]\d{2}:?\d{2})$/i;

/** Parse API timestamps, whose timezone-less values are stored UTC timestamps. */
export function parseApiDate(value: string | null | undefined): Date | null {
  if (!value) return null;
  const text = value.trim();
  const date = new Date(EXPLICIT_TIMEZONE.test(text) ? text : `${text}Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatApiDateTime(value: string | null | undefined): string {
  return parseApiDate(value)?.toLocaleString('zh-CN') ?? '—';
}
