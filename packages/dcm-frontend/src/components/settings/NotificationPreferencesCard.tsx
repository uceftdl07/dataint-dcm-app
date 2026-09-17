import { Bell, Loader2, Search } from 'lucide-react';
import React, { useEffect, useMemo, useState } from 'react';
import { getDcmApiErrorMessage } from '../../api/dcmApiClient';
import { useCurrentDcmUser } from '../../hooks/useCurrentDcmUser';
import { useLandingZonesList } from '../../hooks/useLandingZonesList';
import { useNotificationPreferences } from '../../hooks/useNotificationPreferences';
import type {
  LandingZoneDetail,
  NotificationMinSeverity,
  UserNotificationPreferencesUpdate,
} from '../../types/api';
import { Button } from '../ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../ui/card';
import { Input } from '../ui/input';

const DOMAIN_FIELDS: Array<{
  key: keyof Pick<
    UserNotificationPreferencesUpdate,
    | 'show_pipeline'
    | 'show_cluster'
    | 'show_cost'
    | 'show_security'
    | 'show_governance'
    | 'show_collector_status'
  >;
  label: string;
  description: string;
}> = [
  { key: 'show_pipeline', label: 'Pipelines', description: 'ADF, Glue runs and failures' },
  { key: 'show_cluster', label: 'Clusters', description: 'Databricks, EMR compute' },
  { key: 'show_cost', label: 'Costs', description: 'Spend and budget signals' },
  { key: 'show_security', label: 'Security', description: 'Active security alerts' },
  { key: 'show_governance', label: 'Governance', description: 'Compliance and standard checks' },
  { key: 'show_collector_status', label: 'Collectors', description: 'Collector health and last run' },
];

const SEVERITY_OPTIONS: Array<{ value: NotificationMinSeverity; label: string }> = [
  { value: 'info', label: 'All (info+)' },
  { value: 'warning', label: 'Warning and above' },
  { value: 'critical', label: 'Critical only' },
];

function toUpdatePayload(
  prefs: UserNotificationPreferencesUpdate,
): UserNotificationPreferencesUpdate {
  return {
    show_pipeline: prefs.show_pipeline,
    show_cluster: prefs.show_cluster,
    show_cost: prefs.show_cost,
    show_security: prefs.show_security,
    show_governance: prefs.show_governance,
    show_collector_status: prefs.show_collector_status,
    min_severity: prefs.min_severity,
    hide_info: prefs.hide_info,
    email_enabled: prefs.email_enabled,
    teams_digest_enabled: prefs.teams_digest_enabled,
    notification_lz_ids: prefs.notification_lz_ids ?? [],
  };
}

function landingZoneOptionLabel(landingZone: LandingZoneDetail): string {
  const parts = [
    landingZone.lz_name || landingZone.lz_id,
    landingZone.environment,
    landingZone.cloud_provider.toUpperCase(),
  ].filter(Boolean);
  return parts.join(' · ');
}

