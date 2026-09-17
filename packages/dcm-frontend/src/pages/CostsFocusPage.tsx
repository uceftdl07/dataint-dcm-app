import { ArrowLeft, Copy, RefreshCw } from 'lucide-react';
import React, { useState } from 'react';
import { Link, Navigate, useParams } from 'react-router-dom';
import { PageError } from '../components/domain';
import { ListPagination } from '../components/domain/list-pagination';
import { ServiceCostAccordion } from '../components/domain/service-cost-accordion';
import {
  Content,
  ContentActions,
  ContentDescription,
  ContentHeader,
  ContentMain,
  ContentTitle,
} from '../components/layout/content';
import { Button } from '../components/ui/button';
import { useClientPagination } from '../hooks/useClientPagination';
import { useCostsPageData } from '../hooks/useCostsPageData';
import {
  COSTS_FOCUS_VIEW_DESCRIPTIONS,
  COSTS_FOCUS_VIEW_LABELS,
  parseCostsFocusView,
} from '../lib/costs/focus-view';

const PAGE_SIZE = 10;

const CostsFocusPage: React.FC = () => {
  const { view: viewParam } = useParams<{ view: string }>();
  const view = parseCostsFocusView(viewParam ?? null);
  const { byService, error, load, loading } = useCostsPageData();
  const pagination = useClientPagination(byService, PAGE_SIZE);
  const [copied, setCopied] = useState(false);

  if (!view) return <Navigate to="/costs" replace />;

  return (
    <Content className="mx-auto max-w-[1600px]">
      <ContentHeader>
        <div className="space-y-3">
          <Button variant="ghost" size="sm" className="-ml-2 w-fit" asChild>
            <Link to="/costs">
              <ArrowLeft size={16} />
              Back to Costs overview
            </Link>
          </Button>
          <div>
            <ContentTitle>{COSTS_FOCUS_VIEW_LABELS[view]}</ContentTitle>
            <ContentDescription>{COSTS_FOCUS_VIEW_DESCRIPTIONS[view]}</ContentDescription>
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
        <ServiceCostAccordion
          services={pagination.pageItems}
          loading={loading}
          resetKey={`${pagination.currentPage}-${byService.length}`}
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

export default CostsFocusPage;
