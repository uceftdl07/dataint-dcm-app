# Feature Specification: Marquage des tables supprimées dans le Data Product Usage (Gold DBX Usage)

**Feature Branch**: `027-usage-table-deleted-flag`

**Created**: 2026-09-15

**Status**: Draft

**Input**: User description: "je veux ajoute dans le table gold dbx usage l'information si la table est supprimé ou pas. Ce qui va me permettre de filter côté front/backend d'afficher ou pas ces table et aussi de ne pas les inclure pour le forecast et aussi recomandation et gouvernance de ne pas les inclure"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Connaître l'état de suppression d'une table dans le Data Product Usage (Priority: P1)

En tant que responsable Data d'une Landing Zone, je consulte le Data Product Usage et je veux savoir, pour chaque table listée, si elle existe encore ou si elle a été supprimée du catalogue. Aujourd'hui des tables supprimées continuent d'apparaître avec leur historique d'usage, sans aucune distinction visuelle, ce qui fausse mon analyse.

**Why this priority**: C'est le socle de toute la feature. Sans le signal de suppression porté par la donnée, aucun filtrage (front, backend, forecast, gouvernance) n'est possible. Livrée seule, cette story a déjà de la valeur : l'état est visible et exploitable en analyse.

**Independent Test**: Sélectionner une table réellement supprimée dans une LZ de test, exécuter le pipeline, puis vérifier que l'état de suppression et la date de suppression sont présents et corrects dans les données d'usage exposées ; vérifier symétriquement qu'une table active reste marquée comme active.

**Acceptance Scenarios**:

1. **Given** une table présente dans le catalogue et utilisée récemment, **When** le pipeline d'usage s'exécute, **Then** la table est marquée comme non supprimée et aucune date de suppression n'est renseignée.
2. **Given** une table supprimée du catalogue à une date connue, **When** le pipeline d'usage s'exécute, **Then** la table est marquée comme supprimée avec la date de suppression correspondante, et son historique d'usage antérieur reste consultable.
3. **Given** une table supprimée puis recréée avec le même nom qualifié, **When** le pipeline s'exécute, **Then** la table repasse à l'état non supprimée et la date de suppression est effacée.
4. **Given** une table absente du catalogue pour cause de droits insuffisants (et non de suppression), **When** le pipeline s'exécute, **Then** la table n'est PAS marquée comme supprimée.

---

### User Story 2 - Masquer les tables supprimées dans l'application (Priority: P1)

En tant qu'utilisateur du Data Product Usage, je veux que les tables supprimées soient masquées par défaut dans les écrans (vue d'ensemble, listes détaillées, classements, performance), avec la possibilité d'afficher explicitement les tables supprimées quand j'ai besoin d'auditer l'historique.

**Why this priority**: C'est la valeur directement perçue par l'utilisateur. Dépend de la story 1 mais constitue le livrable visible du sprint.

**Independent Test**: Avec un jeu de données contenant des tables actives et supprimées, vérifier que la liste par défaut ne contient aucune table supprimée, que les compteurs/KPI sont cohérents avec cette exclusion, puis activer l'option d'inclusion et vérifier que les tables supprimées apparaissent avec un marquage explicite.

**Acceptance Scenarios**:

1. **Given** un jeu de données contenant des tables supprimées, **When** j'ouvre le Data Product Usage sans filtre particulier, **Then** aucune table supprimée n'apparaît dans les listes et les KPI n'intègrent pas leur usage.
2. **Given** le même jeu de données, **When** j'active l'option « inclure les tables supprimées », **Then** les tables supprimées apparaissent, identifiées visuellement comme supprimées, avec leur date de suppression.
3. **Given** une requête d'export ou de pagination sur la liste détaillée, **When** l'option d'inclusion n'est pas activée, **Then** la pagination et les totaux portent uniquement sur les tables non supprimées.
4. **Given** un utilisateur ayant activé l'inclusion, **When** il navigue vers un autre écran du Data Product Usage, **Then** le choix d'inclusion reste cohérent sur l'ensemble du parcours.

