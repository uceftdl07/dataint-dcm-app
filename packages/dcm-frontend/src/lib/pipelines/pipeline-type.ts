import type { PipelineRun } from '../../types/api';

type PipelineIdentity = Pick<PipelineRun, 'pipeline_type' | 'pipeline_id'>;

export function isDatabricksPipeline(run: PipelineIdentity) {
  return run.pipeline_type === 'databricks_job' || Boolean(run.pipeline_id?.startsWith('databricks:job:'));
}

export function isAdfPipeline(run: PipelineIdentity) {
  if (isDatabricksPipeline(run)) {
    return false;
  }
  return run.pipeline_type === 'adf';
}
