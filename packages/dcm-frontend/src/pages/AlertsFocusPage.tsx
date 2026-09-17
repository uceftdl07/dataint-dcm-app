import { ArrowLeft, Copy, RefreshCw, Search } from 'lucide-react';
import React, { useCallback, useEffect, useState } from 'react';
import { Link, Navigate, useParams, useSearchParams } from 'react-router-dom';
import { FilterField, FilterPanel, FilterSelect, PageError } from '../components/domain';
import { ListPagination } from '../components/domain/list-pagination';
import { SecurityAlertAccordion } from '../components/domain/security-alert-accordion';
import {
  Content,
  ContentActions,
  ContentDescription,
  ContentHeader,
  ContentMain,
  ContentTitle,
} from '../components/layout/content';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { useClientPagination } from '../hooks/useClientPagination';
import { useAlertsPageData } from '../hooks/useAlertsPageData';
import {
  ALERTS_FOCUS_VIEW_DESCRIPTIONS,
  ALERTS_FOCUS_VIEW_LABELS,
  parseAlertSeverityFromUrl,
  parseAlertsFocusView,
  parseAlertStatusFromUrl,
} from '../lib/alerts/focus-view';
import type { AlertSeverity, AlertStatus } from '../types/api';

const PAGE_SIZE = 10;

const AlertsFocusPage: React.FC = () => {
  const { view: viewParam } = useParams<{ view: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const view = parseAlertsFocusView(viewParam ?? null);
  const urlSeverity = parseAlertSeverityFromUrl(searchParams.get('severity'));
  const urlStatus = parseAlertStatusFromUrl(searchParams.get('status'));
  const urlAlert = searchParams.get('alert');
  const urlSourceLzId = searchParams.get('source_lz_id');

  const {
    error,
    filteredAlerts,
    focusedAlertFound,
    load,
    loading,
    loadingDetails,
    resetFilters,
    search,
    setSearch,
    setSeverity,
    setStatus,
    severity,
    status,
  } = useAlertsPageData({
    initialSeverity: urlSeverity,
    initialStatus: urlStatus || 'active',
    focusAlertId: urlAlert ?? undefined,
    deepLinkSourceLzId: urlSourceLzId ?? undefined,
  });

  const pagination = useClientPagination(filteredAlerts, PAGE_SIZE);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setSeverity(urlSeverity);
  }, [urlSeverity, setSeverity]);
  useEffect(() => {
    if (urlStatus) setStatus(urlStatus);
  }, [urlStatus, setStatus]);

  const syncUrl = useCallback(
    (patch: { severity?: AlertSeverity | ''; status?: AlertStatus | '' }) => {
      setSearchParams(
        (c) => {
          const n = new URLSearchParams(c);
          if (patch.severity !== undefined) {
            if (patch.severity) n.set('severity', patch.severity);
            else n.delete('severity');
          }
          if (patch.status !== undefined) {
            if (patch.status) n.set('status', patch.status);
            else n.delete('status');
          }
          return n;
        },
        { replace: true }
      );
    },
    [setSearchParams]
  );

  if (!view) return <Navigate to="/alerts" replace />;

  const emptyMessage =
    urlAlert && !loading && !focusedAlertFound
      ? 'This alert is no longer active, is outside the notification window, or cannot be loaded with the current filters.'
      : 'No alerts match the selected filters.';

  return (
    <Content>
      <ContentHeader>
        <div className="space-y-3">
          <Button variant="ghost" size="sm" className="-ml-2 w-fit" asChild>
            <Link to="/alerts">
              <ArrowLeft size={16} />
              Back to Alerts overview
            </Link>
          </Button>
          <div>
            <ContentTitle>{ALERTS_FOCUS_VIEW_LABELS[view]}</ContentTitle>
            <ContentDescription>{ALERTS_FOCUS_VIEW_DESCRIPTIONS[view]}</ContentDescription>
          </div>
        </div>
        <ContentActions>
          <Button
            variant="outline"
            size="sm"
            onClick={() =>
              void navigator.clipboard.writeText(window.location.href).then(() => setCopied(true))
            }
          >
            <Copy size={14} />
            {copied ? 'Copied' : 'Copy link'}
          </Button>
          <Button variant="secondary" size="sm" onClick={load} disabled={loading}>
            <RefreshCw />
            Refresh
          </Button>
        </ContentActions>
      </ContentHeader>
      {error && <PageError message={error} />}
      <ContentMain className="space-y-6">
        <FilterPanel
          title="Filters"
          resultCount={filteredAlerts.length}
          activeFilterCount={
            [severity, status, search, urlSourceLzId, urlAlert].filter(Boolean).length
          }
          emptyLabel="Full view"
          onReset={() => {
            resetFilters();
            syncUrl({ severity: '', status: '' });
          }}
          className="grid grid-cols-1 gap-4 md:grid-cols-3"
        >
          <FilterField label="Severity" htmlFor="alerts-severity">
            <FilterSelect
              id="alerts-severity"
              value={severity}
              onChange={(e) => {
                const v = e.target.value as AlertSeverity | '';
                setSeverity(v);
                syncUrl({ severity: v });
              }}
            >
              <option value="">All severities</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="medium">Medium</option>
              <option value="low">Low</option>
            </FilterSelect>
          </FilterField>
          <FilterField label="Status" htmlFor="alerts-status">
            <FilterSelect
              id="alerts-status"
              value={status}
              onChange={(e) => {
                const v = e.target.value as AlertStatus | '';
                setStatus(v);
                syncUrl({ status: v });
              }}
            >
              <option value="">All statuses</option>
              <option value="active">Active</option>
              <option value="resolved">Resolved</option>
              <option value="dismissed">Dismissed</option>
            </FilterSelect>
          </FilterField>
          <FilterField label="Search" htmlFor="alerts-search">
            <div className="relative">
              <Search className="pointer-events-none absolute left-3 top-3 size-4 text-muted-foreground" />
              <Input
                id="alerts-search"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-9"
              />
            </div>
          </FilterField>
        </FilterPanel>
        <SecurityAlertAccordion
          alerts={pagination.pageItems}
          loading={loading || loadingDetails}
          emptyMessage={emptyMessage}
          initialOpenId={urlAlert}
          resetKey={`${pagination.currentPage}-${filteredAlerts.length}-${urlAlert ?? ''}`}
        />
        <ListPagination
          {...pagination}
          onNext={pagination.nextPage}
          onPrevious={pagination.previousPage}
        />
      </ContentMain>
    </Content>
  );
};

export default AlertsFocusPage;