---

### User Story 3 - Exclure les tables supprimées du forecast (Priority: P2)

En tant qu'analyste FinOps, je veux que les prévisions d'usage ne soient plus calculées ni affichées pour les tables supprimées, afin de ne pas projeter une consommation future sur des objets qui n'existent plus.

**Why this priority**: Corrige une distorsion des projections, mais l'impact est moins immédiat que l'affichage. Dépend du signal de la story 1.

**Independent Test**: Exécuter la génération des prévisions sur un jeu contenant une table supprimée disposant d'un historique suffisant, puis vérifier qu'aucune prévision future n'est produite pour cette table et que les prévisions des tables actives sont inchangées.

**Acceptance Scenarios**:

1. **Given** une table supprimée avec un historique d'usage suffisant, **When** les prévisions sont générées, **Then** aucune prévision à horizon futur n'est produite pour cette table.
2. **Given** une table supprimée ayant déjà des prévisions produites lors d'exécutions antérieures, **When** les prévisions sont régénérées, **Then** ses prévisions à horizon futur ne sont plus restituées.
3. **Given** un ensemble de tables actives, **When** les prévisions sont générées, **Then** leurs prévisions restent identiques en présence ou en absence de tables supprimées dans le périmètre.

---

### User Story 4 - Exclure les tables supprimées des recommandations et de la gouvernance (Priority: P2)

En tant que responsable gouvernance, je ne veux plus recevoir de recommandations (table inutilisée, table orpheline, fraîcheur, fiabilité, coût) portant sur des tables déjà supprimées, et je ne veux pas qu'elles dégradent les indicateurs de gouvernance.

**Why this priority**: Réduit le bruit et redonne de la crédibilité aux recommandations. Dépend du signal de la story 1.

**Independent Test**: Exécuter le calcul de gouvernance et de recommandations sur un jeu contenant des tables supprimées qui déclencheraient normalement des règles, puis vérifier qu'aucune recommandation ouverte ne les cible et que les indicateurs de gouvernance les excluent.

**Acceptance Scenarios**:

1. **Given** une table supprimée qui remplit les conditions d'une règle (ex. non lue depuis plus de 90 jours), **When** les recommandations sont calculées, **Then** aucune recommandation ouverte n'est créée pour cette table.
2. **Given** une recommandation ouverte existante sur une table ensuite supprimée, **When** les recommandations sont recalculées, **Then** cette recommandation n'est plus restituée comme ouverte.
3. **Given** un périmètre contenant des tables supprimées, **When** les indicateurs de gouvernance sont calculés, **Then** ces tables ne sont comptées ni au numérateur ni au dénominateur.
4. **Given** une table supprimée puis recréée, **When** les recommandations sont recalculées, **Then** elle redevient éligible aux règles de gouvernance.

---

### Edge Cases

