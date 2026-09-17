import {
  AlertTriangle,
  BookOpen,
  Code2,
  Database,
  FileText,
  Layers,
  RefreshCw,
  Search,
  ShieldCheck,
  Table2,
} from 'lucide-react';
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { queryUnityCatalogTableGeneric } from '../api/dcmApiClient';
import { MetricCard } from '../components/domain';
import {
  Content,
  ContentActions,
  ContentDescription,
  ContentHeader,
  ContentMain,
  ContentTitle,
} from '../components/layout/content';
import { Alert, AlertDescription, AlertTitle } from '../components/ui/alert';
import { Badge } from '../components/ui/badge';
import { Button } from '../components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../components/ui/card';
import { FieldLabel, Input, Select } from '../components/ui/input';
import { Skeleton } from '../components/ui/skeleton';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '../components/ui/table';
import {
  useUnityCatalogNavigation,
  useUnityCatalogTableDetails,
} from '../hooks/useUnityCatalogQueries';
import { unityCatalogQueryKeys } from '../hooks/query-keys';
import type {
  UnityCatalogCellValue,
  UnityCatalogGenericQueryRequest,
  UnityCatalogQueryResult,
} from '../types/api';

const DEFAULT_CATALOG = 'it';
const DEFAULT_TABLE = 'curated_activity_runs';
const DEFAULT_ORDER_BY = 'collected_at DESC';
const PREVIEW_PAGE_SIZE = 100;

function formatCell(value: UnityCatalogCellValue | undefined) {
  if (value === null || value === undefined || value === '') return '-';
  return String(value);
}

function parseColumns(value: string): string[] | undefined {
  const columns = value
    .split(',')
    .map((column) => column.trim())
    .filter(Boolean);
  return columns.length ? columns : undefined;
}

