import { ArrowLeft, Copy, Filter, RefreshCw } from 'lucide-react';
import React, { useCallback, useEffect, useState } from 'react';
import { Link, Navigate, useParams, useSearchParams } from 'react-router-dom';
import { FilterField, FilterPanel, FilterSelect, PageError } from '../components/domain';
import { DataProductUsageAccordion } from '../components/domain/data-product-usage-accordion';
import { ListPagination } from '../components/domain/list-pagination';
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
import { useDataProductUsagePageData } from '../hooks/useDataProductUsagePageData';
import { formatCurrency, formatDateTime } from '../lib/domain/formatters';
import {
  DATA_PRODUCT_FOCUS_VIEW_DESCRIPTIONS,
  DATA_PRODUCT_FOCUS_VIEW_LABELS,
  parseDataProductFocusView,
  parseTopMetricFromUrl,
  type DataProductTopMetric,
} from '../lib/data-product-usage/focus-view';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';

const CONSUMER_PAGE_SIZE = 10;
const TOP_METRICS: Array<{ value: DataProductTopMetric; label: string }> = [
  { value: 'data_read_bytes', label: 'Data read' },
  { value: 'request_count', label: 'Requests' },
  { value: 'rows_read', label: 'Rows read' },
  { value: 'cost_usd', label: 'Estimated cost' },
];

function formatNumber(value: number | null | undefined) {
  return new Intl.NumberFormat('en-GB').format(value ?? 0);
}

function formatBytes(bytes: number | null | undefined) {
  const value = bytes ?? 0;
  if (value < 1024) return `${formatNumber(value)} B`;
  const units = ['KB', 'MB', 'GB', 'TB'];
  let amount = value / 1024;
  let unitIndex = 0;
  while (amount >= 1024 && unitIndex < units.length - 1) {
    amount /= 1024;
    unitIndex += 1;
  }
  return `${amount.toFixed(amount >= 10 ? 1 : 2)} ${units[unitIndex]}`;
}