- Table absente du catalogue sans trace de suppression (droits insuffisants, périmètre non collecté) : elle ne doit pas être considérée comme supprimée ; son état est « indéterminé » et elle suit le traitement des tables actives.
- Table supprimée puis recréée sous le même nom qualifié : l'état repasse à non supprimé et la date de suppression est effacée ; l'historique d'usage n'est pas fusionné artificiellement.
- Table supprimée et recréée plusieurs fois dans la fenêtre d'observation : seule la dernière opération fait foi pour l'état courant.
- Table supprimée pendant la période analysée : son usage avant suppression reste comptabilisé dans l'historique mais elle est exclue des vues par défaut, du forecast et des recommandations.
- Suppression détectée hors de la fenêtre d'historique disponible : l'état de suppression déjà établi doit être conservé et ne pas « revenir » à actif faute de trace récente.
- Aucune table supprimée dans le périmètre : les écrans, prévisions et recommandations restent strictement identiques au comportement actuel.
- Consommateur (utilisateur/service) dont toutes les tables consultées sont supprimées : il ne doit pas disparaître des données historiques mais ne doit plus générer de recommandations liées à ces tables.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: Le système MUST déterminer, pour chaque table du périmètre d'usage Databricks, si elle est supprimée ou non du catalogue, à partir des signaux de cycle de vie déjà collectés (journal des opérations de catalogue et référentiel des tables).
- **FR-002**: Le système MUST exposer cet état de suppression dans les données Gold d'usage, au niveau de la table (grain `cloud_provider` + `catalog` + `schema` + `table_name`), avec au minimum : un indicateur booléen de suppression et la date/heure de suppression constatée.
- **FR-003**: Le système MUST distinguer explicitement trois situations : table active, table supprimée, état indéterminé (absence de signal fiable), et MUST traiter l'état indéterminé comme « non supprimée ».
- **FR-004**: Le système MUST conserver l'historique d'usage des tables supprimées ; aucune donnée historique ne doit être effacée du fait de la suppression de la table.
- **FR-005**: Le système MUST rendre l'état de suppression disponible sur les vues d'usage exploitées par l'application (usage détaillé, popularité, performance de requêtes, gouvernance).
- **FR-006**: L'API MUST permettre de filtrer les résultats sur l'état de suppression, avec un comportement par défaut excluant les tables supprimées de toutes les réponses (KPI, tendances, listes, classements).
- **FR-007**: L'API MUST restituer l'indicateur de suppression et la date de suppression dans les réponses lorsque les tables supprimées sont explicitement demandées.
- **FR-008**: Les agrégats et compteurs retournés par l'API (totaux, pagination, classements) MUST être cohérents avec le filtre de suppression appliqué.
- **FR-009**: L'interface MUST masquer par défaut les tables supprimées sur l'ensemble des écrans du Data Product Usage.
- **FR-010**: L'interface MUST proposer une commande explicite permettant d'inclure les tables supprimées, et MUST alors les identifier visuellement comme supprimées avec leur date de suppression.
- **FR-011**: Le calcul des prévisions d'usage MUST exclure les tables supprimées, aussi bien en entrée (historique d'apprentissage) qu'en sortie (prévisions restituées à horizon futur).
- **FR-012**: Les prévisions déjà produites pour une table devenue supprimée MUST cesser d'être restituées pour les horizons futurs lors de la régénération suivante.
- **FR-013**: Le calcul des recommandations MUST exclure les tables supprimées de toutes les catégories de règles (cycle de vie, fraîcheur, gouvernance, fiabilité, coût).
- **FR-014**: Les recommandations ouvertes portant sur une table devenue supprimée MUST cesser d'être restituées comme ouvertes lors du recalcul suivant.
- **FR-015**: Les indicateurs de gouvernance (tables inutilisées, orphelines, obsolètes mais consommées, criticité, action recommandée) MUST exclure les tables supprimées de leur périmètre de calcul.
- **FR-016**: Une table supprimée puis recréée sous le même nom qualifié MUST redevenir active et réintégrer le périmètre des écrans par défaut, du forecast et des recommandations dès l'exécution suivante.
- **FR-017**: Le système MUST recalculer l'état de suppression à chaque exécution du pipeline d'usage, sans intervention manuelle.
- **FR-018**: Le système MUST produire une mesure de contrôle du nombre de tables marquées supprimées par exécution, exploitable pour détecter une anomalie de détection (ex. pic anormal de suppressions).

### Key Entities *(include if data involved)*

