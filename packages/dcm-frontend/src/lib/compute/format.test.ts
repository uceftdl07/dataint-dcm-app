import { describe, expect, it } from 'vitest';
import { formatHours, formatUsd, lastNDaysPeriodIso, todayIsoUtc } from './format';

describe('formatHours', () => {
  it('breaks an hour count into days, hours, minutes and seconds', () => {
    expect(formatHours(137.4823)).toBe('5d 17h 28m 56s');
    expect(formatHours(2.5)).toBe('2h 30m');
  });

  it('omits the components worth zero', () => {
    expect(formatHours(120)).toBe('5d');
    expect(formatHours(2)).toBe('2h');
    expect(formatHours(0.01)).toBe('36s');
    // Composante intermédiaire nulle : elle est omise elle aussi, `1d 0h 0m 10s`
    // n'apprenant rien de plus que `1d 10s`.
    expect(formatHours(24.0028)).toBe('1d 10s');
  });

  it('renders a real zero as 0s, never as a dash', () => {
    // `—` dit « pas de mesure » ; un cluster mesuré à zéro heure d'activité est une
    // mesure, et c'est même le signal que cherche l'onglet Efficiency.
    expect(formatHours(0)).toBe('0s');
  });

  it('returns a dash for a missing or absurd value', () => {
    expect(formatHours(null)).toBe('—');
    expect(formatHours(undefined)).toBe('—');
    expect(formatHours(Number.NaN)).toBe('—');
    expect(formatHours(-3)).toBe('—');
  });
});

describe('formatUsd', () => {
  it('renders two decimals by default', () => {
    expect(formatUsd(1234.567)).toBe('$1,234.57');
    expect(formatUsd(1234)).toBe('$1,234.00');
  });

  it('keeps a sub-dollar cost readable instead of rounding it away', () => {
    // C'est le cas qui motive le défaut à 2 : beaucoup de ressources coûtent moins
    // d'un dollar sur la fenêtre lue, et un arrondi à l'entier les affichait toutes
    // à `$0`, indistinguables d'un coût nul.
    expect(formatUsd(0.42)).toBe('$0.42');
    expect(formatUsd(0.004)).toBe('$0.00');
    expect(formatUsd(0)).toBe('$0.00');
  });

  it('honours a finer request, for a unit cost', () => {
    // Coût DBU et coût par requête : 3 chiffres demandés à l'appel.
    expect(formatUsd(0.1234, 3)).toBe('$0.123');
    // `minimumFractionDigits` reste à 2, le défaut de l'USD.
    expect(formatUsd(0.12, 3)).toBe('$0.12');
  });

  it('returns a dash for a missing value, never $0', () => {
    expect(formatUsd(null)).toBe('—');
    expect(formatUsd(undefined)).toBe('—');
    expect(formatUsd(Number.NaN)).toBe('—');
  });
});

describe('lastNDaysPeriodIso', () => {
  it('counts the end day in the span', () => {
    expect(lastNDaysPeriodIso(30, '2026-09-07')).toEqual({
      period_start: '2026-08-09',
      period_end: '2026-09-07',
    });
    expect(lastNDaysPeriodIso(1, '2026-09-07')).toEqual({
      period_start: '2026-09-07',
      period_end: '2026-09-07',
    });
  });

  it('ends today when no end date is given', () => {
    expect(lastNDaysPeriodIso(7).period_end).toBe(todayIsoUtc());
  });

  it('never inverts the bounds on a degenerate span', () => {
    expect(lastNDaysPeriodIso(0, '2026-09-07')).toEqual({
      period_start: '2026-09-07',
      period_end: '2026-09-07',
    });
  });
});
