import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  getDcmApiErrorMessage,
  getNotificationPreferences,
  updateNotificationPreferences,
} from '../api/dcmApiClient';
import type {
  UserNotificationPreferences,
  UserNotificationPreferencesUpdate,
} from '../types/api';
import { QUERY_GC_DEFAULT_MS, QUERY_STALE_NOTIFICATIONS_MS } from './query-config';
import { notificationQueryKeys } from './query-keys';

export function useNotificationPreferences() {
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: notificationQueryKeys.preferences(),
    queryFn: getNotificationPreferences,
    staleTime: QUERY_STALE_NOTIFICATIONS_MS,
    gcTime: QUERY_GC_DEFAULT_MS,
  });

  const mutation = useMutation({
    mutationFn: updateNotificationPreferences,
    onSuccess: (data) => {
      queryClient.setQueryData(notificationQueryKeys.preferences(), data);
    },
  });

  const load = () => {
    void query.refetch();
  };

  const save = async (payload: UserNotificationPreferencesUpdate) => mutation.mutateAsync(payload);

  const setPreferences = (preferences: UserNotificationPreferences) => {
    queryClient.setQueryData(notificationQueryKeys.preferences(), preferences);
  };

  const error = query.error
    ? getDcmApiErrorMessage(query.error, 'Failed to load notification preferences')
    : mutation.error
      ? getDcmApiErrorMessage(mutation.error, 'Failed to save notification preferences')
      : null;

  return {
    preferences: query.data ?? null,
    loading: query.isLoading,
    saving: mutation.isPending,
    error,
    load,
    save,
    setPreferences,
  };
}
