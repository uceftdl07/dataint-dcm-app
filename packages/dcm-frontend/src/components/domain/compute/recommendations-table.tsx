import type { ReactNode } from 'react';
import { Badge } from '../../ui/badge';
import {
  ComputeDataTable,
  type ComputeDataTableColumn,
  type SortDirection,
} from './compute-data-table';
import { COLUMN_WIDTH } from './compute-column-widths';
import { severityBadgeVariant } from '../../../lib/compute/badges';
import {
  categoryBadgeVariant,
  categoryLabel,
  daysSince,
  formatRecommendationSavings,
  objectTypeLabel,
  recommendationStatusBadgeVariant,
  recommendationStatusLabel,
} from '../../../lib/compute/recommendations';
import { severityLabel } from '../../../lib/compute/format';
import { computeRecommendationsFieldDescriptions } from '../../../lib/compute/field-descriptions';
import type { ComputeColumnFilterValues, ComputeRecommendationItem } from '../../../types/api';

export type RecommendationSortKey =
  | 'object'
  | 'category'
  | 'severity'
  | 'savings'
  | 'status'
  | 'since';

function ObjectCell({ row }: { row: ComputeRecommendationItem }) {
  // `truncate` sur chaque ligne, et non sur le bloc : les points de suspension d'un
  // conteneur ne s'appliquent qu'à son propre texte, pas à ses enfants de type bloc.
  return (
    <div className="min-w-0">
      <div className="truncate font-semibold text-foreground">
        {row.object_name || row.object_id}
      </div>
      <div className="truncate font-mono text-[10px] text-muted-foreground">{row.object_id}</div>
    </div>
  );
}

export function RecommendationsTable({
  rows,
  loading,
  periodEnd,
  toolbar,
  pagination,
  sort,
  onSortChange,
  onRowClick,
  filters,
  onFiltersChange,
  emptyTitle,
  emptyDescription,
}: {
  rows: ComputeRecommendationItem[];
  loading?: boolean;
  periodEnd: string;
  toolbar?: ReactNode;
  sort?: { key: RecommendationSortKey; direction: SortDirection };
  onSortChange?: (key: RecommendationSortKey) => void;
  pagination?: {
    currentPage: number;
    totalPages: number;
    totalItems: number;
    startIndex: number;
    endIndex: number;
    hasPreviousPage: boolean;
    hasNextPage: boolean;
    onPrevious: () => void;
    onNext: () => void;
  };
  onRowClick?: (row: ComputeRecommendationItem) => void;
  /** Filtres de colonne détenus par la page — voir `ComputeDataTable`. */
  filters?: ComputeColumnFilterValues;
  onFiltersChange?: (next: ComputeColumnFilterValues) => void;
  emptyTitle: string;
  emptyDescription: string;
}) {
  const columns: ComputeDataTableColumn<ComputeRecommendationItem>[] = [
    {
      id: 'object',
      filterKey: 'object',
      width: COLUMN_WIDTH.name,
      header: 'Object',
      description: computeRecommendationsFieldDescriptions.object,
      sortable: true,
      cell: (row) => <ObjectCell row={row} />,
    },
    {
      id: 'category',
      filterKey: 'category',
      width: COLUMN_WIDTH.label,
      header: 'Category',
      description: computeRecommendationsFieldDescriptions.category,
      sortable: true,
      cell: (row) => (
        <Badge variant={categoryBadgeVariant(row.category)}>{categoryLabel(row.category)}</Badge>
      ),
    },
    {
      id: 'title',
      filterKey: 'title',
      width: COLUMN_WIDTH.longName,
      header: 'Title',
      description: computeRecommendationsFieldDescriptions.title,
      // Seule cellule volontairement sur deux lignes. `whitespace-normal` est
      // nécessaire : l'enveloppe de cellule impose `nowrap`, qui s'hérite.
      cell: (row) => (
        <span className="line-clamp-2 whitespace-normal font-medium text-foreground">
          {row.title || '—'}
        </span>
      ),
    },
    {
      id: 'severity',
      filterKey: 'severity',
      width: COLUMN_WIDTH.badge,
      header: 'Severity',
      description: computeRecommendationsFieldDescriptions.severity,
      sortable: true,
      cell: (row) => (
        <Badge variant={severityBadgeVariant(row.severity)}>{severityLabel(row.severity)}</Badge>
      ),
    },
    {
      id: 'savings',
      filterKey: 'savings',
      width: COLUMN_WIDTH.metric,
      header: 'Est. savings',
      description: computeRecommendationsFieldDescriptions.estimatedSavings,
      align: 'right',
      sortable: true,
      cell: (row) => (
        <div className="text-right">
          <div className="font-semibold tabular-nums text-foreground">
            {formatRecommendationSavings(row.estimated_savings_usd)}
          </div>
          <div className="text-[10px] tabular-nums text-muted-foreground">
            Actual {formatRecommendationSavings(row.actual_cost_usd)}
          </div>
        </div>
      ),
    },
    {
      id: 'status',
      filterKey: 'status',
      width: COLUMN_WIDTH.status,
      header: 'Status',
      description: computeRecommendationsFieldDescriptions.status,
      sortable: true,
      cell: (row) => (
        <div className="flex flex-col gap-1">
          <Badge variant={recommendationStatusBadgeVariant(row.status)}>
            {recommendationStatusLabel(row.status)}
          </Badge>
          <span className="text-[10px] text-muted-foreground">
            {objectTypeLabel(row.object_type)}
          </span>
        </div>
      ),
    },
    {
      id: 'since',
      width: COLUMN_WIDTH.number,
      header: 'Since',
      description: computeRecommendationsFieldDescriptions.since,
      align: 'right',
      sortable: true,
      cell: (row) => (
        <span className="text-muted-foreground">{daysSince(row.first_seen_date, periodEnd)}</span>
      ),
    },
  ];

  return (
    <ComputeDataTable
      tableId="compute-recommendations"
      columns={columns}
      rows={rows}
      rowKey={(row) => row.recommendation_id}
      loading={loading}
      emptyTitle={emptyTitle}
      emptyDescription={emptyDescription}
      onRowClick={onRowClick}
      toolbar={toolbar}
      pagination={pagination}
      sort={sort}
      onSortChange={onSortChange ? (key) => onSortChange(key as RecommendationSortKey) : undefined}
      filterView="recommendations"
      filters={filters}
      onFiltersChange={onFiltersChange}
      minWidthClassName="min-w-[1040px]"
    />
  );
}
