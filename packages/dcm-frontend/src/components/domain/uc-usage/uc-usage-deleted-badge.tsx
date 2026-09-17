import { Trash2 } from 'lucide-react';
import { Badge } from '../../ui/badge';
import type { UcUsageLifecycle } from '../../../types/api';

/**
 * Marqueur des tables supprimées de Unity Catalog (spec 027). Rendu **avec** la
 * date de suppression quand elle est connue : sans elle, une ligne supprimée se
 * lirait comme une ligne vide plutôt que comme de l'historique.
 *
 * `null` pour une table vivante — la colonne reste alors telle qu'elle était.
 */
export function UcUsageDeletedBadge({
  row,
}: {
  row: Pick<UcUsageLifecycle, 'is_deleted' | 'deleted_at'>;
}) {
  if (!row.is_deleted) return null;
  const deletedOn = row.deleted_at?.slice(0, 10);
  return (
    <Badge
      variant="destructive"
      className="shrink-0 text-[10px]"
      title={
        deletedOn
          ? `Deleted from Unity Catalog on ${deletedOn}`
          : 'Deleted from Unity Catalog (date unknown)'
      }
    >
      <Trash2 aria-hidden />
      {deletedOn ? `Deleted ${deletedOn}` : 'Deleted'}
    </Badge>
  );
}
