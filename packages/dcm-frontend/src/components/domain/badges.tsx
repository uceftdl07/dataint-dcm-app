import type { AlertSeverity, AlertStatus, StandardCheckState } from '../../types/api';
import {
  alertSeverityLabels,
  alertStatusLabels,
  getAlertSeverityPillClass,
  getAlertSeverityVariant,
  getAlertStatusPillClass,
  getAlertStatusVariant,
} from '../../lib/domain/alerts';
import {
  getCheckEffectPillClass,
  getStandardCheckStatePillClass,
  getStandardCheckStateVariant,
  standardCheckStateLabels,
} from '../../lib/domain/governance';
import { getBudgetLabel, getBudgetPillClass } from '../../lib/domain/finops';
import { Badge } from '../ui/badge';

export function AlertSeverityBadge({ severity }: { severity: AlertSeverity }) {
  return (
    <Badge variant={getAlertSeverityVariant(severity)} className={getAlertSeverityPillClass(severity)}>
      {alertSeverityLabels[severity]}
    </Badge>
  );
}

export function AlertStatusBadge({ status }: { status: AlertStatus }) {
  return (
    <Badge variant={getAlertStatusVariant(status)} className={getAlertStatusPillClass(status)}>
      {alertStatusLabels[status]}
    </Badge>
  );
}

export function StandardCheckStateBadge({ state }: { state: StandardCheckState }) {
  return (
    <Badge variant={getStandardCheckStateVariant(state)} className={getStandardCheckStatePillClass(state)}>
      {standardCheckStateLabels[state]}
    </Badge>
  );
}

export function CheckEffectBadge({ effect }: { effect: string | null }) {
  return (
    <Badge variant="outline" className={getCheckEffectPillClass(effect)}>
      {effect ?? 'N/A'}
    </Badge>
  );
}

export function BudgetBadge({ percentage }: { percentage: number | null }) {
  if (percentage === null) {
    return <Badge variant="outline">No budget</Badge>;
  }

  return (
    <Badge variant="outline" className={getBudgetPillClass(percentage)}>
      {getBudgetLabel(percentage)}
    </Badge>
  );
}
