"""Spike prototype — résolution du périmètre d'accès dans le modèle « projet » DCM.

Branche : spike/access_groupe_strategy
NON câblé dans dcm-backend. Prototype pour arbitrage — à porter dans
``packages/dcm-backend/app/auth/`` si le design est validé.

Remplace le modèle plat actuel (``get_allowed_lz_ids`` → liste de LZ) par un
périmètre à deux dimensions (Landing Zones + workspaces Databricks), calculé
comme l'union des périmètres de tous les projets actifs dont l'utilisateur est
membre. ``super_admin`` (platform_admin) reste non restreint.

Conventions reprises de ``app/auth/dependencies.py`` :
    - requêtes paramétrées ``?`` via ``DatabricksWarehousePool``,
    - ``qualified_table(settings, name)`` pour adresser Unity Catalog,
    - ``None``/``unrestricted`` = accès complet (platform admin).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:  # imports réels côté package une fois câblé
    from ...config import Settings
    from ...db.connection import DatabricksWarehousePool

# Rôle plateforme au-dessus des projets (cf. décision 4 du spike).
PLATFORM_ADMIN_ROLES = frozenset({"super_admin"})
# Statut projet pris en compte pour le calcul du périmètre.
_ACTIVE_PROJECT_STATUS = "active"


class AllowedScope(BaseModel):
    """Périmètre effectif d'un utilisateur, union sur ses projets actifs.

    ``unrestricted=True`` court-circuite tout filtrage (platform admin) :
    équivaut au ``None`` renvoyé aujourd'hui par ``get_allowed_lz_ids``.
    """

    unrestricted: bool = False
    lz_ids: list[str] = Field(default_factory=list)
    workspace_ids: list[str] = Field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """Aucun périmètre : l'utilisateur ne voit rien (0 projet actif)."""
        return not self.unrestricted and not self.lz_ids and not self.workspace_ids


async def get_allowed_scope(
    db: DatabricksWarehousePool,
    settings: Settings,
    *,
    user_id: str,
    platform_role: str,
) -> AllowedScope:
    """Calcule le périmètre LZ + workspace DBX d'un utilisateur.

    Platform admin → accès complet. Sinon union des périmètres des projets
    ``active`` où l'utilisateur est membre (rôle projet indifférent : viewer et
    admin voient les mêmes données, seul l'admin gère le projet).
    """
    from ...db.tables import qualified_table  # local: évite le cycle en prototype

    if platform_role in PLATFORM_ADMIN_ROLES:
        return AllowedScope(unrestricted=True)

    members = qualified_table(settings, "dcm_project_members")
    projects = qualified_table(settings, "dcm_projects")
    lz_scope = qualified_table(settings, "dcm_project_lz_scope")
    dbx_scope = qualified_table(settings, "dcm_project_dbx_scope")

    lz_rows = await db.fetchall(
        f"""
        SELECT DISTINCT s.lz_id
        FROM {members} m
        JOIN {projects} p ON p.id = m.project_id AND p.status = ?
        JOIN {lz_scope} s ON s.project_id = p.id
        WHERE m.user_id = ?
        ORDER BY s.lz_id
        """,
        _ACTIVE_PROJECT_STATUS,
        user_id,
    )
    dbx_rows = await db.fetchall(
        f"""
        SELECT DISTINCT s.workspace_id
        FROM {members} m
        JOIN {projects} p ON p.id = m.project_id AND p.status = ?
        JOIN {dbx_scope} s ON s.project_id = p.id
        WHERE m.user_id = ?
        ORDER BY s.workspace_id
        """,
        _ACTIVE_PROJECT_STATUS,
        user_id,
    )

    return AllowedScope(
        unrestricted=False,
        lz_ids=[row["lz_id"] for row in lz_rows],
        workspace_ids=[row["workspace_id"] for row in dbx_rows],
    )


async def is_project_admin(
    db: DatabricksWarehousePool,
    settings: Settings,
    *,
    user_id: str,
    project_id: str,
) -> bool:
    """Garde projet-scopé : l'utilisateur est-il ``admin`` de CE projet ?

    Remplace ``require_role`` (global) pour les actions de gestion d'un projet
    (membres, rôles, demande d'extension de périmètre). ``super_admin`` court-
    circuite ce contrôle en amont côté route.
    """
    from ...db.tables import qualified_table

    members = qualified_table(settings, "dcm_project_members")
    row = await db.fetchone(
        f"""
        SELECT 1
        FROM {members}
        WHERE user_id = ? AND project_id = ? AND role = 'admin'
        LIMIT 1
        """,
        user_id,
        project_id,
    )
    return row is not None
