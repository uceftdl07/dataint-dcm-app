import { useMemo } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import type { DatabricksFullResponse } from '../api/dcmApiClient';
import { useMonitoringScope } from '../contexts/monitoring-scope';
import { useGlobalTimeRange } from '../contexts/time-range';
import { databricksQueryKeys } from './query-keys';

/** Read cached Databricks dashboard bundle for instant sub-page paint. */
export function useDatabricksBundleCache(): DatabricksFullResponse | undefined {
  const queryClient = useQueryClient();
  const { getScopedParams } = useMonitoringScope();
  const { getApiParams } = useGlobalTimeRange();

  const queryKey = useMemo(() => {
    // Must stay identical to the key `useDatabricksPageData` writes under,
    // including the `sourceLzId` support — a mismatch turns this read into a
    // silent miss and the sub-pages back to a blank first paint.
    const scopedParams = getScopedParams({
      cloudProvider: true,
      subscriptionOrAccountId: true,
      workspaceId: true,
      sourceLzId: true,
    });
    const { start_date, end_date } = getApiParams();
    return databricksQueryKeys.full({
      start_date,
      end_date,
      cloud_provider: scopedParams.cloud_provider,
      subscription_or_account_id: scopedParams.subscription_or_account_id,
      workspace_id: scopedParams.workspace_id,
      workspace_ids: scopedParams.workspace_ids,
      source_lz_id: scopedParams.source_lz_id,
      source_lz_ids: scopedParams.source_lz_ids,
    });
  }, [getApiParams, getScopedParams]);

  return queryClient.getQueryData<DatabricksFullResponse>(queryKey);
}
