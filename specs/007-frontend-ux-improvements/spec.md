# Feature Specification: Frontend UX Improvements

**Feature Branch**: `007-frontend-ux-improvements`  
**Created**: 2026-05-28  
**Status**: Draft  
**Input**: Observation utilisateur de `http://localhost:4000/` et document `docs/proposition/ameliorations-experience-utilisateur.md`

---

## Comprehension du besoin

### Objectif

Ameliorer l'experience utilisateur de l'interface DCM sans modifier les contrats backend ni le contenu fonctionnel des pages.

L'interface actuelle est deja professionnelle et coherente : cartes arrondies, navigation laterale, filtres globaux, modules metier, SSO Microsoft et assistant `Mounir AI`. Le probleme principal est la densite visuelle : la zone de filtres prend beaucoup de place, certaines actions sont masquees ou peu visibles, et le menu reduit depend trop des icones.

Cette spec transforme les recommandations UX en increment implementable cote frontend.

### Perimetre

Inclus :

- Compactage du header de page et des filtres globaux.
- Amelioration du menu lateral reduit.
- Repositionnement ou compactage du bouton flottant `Mounir AI`.
- Clarification des verdicts, KPI, actions et etats vides.
- Harmonisation des libelles principaux.
- Verification responsive sur largeurs courantes.

Hors perimetre :

- Refonte complete du design system.
- Changement de technologie frontend.
- Modification des endpoints backend.
- Ajout d'un systeme i18n complet si non necessaire.
- Refonte metier des pages Databricks, FinOps, Alerts ou Admin.

---

## User Scenarios & Testing

### User Story 1 - Voir les donnees plus rapidement (Priority: P1)

En tant qu'utilisateur DCM, je veux que les filtres globaux prennent moins de place afin de voir les KPI et les resultats importants des le premier ecran.

**Why this priority**: c'est le frein UX le plus visible. Sur plusieurs pages, les champs `Env`, `Start`, `End` et `Range` occupent presque tout le haut de page.

**Independent Test**: ouvrir `/dashboard`, `/databricks`, `/databricksalerts` et `/databricksfinops` sur un viewport desktop standard et verifier que le resume de page et les premiers KPI sont visibles sans scroll excessif.

**Acceptance Scenarios**:

1. **Given** un utilisateur ouvre une page protegee, **When** les filtres globaux sont affiches, **Then** leur hauteur visuelle est reduite par rapport a l'etat actuel.
2. **Given** une largeur suffisante, **When** le header est rendu, **Then** les dates et raccourcis de periode peuvent tenir sur une ligne ou dans une zone compacte.
3. **Given** les filtres sont replis ou compactes, **When** l'utilisateur veut modifier le scope, **Then** il peut toujours ouvrir et changer `Env`, `Start`, `End` et `Range`.
4. **Given** un scope actif, **When** les filtres sont compacts, **Then** un resume lisible du scope reste visible.

---

### User Story 2 - Naviguer clairement avec le menu lateral reduit (Priority: P1)

En tant que nouvel utilisateur, je veux comprendre les icones du menu reduit afin de naviguer sans devoir ouvrir le menu complet a chaque fois.

**Why this priority**: le menu ouvert est clair, mais le menu reduit repose uniquement sur les icones et certaines zones cliquables sont moins evidentes.

**Independent Test**: reduire le menu, survoler les icones, naviguer vers Home, Databricks, Global FinOps et Global Alerts, puis verifier que l'etat actif et les tooltips sont comprehensibles.

**Acceptance Scenarios**:

1. **Given** le menu lateral est reduit, **When** l'utilisateur survole une icone, **Then** un tooltip affiche le libelle de destination.
2. **Given** l'utilisateur est sur une page, **When** le menu reduit est visible, **Then** l'element actif est identifiable.
3. **Given** les liens du menu sont lus par un lecteur d'ecran, **When** les noms accessibles sont exposes, **Then** ils ne contiennent pas de duplication du type `HomeHome`.
4. **Given** l'utilisateur clique sur une icone visible, **When** la navigation est declenchee, **Then** aucun element superpose n'intercepte le clic.

---

### User Story 3 - Utiliser Mounir AI sans masquer les actions (Priority: P1)

En tant qu'utilisateur, je veux que le bouton `Mounir AI` reste disponible sans masquer les boutons ou compteurs importants.

**Why this priority**: le bouton flottant est utile, mais sa taille et sa position peuvent cacher `Refresh`, des compteurs ou des actions secondaires.

**Independent Test**: ouvrir dashboard, Databricks, FinOps et Alerts sur desktop et viewport plus etroit, puis verifier que `Mounir AI` ne recouvre pas les actions principales.

**Acceptance Scenarios**:

