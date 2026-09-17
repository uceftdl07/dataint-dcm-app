/**
 * Colour rules shared by the compute charts, kept in one module so the three of them
 * cannot drift apart. Two ideas only, and they are not interchangeable:
 *
 * - **A magnitude gets one hue.** A ranking or a coverage matrix is read by intensity,
 *   so `sequentialFill` ramps the single brand hue. Eleven surfaces get eleven
 *   intensities, never eleven colours: a categorical palette laid over an ordered
 *   quantity invites the reader to look for a meaning in the hues that is not there.
 * - **A category gets a colour pinned to the entity.** `CATEGORICAL_FILLS` is indexed by
 *   the caller from a closed vocabulary, never by rank — filtering one series out must
 *   not repaint the survivors.
 */

/** Where the sequential ramp starts, so a near-zero value is still a visible mark. */
const RAMP_FLOOR_PCT = 10;

/**
 * Where the ramp stops when the value is printed **on** the fill.
 *
 * The ramp runs between `--tdf-blue-subtle` and `--tdf-blue`, and those two swap
 * lightness between themes (subtle is near-white in light, near-black in dark). A fill
 * capped at 65 % keeps `text-foreground` above a 3:1 contrast on both, which a fill
 * reaching the full brand blue would not — and flipping the text colour mid-ramp would
 * only move the problem to the middle of the scale.
 */
const RAMP_CEILING_ON_FILL_PCT = 65;

/** Ceiling when nothing is printed on the fill (a bar with its label outside). */
export const RAMP_CEILING_STANDALONE_PCT = 100;

export function sequentialFill(
  ratio: number | null | undefined,
  ceilingPct: number = RAMP_CEILING_ON_FILL_PCT
): string {
  return `color-mix(in oklch, var(--tdf-blue) ${sequentialIntensity(
    ratio,
    ceilingPct
  )}%, var(--tdf-blue-subtle))`;
}

/**
 * The ramp position, in percent of the brand hue — the number behind `sequentialFill`.
 *
 * Exposed because `color-mix()` is not parsed by jsdom: a test asserting the encoding is
 * sequential reads this figure from a `data-` attribute instead of a computed colour.
 */
export function sequentialIntensity(
  ratio: number | null | undefined,
  ceilingPct: number = RAMP_CEILING_ON_FILL_PCT
): number {
  const value = ratio == null || Number.isNaN(Number(ratio)) ? 0 : Number(ratio);
  const clamped = Math.min(Math.max(value, 0), 1);
  return Math.round(RAMP_FLOOR_PCT + clamped * (ceilingPct - RAMP_FLOOR_PCT));
}

/** Text colour that stays readable over `sequentialFill` on both themes. */
export const SEQUENTIAL_TEXT_CLASS = 'text-foreground';

/**
 * Twelve fills, six hues at two intensities — enough to pin every member of a closed
 * vocabulary of a dozen values to a colour of its own.
 *
 * The order is stable and part of the contract: a caller pins an entity to an index
 * once, and that index is what keeps the entity's colour across windows, filters and
 * refreshes. Nothing here reads a rank.
 */
const CATEGORICAL_HUES = [
  '--tdf-blue',
  '--tdf-teal',
  '--tdf-purple',
  '--tdf-pink',
  '--tdf-green',
  '--tdf-grey',
] as const;

export const CATEGORICAL_FILLS: readonly string[] = [
  ...CATEGORICAL_HUES.map((hue) => `var(${hue})`),
  ...CATEGORICAL_HUES.map((hue) => `color-mix(in oklch, var(${hue}) 55%, var(--card-background))`),
];

/** The fill at `index`, wrapping around rather than rendering an undefined colour. */
export function categoricalFill(index: number): string {
  const count = CATEGORICAL_FILLS.length;
  return CATEGORICAL_FILLS[((index % count) + count) % count]!;
}
