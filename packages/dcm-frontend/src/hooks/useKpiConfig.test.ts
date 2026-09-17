import { describe, expect, it } from 'vitest';
import { getKpiThresholdTone } from './useKpiConfig';

const values = {
  open_alerts_warning_count: 5,
  open_alerts_critical_count: 20,
  compliance_score_warning_pct: 80,
  compliance_score_critical_pct: 60,
};

describe('getKpiThresholdTone', () => {
  it('classifies normal thresholds as success, warning and danger', () => {
    expect(getKpiThresholdTone(values, 1, 'open_alerts_warning_count', 'open_alerts_critical_count')).toBe('success');
    expect(getKpiThresholdTone(values, 8, 'open_alerts_warning_count', 'open_alerts_critical_count')).toBe('warning');
    expect(getKpiThresholdTone(values, 25, 'open_alerts_warning_count', 'open_alerts_critical_count')).toBe('danger');
  });

  it('supports inverted thresholds for compliance scores', () => {
    expect(getKpiThresholdTone(values, 95, 'compliance_score_warning_pct', 'compliance_score_critical_pct', { inverted: true })).toBe('success');
    expect(getKpiThresholdTone(values, 75, 'compliance_score_warning_pct', 'compliance_score_critical_pct', { inverted: true })).toBe('warning');
    expect(getKpiThresholdTone(values, 50, 'compliance_score_warning_pct', 'compliance_score_critical_pct', { inverted: true })).toBe('danger');
  });
});