1. **Given** une page avec actions en bas de la zone visible, **When** `Mounir AI` est affiche, **Then** il ne recouvre pas `Refresh`, `Export`, `Reset` ou les KPI.
2. **Given** un viewport etroit, **When** l'espace est limite, **Then** le bouton passe en etat compact ou se positionne dans une zone non conflictuelle.
3. **Given** l'utilisateur ouvre l'assistant, **When** l'assistant est referme, **Then** la page retrouve son etat visuel sans decalage inattendu.

---

### User Story 4 - Comprendre rapidement l'etat metier (Priority: P2)

En tant qu'utilisateur metier ou technique, je veux voir un verdict court et les KPI prioritaires avant les textes explicatifs afin de savoir rapidement si une action est necessaire.

**Why this priority**: certaines pages expliquent beaucoup avant de mettre en avant la conclusion operationnelle.

**Independent Test**: ouvrir les pages principales et verifier la presence d'un resume court de type `Healthy`, `Action required`, `No data` ou `To monitor`, suivi des KPI principaux.

**Acceptance Scenarios**:

1. **Given** une page de monitoring, **When** les donnees sont chargees, **Then** un verdict court est visible pres du haut de page.
2. **Given** des KPI existent, **When** la page est affichee, **Then** les 3 ou 4 KPI principaux sont plus visibles que les descriptions longues.
3. **Given** des anomalies existent, **When** elles sont affichees, **Then** elles ont une priorite visuelle plus forte que les blocs informatifs.

---

### User Story 5 - Comprendre les etats vides (Priority: P2)

En tant qu'utilisateur, je veux comprendre pourquoi une page n'affiche aucune donnee afin de distinguer un etat sain d'une collecte manquante ou d'un filtre trop restrictif.

**Why this priority**: `No alert found for this period` ou `No cost found` ne dit pas toujours si tout va bien ou si les donnees manquent.

**Independent Test**: ouvrir les pages Alerts, FinOps et Jobs avec des donnees vides, puis verifier que chaque etat vide propose une explication et une action utile.

**Acceptance Scenarios**:

1. **Given** aucune alerte n'existe, **When** la page Alerts est affichee, **Then** le message indique que le scope est sain ou que rien n'est a traiter.
2. **Given** aucune donnee de cout n'est disponible, **When** la page FinOps est affichee, **Then** le message mentionne la collecte FinOps ou le scope.
3. **Given** une page sans resultats a cause de filtres, **When** l'etat vide est affiche, **Then** une action propose d'elargir la periode, changer le scope ou verifier la collecte.

---

### User Story 6 - Harmoniser les libelles principaux (Priority: P3)

En tant qu'utilisateur interne, je veux une interface linguistiquement coherente afin de reduire l'effort de comprehension.

**Why this priority**: le melange francais / anglais donne une impression moins finalisee, meme si ce n'est pas bloquant.

**Independent Test**: parcourir les pages principales et verifier que les libelles de base suivent une convention stable.

**Acceptance Scenarios**:

1. **Given** les libelles principaux sont visibles, **When** l'utilisateur parcourt l'interface, **Then** `Start`, `End`, `Refresh`, `No alert` et `To handle` sont harmonises.
2. **Given** un terme technique standard existe, **When** il est affiche, **Then** il peut rester en anglais s'il est attendu par les utilisateurs (`Databricks`, `FinOps`, `Unity Catalog`).
3. **Given** des messages d'erreur ou d'etat vide sont affiches, **When** ils sont lus, **Then** ils utilisent le meme ton et la meme langue que le reste de l'interface.

---

### User Story 7 - Entrer plus facilement dans l'application (Priority: P3)

En tant que nouvel utilisateur, je veux comprendre rapidement comment acceder au cockpit depuis la page d'accueil.

**Why this priority**: la page d'accueil est visuellement forte, mais les actions `Sign in` et `Initialize the cockpit` peuvent etre clarifiees.

**Independent Test**: ouvrir `/` en etat non authentifie et verifier que le CTA principal est visible, explicite et prioritaire.

**Acceptance Scenarios**:

1. **Given** l'utilisateur arrive sur `/`, **When** il n'est pas authentifie, **Then** l'action principale de connexion est evidente.
2. **Given** deux CTA restent visibles, **When** l'utilisateur les lit, **Then** la difference entre eux est claire.
3. **Given** le fond decoratif est affiche, **When** la page est rendue, **Then** il ne masque pas la comprehension du CTA principal.

---

## Edge Cases

