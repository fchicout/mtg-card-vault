export type Currency = 'USD' | 'EUR';

const AMOUNT = /^(-?)(\d+)(?:\.(\d+))?$/;
const SAMPLE = 1234567.89;

/**
 * Formats an exact decimal string from the API ("1234.5") for a locale and currency (FR-PRC-02).
 * The value is never turned into a number: totals can be large and cents must not drift, so only
 * the layout (symbol and its position, separators) comes from Intl and the digits stay as they
 * arrived. Returns null for a missing or unusable value: no price is not zero.
 */
export function formatMoney(
  value: string | null | undefined,
  currency: Currency,
  locale = 'en-US',
): string | null {
  const match = value == null ? null : AMOUNT.exec(value.trim());
  if (!match) {
    return null;
  }
  const [, sign, whole, fraction = ''] = match;
  const cents = fraction.padEnd(2, '0').slice(0, 2);
  const layout = new Intl.NumberFormat(locale, { style: 'currency', currency }).formatToParts(
    SAMPLE,
  );
  const separator = (type: 'group' | 'decimal', fallback: string): string =>
    layout.find((part) => part.type === type)?.value ?? fallback;
  const grouped = group(whole, separator('group', ','));
  const first = layout.findIndex((part) => part.type === 'integer');
  const last = layout.map((part) => part.type).lastIndexOf('fraction');
  const text = (parts: Intl.NumberFormatPart[]): string => parts.map((p) => p.value).join('');
  return `${sign}${text(layout.slice(0, first))}${grouped}${separator('decimal', '.')}${cents}${text(layout.slice(last + 1))}`;
}

/** Digits in groups of three from the right (linear time, no regular expression to backtrack). */
function group(digits: string, separator: string): string {
  const parts: string[] = [];
  for (let end = digits.length; end > 0; end -= 3) {
    parts.unshift(digits.slice(Math.max(0, end - 3), end));
  }
  return parts.join(separator);
}
