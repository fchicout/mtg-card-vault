import { formatMoney } from './money';

describe('formatMoney', () => {
  it.each([
    ['1.5', 'USD', 'en-US', '$1.50'],
    ['0.35', 'USD', 'en-US', '$0.35'],
    ['0', 'USD', 'en-US', '$0.00'],
    ['1234.5', 'EUR', 'en-US', '€1,234.50'],
    ['12344365.44', 'USD', 'en-US', '$12,344,365.44'],
    ['1234.5', 'EUR', 'de-DE', '1.234,50 €'],
    ['9.99', 'EUR', 'fr-FR', '9,99 €'],
    ['-2.00', 'USD', 'en-US', '-$2.00'],
  ] as const)('formats %s %s for %s as %s', (value, currency, locale, expected) => {
    expect(formatMoney(value, currency, locale)).toBe(expected);
  });

  it('keeps digits beyond what a float can hold', () => {
    // 2^53 + 1 and cents: a number would round these.
    expect(formatMoney('9007199254740993.07', 'USD')).toBe('$9,007,199,254,740,993.07');
    expect(formatMoney('0.10', 'USD')).toBe('$0.10');
    expect(formatMoney('0.30', 'USD')).toBe('$0.30');
  });

  it('cuts extra fraction digits instead of rounding by float', () => {
    expect(formatMoney('1.239', 'USD')).toBe('$1.23');
  });

  it.each([null, undefined, '', 'abc', '1,50', '1e3', '--1', ' '])(
    'has no text for %j (no price is not zero)',
    (value) => {
      expect(formatMoney(value, 'USD')).toBeNull();
    },
  );
});
