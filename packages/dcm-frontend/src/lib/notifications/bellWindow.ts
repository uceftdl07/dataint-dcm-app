/** Fixed sliding window for the header bell — independent of header time range. */
export const BELL_WINDOW_DAYS = 90;

export function getBellWindowApiParams(referenceDate: Date = new Date()) {
  const end_date = referenceDate.toISOString().split('T')[0];
  const start = new Date(referenceDate);
  start.setUTCDate(start.getUTCDate() - BELL_WINDOW_DAYS);

  return {
    start_date: start.toISOString().split('T')[0],
    end_date,
  };
}
