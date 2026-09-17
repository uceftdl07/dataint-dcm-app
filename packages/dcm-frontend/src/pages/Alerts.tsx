import { AlertCircle, AlertTriangle, Bell, RefreshCw } from 'lucide-react';
import React from 'react';
import { useNavigate } from 'react-router-dom';
import {
  HeaderTags,
  headerTagsDescriptionClass,
  MetricCard,
  MetricGrid,
} from '../components/domain';
import {
  Content,
  ContentActions,
  ContentDescription,
  ContentHeader,
  ContentMain,
  ContentTitle,
} from '../components/layout/content';
import { Alert, AlertDescription, AlertTitle } from '../components/ui/alert';
import { Button } from '../components/ui/button';
import { Card, CardContent } from '../components/ui/card';
import { Skeleton } from '../components/ui/skeleton';
import { useGlobalTimeRange } from '../contexts/time-range';
import { useAlertsPageData } from '../hooks/useAlertsPageData';
import { buildAlertsFocusPath } from '../lib/alerts/focus-view';

const Alerts: React.FC = () => {
  const navigate = useNavigate();
  const { getDisplayRange } = useGlobalTimeRange();
  const {
    activeCount,
    criticalCount,
    error,
    highCount,
    load,
    loading,
    loadingDetails,
    scopedAlerts,
    scope,
  } = useAlertsPageData();
  const display = getDisplayRange();

  return (
    <Content>
      <ContentHeader>
        <div>
          <ContentTitle>Global Alerts</ContentTitle>
          <ContentDescription className={headerTagsDescriptionClass}>
            <HeaderTags
              description={`Backend security alerts — ${display.startDate} to ${display.endDate} — ${scope.label}`}
              tags={[
                { value: 'Backend security', icon: <Bell size={14} />, tone: 'danger' },
                { label: 'From', value: display.startDate },
                { label: 'To', value: display.endDate },
                { label: 'Scope', value: scope.label },
              ]}
            />
          </ContentDescription>
        </div>
        <ContentActions>
          <Button variant="secondary" size="sm" onClick={load} disabled={loading || loadingDetails}>
            <RefreshCw />
            Refresh
          </Button>
        </ContentActions>
      </ContentHeader>
      {error && (
        <Alert variant="destructive">
          <AlertTriangle />
          <AlertTitle>Loading error</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      <ContentMain className="space-y-6">
        {loading ? (
          <Skeleton className="h-[140px]" />
        ) : (
          <Card>
            <CardContent className="p-5">
              <p className="text-xs font-semibold uppercase tracking-[0.22em] text-tdf-blue">
                Alerts overview
              </p>
              <h2 className="mt-2 text-2xl font-semibold">
                Click a metric to open the alert list.
              </h2>
            </CardContent>
          </Card>
        )}
        <MetricGrid
          loading={loading}
          skeletonCount={4}
          className="grid grid-cols-1 gap-4 md:grid-cols-4"
        >
          <MetricCard
            label="Total alerts"
            value={scopedAlerts.length}
            description="All alerts"
            icon={<Bell />}
            onClick={() => navigate(buildAlertsFocusPath('list'))}
          />
          <MetricCard
            label="Active"
            value={activeCount}
            description="Open alerts"
            icon={<AlertCircle />}
            tone="danger"
            onClick={() => navigate(buildAlertsFocusPath('list', { status: 'active' }))}
          />
          <MetricCard
            label="Critical"
            value={criticalCount}
            description="Critical severity"
            icon={<AlertTriangle />}
            tone="danger"
            onClick={() => navigate(buildAlertsFocusPath('list', { severity: 'critical' }))}
          />
          <MetricCard
            label="High"
            value={highCount}
            description="High severity"
            icon={<AlertTriangle />}
            tone="warning"
            onClick={() => navigate(buildAlertsFocusPath('list', { severity: 'high' }))}
          />
        </MetricGrid>
      </ContentMain>
    </Content>
  );
};

export default Alerts;
