import type { UcUsageRecommendation } from '../../types/api';

// Existing Gold templates only. Unknown/custom messages and identifiers stay verbatim.
const TITLES: Record<string, string> = {
  'Data product inutilise': 'Unused data product',
  'Data product critique marque inutilise': 'Critical data product marked unused',
  'Data product perime mais toujours consomme': 'Stale data product still being consumed',
  'Data product orphelin (aucun tag de gouvernance)': 'Data product missing governance tags',
  'Data product publie sans classification': 'Published data product without classification',
  "Taux d'echec eleve sur ce data product": 'High access failure rate',
  'Cout de consommation eleve': 'High consumption cost',
};
const ACTIONS: Record<string, string> = {
  'Proposer depreciation / suppression': 'Review for deprecation or removal.',
  'Ne PAS deprecier ; investiguer les dependances aval':
    'Keep the table and investigate downstream dependencies before considering deprecation.',
  'Corriger le pipeline amont ; prevenir les consommateurs':
    'Fix the upstream pipeline and notify consumers.',
  'Ajouter les tags owner/domain/cost-center': 'Add the owner, domain and cost center tags.',
  'Classifier la donnee': 'Classify the data.',
  'Investiguer les acces en echec (droits/schema)':
    'Investigate failed accesses, including permissions and schema changes.',
  'Sensibiliser / optimiser le consommateur':
    'Review the consumer’s usage and identify optimisation opportunities.',
};
export function ucRecommendationCopy(item: UcUsageRecommendation) {
  let detail = item.detail;
  if (TITLES[item.title] && detail) {
    detail = detail
      .replace('Aucune lecture depuis ', 'No read for ')
      .replace(' jours (ou jamais lu).', ' days, or never read.')
      .replace('downstream_fanout=', 'Observed downstream objects=')
      .replace(', aucune lecture depuis ', ', no read for ')
      .replace('freshness_lag_hours=', 'Write age=')
      .replace('h, derniere lecture il y a ', ' hours, last read ')
      .replace(' jours.', item.category === 'FRESHNESS' ? ' days ago.' : ' days.')
      .replace("Taux d'echec=", 'Failure rate=')
      .replace('Cout estime du jour=', 'Estimated daily cost=');
    if (item.title === 'Data product orphelin (aucun tag de gouvernance)')
      detail = 'Owner, domain and cost center tags are missing.';
    if (item.title === 'Data product publie sans classification')
      detail = 'Published as a data product without a classification.';
  }
  return {
    title: TITLES[item.title] ?? item.title,
    detail,
    action: item.recommended_action
      ? (ACTIONS[item.recommended_action] ?? item.recommended_action)
      : null,
  };
}