- **Table du catalogue (objet observé)** : identifiée par le fournisseur cloud, le catalogue, le schéma et le nom de table. Porte désormais un état de cycle de vie : supprimée / active / indéterminé, ainsi que la date de suppression constatée.
- **Événement de cycle de vie de table** : trace de création, modification ou suppression d'une table dans le catalogue, horodatée et attribuée à un auteur. Source du calcul de l'état de suppression.
- **Fait d'usage** : consommation d'une table par un consommateur sur une période. Conserve l'historique même après suppression de la table, mais hérite de l'état de suppression pour le filtrage.
- **Prévision d'usage** : projection d'une métrique d'usage pour un objet à une date future. N'est plus produite pour les tables supprimées.
- **Recommandation** : action suggérée sur une table ou un consommateur, avec catégorie, sévérité et statut. N'est plus ouverte sur les tables supprimées.
- **Indicateur de gouvernance** : synthèse d'état d'une table (inutilisée, orpheline, critique…), dont le périmètre exclut les tables supprimées.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100 % des tables réellement supprimées du catalogue sur un périmètre de validation sont correctement marquées comme supprimées après une exécution du pipeline.
- **SC-002**: 0 % de faux positifs sur un périmètre de validation : aucune table encore existante n'est marquée comme supprimée.
- **SC-003**: Aucune table supprimée n'apparaît dans les écrans du Data Product Usage lorsque l'option d'inclusion n'est pas activée (vérifié sur les quatre vues : vue d'ensemble, usage détaillé, consommateurs, performance).
- **SC-004**: Aucune prévision à horizon futur n'est restituée pour une table supprimée après régénération.
- **SC-005**: Aucune recommandation ouverte ne cible une table supprimée après recalcul.
- **SC-006**: L'état de suppression d'une table est reflété dans l'application au plus tard à l'exécution planifiée suivante du pipeline d'usage (au maximum 24 h après la suppression).
- **SC-007**: Le temps d'affichage des écrans du Data Product Usage n'augmente pas de plus de 10 % par rapport à la situation avant la feature.
- **SC-008**: Le volume de recommandations ouvertes considérées comme non pertinentes par les responsables gouvernance diminue d'au moins 30 % sur un périmètre contenant des tables supprimées.
- **SC-009**: Un utilisateur peut basculer entre « masquer » et « afficher » les tables supprimées et constater l'effet en une seule action, sans rechargement manuel de la page.

## Assumptions

- Le signal de suppression est dérivable des données déjà collectées (journal d'audit des opérations de catalogue contenant l'action de suppression de table, et référentiel des tables du catalogue). Aucune nouvelle source externe n'est nécessaire.
- L'absence d'une table du référentiel du catalogue ne suffit pas à conclure à une suppression : elle peut résulter d'un défaut de droits ou d'un périmètre non collecté. Une corroboration par un événement de suppression est requise pour marquer l'état « supprimée ».
- Le comportement par défaut retenu est de masquer les tables supprimées côté application (et non de les supprimer des données), afin de préserver l'auditabilité et l'historique.
- L'identité d'une table est son nom qualifié complet (catalogue, schéma, table) ; une table recréée sous le même nom est considérée comme la même entité et redevient active.
- La détection est recalculée à chaque exécution du pipeline d'usage ; aucune saisie ou validation manuelle de l'état n'est prévue.
- Les consommateurs (utilisateurs et services) ne sont pas concernés par cet indicateur : seul l'objet « table » porte l'état de suppression.
- La feature s'applique au périmètre Databricks (Azure et AWS) couvert par le Data Product Usage ; les autres domaines de métriques ne sont pas impactés.
- Aucune notification ni alerte n'est déclenchée par la détection d'une suppression dans le cadre de cette feature ; seule la mesure de contrôle de volume est produite.

## Out of Scope

- Purge ou archivage physique des données d'usage historiques des tables supprimées.
- Alerting ou notification (Teams, e-mail, Jira) sur la suppression d'une table.
- Détection de la suppression de schémas, catalogues, vues matérialisées ou autres objets que les tables.
- Restauration ou récupération de tables supprimées.
- Suivi de l'auteur de la suppression comme fonctionnalité d'enquête dédiée (l'information reste disponible dans les données de cycle de vie existantes).