- Auth active vs desactivee en local : les pages doivent rester testables sans SSO reel.
- Viewport etroit dans Cursor ou tablette : les filtres doivent rester utilisables et ne pas provoquer de chevauchement.
- Sidebar ouverte vs reduite : l'etat actif doit rester coherent dans les deux modes.
- `Mounir AI` ouvert ou ferme : ne doit pas casser le scroll ni cacher une action critique.
- Donnees absentes vs zero probleme : les messages doivent differencier "rien a traiter" de "donnees non collectees".
- Pages avec peu de donnees : ne pas ajouter de blocs decoratifs qui recreent de la lourdeur.
- Accessibilite : les tooltips ne doivent pas etre la seule source d'information pour les lecteurs d'ecran.

## Requirements

### Functional Requirements

- **FR-001**: Le header global des pages protegees MUST etre compacte pour afficher plus de contenu metier au premier ecran.
- **FR-002**: Les filtres `Env`, `Start`, `End` et `Range` MUST rester accessibles et modifiables apres compactage.
- **FR-003**: Un resume du scope actif SHOULD etre visible lorsque les filtres sont compactes ou replis.
- **FR-004**: Le menu lateral reduit MUST afficher des tooltips ou une aide equivalente pour chaque destination.
- **FR-005**: Les noms accessibles des liens de navigation MUST eviter les duplications de libelles.
- **FR-006**: L'etat actif de navigation MUST etre visible dans le menu ouvert et reduit.
- **FR-007**: Le bouton `Mounir AI` MUST ne pas recouvrir les actions principales des pages.
- **FR-008**: Les pages principales SHOULD afficher un verdict court avant les details longs.
- **FR-009**: Les KPI principaux SHOULD apparaitre avant les textes explicatifs longs.
- **FR-010**: Les etats vides MUST expliquer si l'absence de donnees signifie aucun probleme, filtre trop restrictif ou collecte indisponible lorsque cette information est connue.
- **FR-011**: Les etats vides SHOULD proposer une action utile quand elle existe.
- **FR-012**: Les libelles principaux SHOULD etre harmonises dans une langue cible stable.
- **FR-013**: La page d'accueil SHOULD rendre le CTA de connexion ou d'initialisation plus evident.
- **FR-014**: Les changements MUST conserver les routes et contrats API existants.

### Non-Functional Requirements

- **NFR-001**: Les changements doivent rester incrementaux et reviewables.
- **NFR-002**: Aucune nouvelle librairie UI lourde ne doit etre ajoutee pour ces ajustements.
- **NFR-003**: Les composants modifies doivent rester compatibles avec React 18, TypeScript et Tailwind.
- **NFR-004**: Les ajustements responsive doivent etre verifies au minimum sur desktop large, largeur moyenne type panneau Cursor, et petit viewport.
- **NFR-005**: Les changements doivent ameliorer l'accessibilite ou au minimum ne pas la degrader.

### Key Entities

- **Global Page Header**: titre, bouton retour, scope, dates, raccourcis de periode et actions principales.
- **Monitoring Scope Summary**: representation compacte du scope, de la periode et du range actif.
- **Sidebar Item**: lien ou groupe de navigation avec icone, libelle, tooltip, etat actif et nom accessible.
- **Floating Assistant Button**: point d'entree `Mounir AI`, avec etat normal, compact et interactions d'ouverture.
- **Empty State**: bloc d'information affichant cause probable, interpretation et action possible.
- **Page Verdict**: statut court donnant la conclusion operationnelle de la page.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Sur `/dashboard`, `/databricks`, `/databricksalerts` et `/databricksfinops`, les premiers KPI ou le verdict de page sont visibles plus haut qu'avant.
- **SC-002**: Le menu reduit expose un libelle comprehensible pour chaque icone au survol et via accessibilite.
- **SC-003**: Aucun lien de navigation principal n'a un nom accessible duplique comme `HomeHome`.
- **SC-004**: `Mounir AI` ne masque pas `Refresh`, `Export`, `Reset` ni les KPI principaux sur les viewports testes.
- **SC-005**: Les pages Alerts et FinOps ont des etats vides plus explicites que `No alert found` ou `No cost found`.
- **SC-006**: Les libelles `Start`, `End`, `Refresh` et messages d'etat prioritaires sont harmonises selon la langue choisie.
- **SC-007**: Les routes existantes continuent de fonctionner.
- **SC-008**: `npm run lint` et `npm run build` passent dans `packages/dcm-frontend`.

## Assumptions

- La cible principale est l'application frontend dans `packages/dcm-frontend`.
- Le design actuel reste la base : il faut l'ajuster, pas le remplacer.
- Les donnees backend actuelles restent disponibles avec les memes endpoints.
- Les ameliorations peuvent etre livrees par increments, en commencant par header, sidebar et `Mounir AI`.
- L'harmonisation linguistique peut etre faite par libelles directs avant de choisir un vrai systeme i18n.