const DataProductUsageFocusPage: React.FC = () => {
  const { view: viewParam } = useParams<{ view: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const view = parseDataProductFocusView(viewParam ?? null);
  const urlMetric = parseTopMetricFromUrl(searchParams.get('metric'));
  const urlProduct = searchParams.get('product') ?? '';
  const urlConsumer = searchParams.get('consumer') ?? '';

  const {
    canNext,
    canPrev,
    consumerFilter,
    dataProductFilter,
    error,
    load,
    loading,
    offset,
    resetFilters,
    rows,
    setConsumerFilter,
    setDataProductFilter,
    setTopMetric,
    topConsumers,
    topMetric,
    total,
  } = useDataProductUsagePageData({
    initialConsumerFilter: urlConsumer,
    initialProductFilter: urlProduct,
    initialTopMetric: urlMetric,
  });

  const consumerPagination = useClientPagination(topConsumers, CONSUMER_PAGE_SIZE);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setDataProductFilter(urlProduct);
  }, [urlProduct, setDataProductFilter]);

  useEffect(() => {
    setConsumerFilter(urlConsumer);
  }, [urlConsumer, setConsumerFilter]);

  useEffect(() => {
    setTopMetric(urlMetric);
  }, [urlMetric, setTopMetric]);

  const syncUrlFilters = useCallback(
    (patch: { product?: string; consumer?: string; metric?: DataProductTopMetric }) => {
      setSearchParams(
        (current) => {
          const next = new URLSearchParams(current);
          if (patch.product !== undefined) {
            if (patch.product) next.set('product', patch.product);
            else next.delete('product');
          }
          if (patch.consumer !== undefined) {
            if (patch.consumer) next.set('consumer', patch.consumer);
            else next.delete('consumer');
          }
          if (patch.metric !== undefined) next.set('metric', patch.metric);
          return next;
        },
        { replace: true }
      );
    },
    [setSearchParams]
  );

  const copyLink = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }, []);

  if (!view) return <Navigate to="/data-product-usage" replace />;

  const formatMetric = (value: number) => {
    if (topMetric.includes('bytes')) return formatBytes(value);
    if (topMetric === 'cost_usd') return formatCurrency(value);
    return formatNumber(value);
  };

  return (
    <Content className="mx-auto max-w-[1700px]">
      <ContentHeader>
        <div className="space-y-3">
          <Button variant="ghost" size="sm" className="-ml-2 w-fit" asChild>
            <Link to="/data-product-usage">
              <ArrowLeft size={16} />
              Back to Data Product overview
            </Link>
          </Button>
          <div>
            <ContentTitle>{DATA_PRODUCT_FOCUS_VIEW_LABELS[view]}</ContentTitle>
            <ContentDescription>{DATA_PRODUCT_FOCUS_VIEW_DESCRIPTIONS[view]}</ContentDescription>
          </div>
        </div>
        <ContentActions>
          <Button variant="outline" size="sm" onClick={() => void copyLink()}>
            <Copy size={14} />
            {copied ? 'Link copied' : 'Copy link'}
          </Button>
          <Button variant="outline" size="sm" onClick={() => load(offset)} disabled={loading}>
            <RefreshCw size={14} />
            Refresh
          </Button>
        </ContentActions>
      </ContentHeader>

      {error && <PageError message={error} />}

      <ContentMain className="space-y-6">
        <FilterPanel
          title="Filters"
          description="Refine by product or consumer. Scope comes from the header."
          icon={<Filter size={16} />}
          resultCount={view === 'usage' ? total : topConsumers.length}
          activeFilterCount={[dataProductFilter, consumerFilter].filter(Boolean).length}
          emptyLabel="Global view"
          onReset={() => {
            resetFilters();
            syncUrlFilters({ product: '', consumer: '' });
          }}
          className="grid grid-cols-1 items-end gap-4 pt-0 md:grid-cols-2"
        >
          <FilterField label="Data product" htmlFor="dpu-focus-product">
            <Input
              id="dpu-focus-product"
              value={dataProductFilter}
              onChange={(e) => {
                setDataProductFilter(e.target.value);
                syncUrlFilters({ product: e.target.value });
              }}
              placeholder="data_product_id"
            />
          </FilterField>
          <FilterField label="Consumer" htmlFor="dpu-focus-consumer">
            <Input
              id="dpu-focus-consumer"
              value={consumerFilter}
              onChange={(e) => {
                setConsumerFilter(e.target.value);
                syncUrlFilters({ consumer: e.target.value });
              }}
              placeholder="consumer_id"
            />
          </FilterField>
        </FilterPanel>

        {view === 'usage' && (
          <>
            <DataProductUsageAccordion rows={rows} loading={loading} />
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border/60 pt-4 text-sm text-muted-foreground">
              <span>
                {formatNumber(Math.min(offset + 1, total))}–
                {formatNumber(Math.min(offset + 50, total))} of {formatNumber(total)}
              </span>
              <div className="flex gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={!canPrev || loading}
                  onClick={() => load(Math.max(0, offset - 50))}
                >
                  Previous
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={!canNext || loading}
                  onClick={() => load(offset + 50)}
                >
                  Next
                </Button>
              </div>
            </div>
          </>
        )}

        {view === 'consumers' && (
          <Card className="rounded-[1.5rem] border-border/70 shadow-none">
            <CardHeader>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <CardTitle className="text-base">
                    {topConsumers.length} consumer{topConsumers.length === 1 ? '' : 's'}
                  </CardTitle>
                  <CardDescription>Ranked by selected metric</CardDescription>
                </div>
                <FilterSelect
                  value={topMetric}
                  onChange={(e) => {
                    const next = e.target.value as DataProductTopMetric;
                    setTopMetric(next);
                    syncUrlFilters({ metric: next });
                  }}
                  className="w-40"
                >
                  {TOP_METRICS.map((m) => (
                    <option key={m.value} value={m.value}>
                      {m.label}
                    </option>
                  ))}
                </FilterSelect>
              </div>
            </CardHeader>
            <CardContent className="space-y-3 pt-0">
              {consumerPagination.pageItems.map((consumer, index) => (
                <div
                  key={`${consumer.consumer_id}-${index}`}
                  className="rounded-2xl border border-border/70 bg-background/70 p-4"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="truncate font-medium">
                        {consumer.consumer_name || consumer.consumer_id}
                      </p>
                      <p className="mt-1 truncate text-xs text-muted-foreground">
                        {consumer.consumer_id} · {consumer.source_lz_id}
                      </p>
                    </div>
                    <span className="text-sm font-semibold text-primary">
                      {formatMetric(consumer.metric_value)}
                    </span>
                  </div>
                  <div className="mt-3 grid grid-cols-3 gap-2 text-xs">
                    <div>
                      <p className="text-muted-foreground">Products</p>
                      <p className="font-semibold">{formatNumber(consumer.data_product_count)}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Metric</p>
                      <p className="font-semibold">{formatMetric(consumer.metric_value)}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Last used</p>
                      <p className="font-semibold">{formatDateTime(consumer.last_used_at)}</p>
                    </div>
                  </div>
                </div>
              ))}
              <ListPagination
                currentPage={consumerPagination.currentPage}
                endIndex={consumerPagination.endIndex}
                hasNextPage={consumerPagination.hasNextPage}
                hasPreviousPage={consumerPagination.hasPreviousPage}
                onNext={consumerPagination.nextPage}
                onPrevious={consumerPagination.previousPage}
                startIndex={consumerPagination.startIndex}
                totalItems={consumerPagination.totalItems}
                totalPages={consumerPagination.totalPages}
              />
            </CardContent>
          </Card>
        )}
      </ContentMain>
    </Content>
  );
};

export default DataProductUsageFocusPage;
