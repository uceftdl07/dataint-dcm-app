import { describe, expect, it } from 'vitest';
import type { PipelineRun } from '../../types/api';
import { isAdfPipeline, isDatabricksPipeline } from './pipeline-type';

function run(overrides: Partial<PipelineRun>): PipelineRun {
  return {
    run_id: 'run-1',
    pipeline_id: 'pl-1',
    pipeline_name: 'pipeline',
    cloud_provider: 'azure',
    source_lz_id: 'lz-1',
    status: 'succeeded',
    ...overrides,
  } as PipelineRun;
}

describe('pipeline-type helpers', () => {
  it('detects Databricks job runs', () => {
    expect(isDatabricksPipeline(run({ pipeline_type: 'databricks_job' }))).toBe(true);
    expect(isDatabricksPipeline(run({ pipeline_id: 'databricks:job:42' }))).toBe(true);
  });

  it('detects ADF runs and excludes Databricks ids', () => {
    expect(isAdfPipeline(run({ pipeline_type: 'adf' }))).toBe(true);
    expect(isAdfPipeline(run({ pipeline_type: 'adf', pipeline_id: 'databricks:job:42' }))).toBe(false);
    expect(isAdfPipeline(run({ pipeline_type: 'databricks_job' }))).toBe(false);
  });
});