const UnityCatalogExplorer: React.FC = () => {
  const queryClient = useQueryClient();
  const [selectedCatalog, setSelectedCatalog] = useState(DEFAULT_CATALOG);
  const [selectedSchema, setSelectedSchema] = useState('');
  const [selectedTable, setSelectedTable] = useState('');
  const [activeTable, setActiveTable] = useState('');
  const [previewOffset, setPreviewOffset] = useState(0);
  const [genericColumns, setGenericColumns] = useState('');
  const [genericWhere, setGenericWhere] = useState('');
  const [genericOrderBy, setGenericOrderBy] = useState(DEFAULT_ORDER_BY);
  const [genericLimit, setGenericLimit] = useState(100);
  const [genericResult, setGenericResult] = useState<UnityCatalogQueryResult | null>(null);
  const [loadingGeneric, setLoadingGeneric] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const navigation = useUnityCatalogNavigation({
    catalogName: selectedCatalog,
    schemaName: selectedSchema || undefined,
  });

  const catalogs = navigation.data?.Catalogs ?? navigation.data?.catalogs ?? [];
  const schemas = useMemo(
    () => navigation.data?.Schemas ?? navigation.data?.schemas ?? [],
    [navigation.data?.Schemas, navigation.data?.schemas]
  );
  const tables = navigation.data?.Tables ?? navigation.data?.tables ?? [];

  // The monitoring schema is environment-specific (`…__d` in dev, `…__p` in prod),
  // so it cannot be preselected from a constant here: the server flags it as the
  // target schema and we land on that one. Remembered per catalog so picking
  // "Select a schema" back is not undone on the next render.
  const autoSelectedCatalog = useRef<string | null>(null);
  useEffect(() => {
    if (!selectedCatalog || selectedSchema || autoSelectedCatalog.current === selectedCatalog) {
      return;
    }
    const target = schemas.find((schema) => schema.IsTargetSchema);
    if (!target) return;
    autoSelectedCatalog.current = selectedCatalog;
    setSelectedSchema(target.Name);
  }, [schemas, selectedCatalog, selectedSchema]);

  const previewOrderBy = activeTable === DEFAULT_TABLE ? DEFAULT_ORDER_BY : undefined;

  const tableDetails = useUnityCatalogTableDetails(
    {
      catalogName: selectedCatalog,
      schemaName: selectedSchema,
      tableName: activeTable,
      offset: previewOffset,
      limit: PREVIEW_PAGE_SIZE,
      orderBy: previewOrderBy,
    },
    Boolean(activeTable)
  );

  const handleRefresh = useCallback(async () => {
    await queryClient.invalidateQueries({ queryKey: unityCatalogQueryKeys.all });
  }, [queryClient]);

  const handleCatalogChange = (catalogName: string) => {
    setSelectedCatalog(catalogName);
    setSelectedSchema('');
    setSelectedTable('');
    setActiveTable('');
    setPreviewOffset(0);
    setGenericResult(null);
  };

  const handleSchemaChange = (schemaName: string) => {
    setSelectedSchema(schemaName);
    setSelectedTable('');
    setActiveTable('');
    setPreviewOffset(0);
    setGenericResult(null);
  };

  const handleTableChange = (tableName: string) => {
    setSelectedTable(tableName);
    setActiveTable(tableName);
    setPreviewOffset(0);
    setGenericResult(null);
    setPreviewError(null);
  };

  const runGenericQuery = useCallback(async () => {
    if (!selectedCatalog || !selectedSchema || !selectedTable) return;
    setLoadingGeneric(true);
    setPreviewError(null);
    try {
      const request: UnityCatalogGenericQueryRequest = {
        catalogName: selectedCatalog,
        schemaName: selectedSchema,
        tableName: selectedTable,
        columns: parseColumns(genericColumns),
        whereClause: genericWhere.trim() || undefined,
        orderBy: genericOrderBy.trim() || undefined,
        limit: genericLimit,
        offset: 0,
      };
      setGenericResult(await queryUnityCatalogTableGeneric(request));
    } catch (err) {
      setPreviewError(err instanceof Error ? err.message : 'Unable to run Unity Catalog query');
    } finally {
      setLoadingGeneric(false);
    }
  }, [
    genericColumns,
    genericLimit,
    genericOrderBy,
    genericWhere,
    selectedCatalog,
    selectedSchema,
    selectedTable,
  ]);

  const loading = navigation.isLoading;
  const loadingNavigation = navigation.isFetching && !navigation.isLoading;
  const error =
    navigation.error instanceof Error
      ? navigation.error.message
      : navigation.error
        ? String(navigation.error)
        : null;
  const detailsError =
    tableDetails.error instanceof Error
      ? tableDetails.error.message
      : tableDetails.error
        ? String(tableDetails.error)
        : null;

  const selectedPath = useMemo(
    () => [selectedCatalog, selectedSchema, selectedTable].filter(Boolean).join('.'),
    [selectedCatalog, selectedSchema, selectedTable]
  );

  const monitoringTables = tables.filter((table) => table.IsMonitoringTable);
  const targetSchemas = schemas.filter((schema) => schema.IsTargetSchema);
  const defaultPocPath = [
    DEFAULT_CATALOG,
    targetSchemas[0]?.Name ?? '<monitoring schema>',
    DEFAULT_TABLE,
  ].join('.');
  const recommendedCatalogs = catalogs.filter((catalog) => catalog.RecommendedForExploration);
  const tableMetadata = tableDetails.metadata;
  const tablePreview = tableDetails.preview;
  const pagination = tableDetails.pagination;
  const previewRows = tablePreview?.Data ?? [];
  const genericRows = genericResult?.Data ?? [];

  return (
    <Content>
      <ContentHeader>
        <div>
          <div className="sr-only">
            <div className="rounded-xl bg-primary p-2 text-primary-foreground">
              <BookOpen size={20} />
            </div>
            <ContentTitle>Unity Catalog Explore</ContentTitle>
          </div>
          <ContentDescription>
            Explore Unity Catalog catalogs, schemas, and tables with the same experience as
            Databricks.
          </ContentDescription>
        </div>
        <ContentActions className="flex flex-wrap items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => void handleRefresh()}
            disabled={navigation.isFetching}
          >
            <RefreshCw />
            Refresh
          </Button>
        </ContentActions>
      </ContentHeader>

      {error && (
        <Alert variant="destructive">
          <AlertTriangle />
          <AlertTitle>Unity Catalog error</AlertTitle>
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <ContentMain>
        <div className="grid gap-4 md:grid-cols-4">
          {loading ? (
            Array.from({ length: 4 }).map((_, index) => <Skeleton key={index} className="h-32" />)
          ) : (
            <>
              <MetricCard
                label="Collected catalogs"
                value={catalogs.length}
                description="Espaces Unity Catalog available"
                icon={<Database />}
              />
              <MetricCard
                label="Target schemas"
                value={targetSchemas.length}
                description="Monitoring-oriented schemas"
                icon={<Layers />}
                tone="purple"
              />
              <MetricCard
                label="Monitoring tables"
                value={monitoringTables.length}
                description="Tables ready to inspect"
                icon={<Table2 />}
                tone="success"
              />
              <MetricCard
                label="Recommended"
                value={recommendedCatalogs.length}
                description="Catalogs to explore first"
                icon={<ShieldCheck />}
              />
            </>
          )}
        </div>

        <Card>
          <CardHeader>
            <CardTitle>Navigation Unity Catalog</CardTitle>
            <CardDescription>Select a catalog, then a schema and table to inspect.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 pt-0">
            {loading ? (
              <div className="grid gap-4 md:grid-cols-3">
                {Array.from({ length: 3 }).map((_, index) => (
                  <Skeleton key={index} className="h-10" />
                ))}
              </div>
            ) : (
              <>
                <div className="grid gap-4 md:grid-cols-3">
                  <div className="space-y-2">
                    <label className="grid gap-1.5" htmlFor="unity-catalog">
                      <FieldLabel>Catalogue</FieldLabel>
                      <Select
                        id="unity-catalog"
                        value={selectedCatalog}
                        onChange={(event) => handleCatalogChange(event.target.value)}
                        className="w-full"
                      >
                        <option value="">Select a catalog</option>
                        {catalogs.map((catalog) => (
                          <option key={catalog.Name} value={catalog.Name}>
                            {catalog.Name}
                            {catalog.RecommendedForExploration ? ' ★' : ''}
                          </option>
                        ))}
                      </Select>
                    </label>
                  </div>
                  <div className="space-y-2">
                    <label className="grid gap-1.5" htmlFor="unity-schema">
                      <FieldLabel>Schema</FieldLabel>
                      <Select
                        id="unity-schema"
                        value={selectedSchema}
                        onChange={(event) => handleSchemaChange(event.target.value)}
                        className="w-full"
                        disabled={loadingNavigation || !selectedCatalog}
                      >
                        <option value="">
                          {loadingNavigation ? 'Loading schemas...' : 'Select a schema'}
                        </option>
                        {schemas.map((schema) => (
                          <option key={schema.Name} value={schema.Name}>
                            {schema.Name}
                            {schema.IsTargetSchema ? ' ★' : ''}
                          </option>
                        ))}
                      </Select>
                    </label>
                  </div>
                  <div className="space-y-2">
                    <label className="grid gap-1.5" htmlFor="unity-table">
                      <FieldLabel>Table</FieldLabel>
                      <Select
                        id="unity-table"
                        value={selectedTable}
                        onChange={(event) => handleTableChange(event.target.value)}
                        className="w-full"
                        disabled={loadingNavigation || !selectedSchema}
                      >
                        <option value="">
                          {loadingNavigation ? 'Loading tables...' : 'Select a table'}
                        </option>
                        {tables.map((table) => (
                          <option key={table.Name} value={table.Name}>
                            {table.Name} ({table.Format}){table.IsMonitoringTable ? ' ★' : ''}
                          </option>
                        ))}
                      </Select>
                    </label>
                  </div>
                </div>

                {selectedPath && (
                  <div className="rounded-xl border bg-muted/40 p-3">
                    <p className="text-xs uppercase tracking-wide text-muted-foreground">
                      Localisation
                    </p>
                    <p className="mt-1 truncate font-mono text-sm text-foreground">
                      {selectedPath}
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      Select a table to load metadata and preview. Default POC path:{' '}
                      {defaultPocPath}
                    </p>
                  </div>
                )}
              </>
            )}
          </CardContent>
        </Card>

        {(previewError || detailsError) && (
          <Alert variant="destructive">
            <AlertTriangle />
            <AlertTitle>Data preview error</AlertTitle>
            <AlertDescription>{previewError || detailsError}</AlertDescription>
          </Alert>
        )}

        {activeTable && tableDetails.isLoadingDetails && <Skeleton className="h-72" />}

        {activeTable && tableMetadata && !tableDetails.isLoadingDetails && (
          <Card>
            <CardHeader>
              <CardTitle>Table metadata</CardTitle>
              <CardDescription>
                {selectedPath || tablePreview?.FullTableName || 'No table selected'}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6 pt-0">
              <div className="grid gap-4 md:grid-cols-4">
                <Card>
                  <CardContent>
                    <FileText className="mb-3 text-primary" />
                    <p className="text-lg font-semibold">{tableMetadata.Type}</p>
                    <p className="text-xs text-muted-foreground">Type</p>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent>
                    <Database className="mb-3 text-primary" />
                    <p className="text-lg font-semibold">{tableMetadata.Format}</p>
                    <p className="text-xs text-muted-foreground">Format</p>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent>
                    <ShieldCheck className="mb-3 text-primary" />
                    <p className="truncate text-lg font-semibold">{tableMetadata.Owner}</p>
                    <p className="text-xs text-muted-foreground">Owner</p>
                  </CardContent>
                </Card>
                <Card>
                  <CardContent>
                    <Layers className="mb-3 text-primary" />
                    <p className="text-lg font-semibold">{tableMetadata.ColumnsCount}</p>
                    <p className="text-xs text-muted-foreground">Columns</p>
                  </CardContent>
                </Card>
              </div>

              <div>
                <div className="mb-3 flex items-center justify-between gap-3">
                  <h3 className="font-medium text-foreground">Column structure</h3>
                  <Badge variant="secondary">
                    {tableMetadata.Columns.length.toLocaleString('en-GB')} column(s)
                  </Badge>
                </div>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Name</TableHead>
                      <TableHead>Type</TableHead>
                      <TableHead>Nullable</TableHead>
                      <TableHead>Comment</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {tableMetadata.Columns.map((column) => (
                      <TableRow key={column.Name}>
                        <TableCell className="font-mono">{column.Name}</TableCell>
                        <TableCell>{column.Type}</TableCell>
                        <TableCell>
                          <Badge variant={column.Nullable ? 'secondary' : 'success'}>
                            {column.Nullable ? 'Yes' : 'No'}
                          </Badge>
                        </TableCell>
                        <TableCell className="max-w-md truncate text-muted-foreground">
                          {column.Comment || '-'}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </CardContent>
          </Card>
        )}

        {activeTable && tablePreview && !tableDetails.isLoadingDetails && (
          <Card>
            <CardHeader>
              <CardTitle>Data preview</CardTitle>
              <CardDescription>
                {tablePreview.RowsRetrieved.toLocaleString('en-GB')} row(s) shown,{' '}
                {tablePreview.ColumnsCount.toLocaleString('en-GB')} column(s)
                {pagination?.TotalRows
                  ? `, ${pagination.TotalRows.toLocaleString('en-GB')} total row(s)`
                  : ''}
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4 pt-0">
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      {tablePreview.Columns.map((column) => (
                        <TableHead key={column}>{column}</TableHead>
                      ))}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {previewRows.map((row, rowIndex) => (
                      <TableRow key={`${tablePreview.FullTableName}-${rowIndex}`}>
                        {row.map((cell, cellIndex) => (
                          <TableCell key={`${rowIndex}-${cellIndex}`} className="max-w-xs truncate">
                            {formatCell(cell)}
                          </TableCell>
                        ))}
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
              {pagination && (
                <div className="flex flex-wrap items-center justify-between gap-3 text-sm text-muted-foreground">
                  <span>
                    Page {pagination.CurrentPage}
                    {pagination.TotalPages ? ` / ${pagination.TotalPages}` : ''} · Offset{' '}
                    {pagination.Offset}
                  </span>
                  <div className="flex gap-2">
                    <Button
                      variant="secondary"
                      size="sm"
                      disabled={!pagination.HasPreviousPage || tableDetails.isFetchingDetails}
                      onClick={() => setPreviewOffset(pagination.PreviousOffset ?? 0)}
                    >
                      Previous
                    </Button>
                    <Button
                      variant="secondary"
                      size="sm"
                      disabled={!pagination.HasNextPage || tableDetails.isFetchingDetails}
                      onClick={() =>
                        setPreviewOffset(pagination.NextOffset ?? previewOffset + PREVIEW_PAGE_SIZE)
                      }
                    >
                      Next
                    </Button>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {selectedTable && (
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Code2 size={18} />
                Generic query
              </CardTitle>
              <CardDescription>
                POC-compatible query builder for columns, whereClause, orderBy, limit and offset.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4 pt-0">
              <div className="grid gap-4 lg:grid-cols-4">
                <div className="space-y-2">
                  <label className="text-sm font-medium" htmlFor="unity-columns">
                    Columns
                  </label>
                  <Input
                    id="unity-columns"
                    value={genericColumns}
                    onChange={(event) => setGenericColumns(event.target.value)}
                    placeholder="nom_script, statut"
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium" htmlFor="unity-where">
                    Where clause
                  </label>
                  <Input
                    id="unity-where"
                    value={genericWhere}
                    onChange={(event) => setGenericWhere(event.target.value)}
                    placeholder="statut = 'OK'"
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium" htmlFor="unity-order">
                    Order by
                  </label>
                  <Input
                    id="unity-order"
                    value={genericOrderBy}
                    onChange={(event) => setGenericOrderBy(event.target.value)}
                    placeholder="date_maj DESC"
                  />
                </div>
                <div className="space-y-2">
                  <label className="text-sm font-medium" htmlFor="unity-limit">
                    Limit
                  </label>
                  <Input
                    id="unity-limit"
                    type="number"
                    min={1}
                    max={50000}
                    value={genericLimit}
                    onChange={(event) => setGenericLimit(Number(event.target.value) || 100)}
                  />
                </div>
              </div>
              <Button onClick={() => void runGenericQuery()} disabled={loadingGeneric}>
                <Search />
                {loadingGeneric ? 'Running query' : 'Run query'}
              </Button>
              {genericResult && (
                <div className="space-y-3">
                  <div className="rounded-xl border bg-muted/40 p-3 text-xs text-muted-foreground">
                    <p className="font-mono text-foreground">{genericResult.SqlQuery}</p>
                    <p className="mt-1">
                      {genericResult.RowsRetrieved.toLocaleString('en-GB')} row(s),{' '}
                      {genericResult.ColumnsCount.toLocaleString('en-GB')} column(s),{' '}
                      {genericResult.ExecutionTime}s
                    </p>
                  </div>
                  <div className="overflow-x-auto">
                    <Table>
                      <TableHeader>
                        <TableRow>
                          {genericResult.Columns.map((column) => (
                            <TableHead key={column}>{column}</TableHead>
                          ))}
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {genericRows.slice(0, 50).map((row, rowIndex) => (
                          <TableRow key={`${genericResult.FullTableName}-${rowIndex}`}>
                            {row.map((cell, cellIndex) => (
                              <TableCell
                                key={`${rowIndex}-${cellIndex}`}
                                className="max-w-xs truncate"
                              >
                                {formatCell(cell)}
                              </TableCell>
                            ))}
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {tableMetadata && (
          <Alert>
            <ShieldCheck />
            <AlertTitle>PowerBI compatibility</AlertTitle>
            <AlertDescription>
              Same Unity Catalog source, {tableMetadata.Format} format compatible with PowerBI, and
              recommended connection through the Unity Catalog connector or SQL Warehouse.
            </AlertDescription>
          </Alert>
        )}
      </ContentMain>
    </Content>
  );
};

export default UnityCatalogExplorer;
