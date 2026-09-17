export type DataIQIntent =
  | 'costs'
  | 'pipelines'
  | 'security'
  | 'governance'
  | 'data-product-usage'
  | 'compute'
  | 'databases'
  | 'overview'
  | 'unsupported';

const normalizeQuery = (query: string): string =>
  query
    .toLowerCase()
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '');

export const detectDataIQIntent = (query: string): DataIQIntent => {
  const normalized = normalizeQuery(query);

  if (/(security|alert|vulnerability|risk|defender|mfa)/.test(normalized)) {
    return 'security';
  }
  if (/(governance|compliance|standard|check|landing zone|score)/.test(normalized)) {
    return 'governance';
  }
  if (/(data product|data products|usage|consumer|consumption)/.test(normalized)) {
    return 'data-product-usage';
  }
  if (/(cluster|clusters|compute|databricks|emr|compute resource|compute resources)/.test(normalized)) {
    return 'compute';
  }
  if (/(database|databases|db|sql|rds|postgres|mysql|cosmos|redshift)/.test(normalized)) {
    return 'databases';
  }
  if (/(pipeline|pipelines|job|jobs|failed|failure|glue|adf|data factory)/.test(normalized)) {
    return 'pipelines';
  }
  if (/(cost|costs|finops|budget|spend|spending)/.test(normalized)) {
    return 'costs';
  }
  if (/(overview|global|summary|platform|dashboard|kpi|state|status)/.test(normalized)) {
    return 'overview';
  }

  return 'unsupported';
};
