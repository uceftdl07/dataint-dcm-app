import { describe, expect, it } from 'vitest';
import { detectDataIQIntent } from './talk-to-data-intent';

describe('detectDataIQIntent', () => {
  it('detects supported intents from natural language', () => {
    expect(detectDataIQIntent('Compare my Azure and AWS costs this month')).toBe('costs');
    expect(detectDataIQIntent('Which jobs failed today?')).toBe('pipelines');
    expect(detectDataIQIntent('Analyze the security of my databases')).toBe('security');
    expect(detectDataIQIntent('What is the compliance score?')).toBe('governance');
    expect(detectDataIQIntent('Which data products are consumed the most?')).toBe('data-product-usage');
    expect(detectDataIQIntent('What is the state of Databricks clusters?')).toBe('compute');
    expect(detectDataIQIntent('Which databases are unavailable?')).toBe('databases');
    expect(detectDataIQIntent('Give me a global platform overview')).toBe('overview');
  });

  it('falls back for unsupported questions', () => {
    expect(detectDataIQIntent('Can you tell me a joke?')).toBe('unsupported');
  });
});