function landingZoneMatchesSearch(landingZone: LandingZoneDetail, query: string): boolean {
  if (!query) {
    return true;
  }
  const haystack = [
    landingZone.lz_id,
    landingZone.lz_name,
    landingZone.environment,
    landingZone.cloud_provider,
    landingZone.subscription_or_account_id,
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();
  return haystack.includes(query);
}

export const NotificationPreferencesCard: React.FC = () => {
  const { preferences, loading, saving, error, save } = useNotificationPreferences();
  const { user: currentUser } = useCurrentDcmUser();
  const landingZonesQuery = useLandingZonesList();
  const [draft, setDraft] = useState<UserNotificationPreferencesUpdate | null>(null);
  const [savedMessage, setSavedMessage] = useState<string | null>(null);
  const [landingZoneSearch, setLandingZoneSearch] = useState('');
  const landingZones = landingZonesQuery.data?.items ?? [];
  const landingZonesLoading = landingZonesQuery.isLoading;
  const landingZonesError = landingZonesQuery.error
    ? getDcmApiErrorMessage(landingZonesQuery.error, 'Failed to load landing zones')
    : null;

  useEffect(() => {
    if (preferences) {
      setDraft(toUpdatePayload(preferences));
    }
  }, [preferences]);

  const selectableLandingZones = useMemo(() => {
    const allowedIds = currentUser?.lz_ids ?? [];
    if (allowedIds.length === 0) {
      return landingZones;
    }
    const allowed = new Set(allowedIds);
    return landingZones.filter((landingZone) => allowed.has(landingZone.lz_id));
  }, [currentUser?.lz_ids, landingZones]);

  const landingZoneSearchQuery = landingZoneSearch.trim().toLowerCase();

  const filteredLandingZones = useMemo(
    () =>
      selectableLandingZones.filter((landingZone) =>
        landingZoneMatchesSearch(landingZone, landingZoneSearchQuery),
      ),
    [landingZoneSearchQuery, selectableLandingZones],
  );

  const selectedLandingZoneCount = draft?.notification_lz_ids?.length ?? 0;

  const toggleDomain = (key: (typeof DOMAIN_FIELDS)[number]['key']) => {
    setDraft((current) => (current ? { ...current, [key]: !current[key] } : current));
    setSavedMessage(null);
  };

  const toggleLandingZone = (lzId: string) => {
    setDraft((current) => {
      if (!current) {
        return current;
      }
      const selected = new Set(current.notification_lz_ids ?? []);
      if (selected.has(lzId)) {
        selected.delete(lzId);
      } else {
        selected.add(lzId);
      }
      return { ...current, notification_lz_ids: Array.from(selected) };
    });
    setSavedMessage(null);
  };

  const clearLandingZoneFilter = () => {
    setDraft((current) => (current ? { ...current, notification_lz_ids: [] } : current));
    setSavedMessage(null);
  };

  const selectFilteredLandingZones = () => {
    setDraft((current) => {
      if (!current) {
        return current;
      }
      const selected = new Set(current.notification_lz_ids ?? []);
      filteredLandingZones.forEach((landingZone) => selected.add(landingZone.lz_id));
      return { ...current, notification_lz_ids: Array.from(selected) };
    });
    setSavedMessage(null);
  };

  const deselectFilteredLandingZones = () => {
    setDraft((current) => {
      if (!current) {
        return current;
      }
      const filteredIds = new Set(filteredLandingZones.map((landingZone) => landingZone.lz_id));
      const selected = (current.notification_lz_ids ?? []).filter((lzId) => !filteredIds.has(lzId));
      return { ...current, notification_lz_ids: selected };
    });
    setSavedMessage(null);
  };

  const handleSave = async () => {
    if (!draft) {
      return;
    }
    setSavedMessage(null);
    await save(draft);
    setSavedMessage('Preferences saved.');
  };

  return (
    <Card className="md:col-span-2">
      <CardHeader>
        <div className="flex items-center gap-2">
          <Bell className="h-5 w-5 text-primary" />
          <CardTitle>Notifications</CardTitle>
        </div>
        <CardDescription>
          Choose which alert domains and landing zones appear in the notification center. Critical
          security alerts always remain visible for your role. Outbound email and Teams digest are
          reserved for a later phase.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {loading ? (
          <p className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading preferences...
          </p>
        ) : error && !draft ? (
          <p className="text-sm text-destructive">{error}</p>
        ) : draft ? (
          <>
            <div>
              <p className="mb-3 text-sm font-medium">Domains shown in the app</p>
              <div className="grid gap-3 sm:grid-cols-2">
                {DOMAIN_FIELDS.map(({ key, label, description }) => (
                  <label
                    key={key}
                    className="flex cursor-pointer items-start gap-3 rounded-xl border p-3 has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring"
                  >
                    <input
                      type="checkbox"
                      className="mt-1 h-4 w-4 rounded border-input"
                      checked={draft[key]}
                      onChange={() => toggleDomain(key)}
                    />
                    <span>
                      <span className="block font-medium">{label}</span>
                      <span className="text-sm text-muted-foreground">{description}</span>
                    </span>
                  </label>
                ))}
              </div>
            </div>

            <div>
              <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p className="text-sm font-medium">Landing zones in the notification center</p>
                  {selectedLandingZoneCount > 0 ? (
                    <p className="text-xs text-muted-foreground">
                      {selectedLandingZoneCount} landing zone
                      {selectedLandingZoneCount === 1 ? '' : 's'} selected
                    </p>
                  ) : (
                    <p className="text-xs text-muted-foreground">All accessible landing zones</p>
                  )}
                </div>
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={clearLandingZoneFilter}
                  disabled={selectedLandingZoneCount === 0}
                >
                  Clear selection
                </Button>
              </div>
              <p className="mb-3 text-sm text-muted-foreground">
                Leave all unchecked to follow every landing zone you can access. Select one or more
                to only show personalized alerts for those zones (in addition to domain and severity
                filters above).
              </p>
              {landingZonesLoading ? (
                <p className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Loading landing zones...
                </p>
              ) : landingZonesError ? (
                <p className="text-sm text-destructive">{landingZonesError}</p>
              ) : selectableLandingZones.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  No landing zone metadata available for your account.
                </p>
              ) : (
                <div className="space-y-3">
                  <div className="relative">
                    <Search
                      size={15}
                      className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground"
                      aria-hidden
                    />
                    <Input
                      type="search"
                      value={landingZoneSearch}
                      onChange={(event) => setLandingZoneSearch(event.target.value)}
                      placeholder="Search by name, ID, environment or cloud..."
                      className="pl-9"
                      aria-label="Search landing zones"
                    />
                  </div>

                  {filteredLandingZones.length > 0 ? (
                    <div className="flex flex-wrap gap-2">
                      <Button
                        type="button"
                        variant="secondary"
                        size="sm"
                        onClick={selectFilteredLandingZones}
                      >
                        Select {landingZoneSearchQuery ? 'matching' : 'all'}
                      </Button>
                      <Button
                        type="button"
                        variant="secondary"
                        size="sm"
                        onClick={deselectFilteredLandingZones}
                        disabled={
                          !filteredLandingZones.some((landingZone) =>
                            (draft.notification_lz_ids ?? []).includes(landingZone.lz_id),
                          )
                        }
                      >
                        Deselect {landingZoneSearchQuery ? 'matching' : 'all'}
                      </Button>
                    </div>
                  ) : null}

                  {filteredLandingZones.length === 0 ? (
                    <p className="text-sm text-muted-foreground">
                      No landing zone matches &quot;{landingZoneSearch.trim()}&quot;.
                    </p>
                  ) : (
                    <div className="grid max-h-72 gap-3 overflow-y-auto pr-1 sm:grid-cols-2">
                      {filteredLandingZones.map((landingZone) => {
                        const checked = (draft.notification_lz_ids ?? []).includes(
                          landingZone.lz_id,
                        );
                        return (
                          <label
                            key={landingZone.lz_id}
                            className="flex cursor-pointer items-start gap-3 rounded-xl border p-3 has-[:focus-visible]:ring-2 has-[:focus-visible]:ring-ring"
                          >
                            <input
                              type="checkbox"
                              className="mt-1 h-4 w-4 rounded border-input"
                              checked={checked}
                              onChange={() => toggleLandingZone(landingZone.lz_id)}
                            />
                            <span>
                              <span className="block font-medium">
                                {landingZone.lz_name || landingZone.lz_id}
                              </span>
                              <span className="text-sm text-muted-foreground">
                                {landingZoneOptionLabel(landingZone)}
                              </span>
                              <span className="mt-0.5 block font-mono text-xs text-muted-foreground">
                                {landingZone.lz_id}
                              </span>
                            </span>
                          </label>
                        );
                      })}
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div>
                <label htmlFor="min-severity" className="mb-2 block text-sm font-medium">
                  Minimum severity displayed
                </label>
                <select
                  id="min-severity"
                  className="w-full rounded-lg border bg-background px-3 py-2 text-sm"
                  value={draft.min_severity}
                  onChange={(event) => {
                    setDraft({
                      ...draft,
                      min_severity: event.target.value as NotificationMinSeverity,
                    });
                    setSavedMessage(null);
                  }}
                >
                  {SEVERITY_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>

              <label className="flex items-start gap-3 rounded-xl border p-3">
                <input
                  type="checkbox"
                  className="mt-1 h-4 w-4 rounded border-input"
                  checked={draft.hide_info}
                  onChange={() => {
                    setDraft({ ...draft, hide_info: !draft.hide_info });
                    setSavedMessage(null);
                  }}
                />
                <span>
                  <span className="block font-medium">Hide info-level alerts</span>
                  <span className="text-sm text-muted-foreground">
                    Warning and critical remain visible according to the minimum above.
                  </span>
                </span>
              </label>
            </div>

            <div className="rounded-xl border border-dashed p-3 text-sm text-muted-foreground">
              <p className="font-medium text-foreground">Coming soon</p>
              <p>Personal email alerts and Teams digest subscriptions (phase 2).</p>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <Button onClick={() => void handleSave()} disabled={saving}>
                {saving ? (
                  <>
                    <Loader2 className="animate-spin" />
                    Saving...
                  </>
                ) : (
                  'Save preferences'
                )}
              </Button>
              {preferences?.is_default ? (
                <span className="text-sm text-muted-foreground">Using default preferences</span>
              ) : null}
              {savedMessage ? (
                <span className="text-sm text-tdf-green">{savedMessage}</span>
              ) : null}
              {error ? <span className="text-sm text-destructive">{error}</span> : null}
            </div>
          </>
        ) : null}
      </CardContent>
    </Card>
  );
};
