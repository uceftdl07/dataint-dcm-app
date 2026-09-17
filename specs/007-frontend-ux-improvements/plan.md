# Implementation Plan: Frontend UX Improvements

**Branch**: `007-frontend-ux-improvements` | **Date**: 2026-05-28 | **Spec**: `specs/007-frontend-ux-improvements/spec.md`

**Input**: Feature specification from `/specs/007-frontend-ux-improvements/spec.md`

## Summary

Ameliorer l'experience utilisateur du frontend DCM par petites touches ciblees : compacter le header global et ses filtres, rendre le menu reduit plus clair, repositionner `Mounir AI`, clarifier les etats vides et harmoniser les libelles visibles. Le but est d'augmenter la lisibilite et l'efficacite sans changer les endpoints backend ni reconstruire le design system.

## Technical Context

- **Frontend**: React 18, TypeScript, Vite, Tailwind CSS, Lucide.
- **Routing**: routes React existantes dans `packages/dcm-frontend/src`.
- **Auth**: MSAL / Entra ID, avec mode local deja utilise.
- **Backend**: inchange, les API existantes restent la source des donnees.
- **Testing**: lint/build frontend, tests frontend existants si disponibles, verification manuelle navigateur.
- **Primary UX Targets**: `/`, `/dashboard`, `/databricks`, `/databricksalerts`, `/databricksfinops`, `/monitoringreports`.

## Constitution Check

- **Test-First & Code Quality**: ajouter ou adapter des tests lorsque les composants partages sont modifies, notamment header/sidebar/empty states.
- **Explicit Architecture & Modularity**: privilegier les composants partages existants plutot que dupliquer les ajustements page par page.
- **Security & Secrets Management**: aucun changement sur auth, tokens ou secrets.
- **Observability & Traceability**: conserver les messages d'erreur utiles et les feedbacks de chargement.
- **Simplicity & Versioning**: livrer des increments courts, sans refonte visuelle massive.

## Project Structure

```text
specs/007-frontend-ux-improvements/
+-- spec.md
+-- plan.md
+-- tasks.md

docs/proposition/
+-- ameliorations-experience-utilisateur.md

packages/dcm-frontend/src/
+-- components/
|   +-- layout/
|   +-- ui/
|   +-- domain/
+-- config/
|   +-- navigation.ts
+-- pages/
+-- App.tsx
+-- ...
```

Les chemins exacts des composants seront confirmes pendant l'implementation en lisant le frontend actuel. Cette spec ne doit pas forcer une nouvelle arborescence si les composants existent deja ailleurs.

## Proposed Design

### Phase 1 - Audit court des composants partages

- Identifier le composant qui rend le layout protege, le header global, les filtres de periode/scope, la sidebar et le bouton `Mounir AI`.
- Identifier les composants d'etat vide et de KPI deja existants.
- Relever les libelles principaux a harmoniser.

### Phase 2 - Header et filtres compacts

- Reduire la hauteur des champs globaux.
- Adapter la disposition responsive :
  - desktop large : filtres sur une ou deux lignes compactes ;
  - largeur moyenne : resume actif + controles accessibles ;
  - petit viewport : pile lisible, sans chevauchement.
- Ajouter un resume du scope actif lorsque les filtres sont replis ou visuellement compactes.
- Conserver les memes valeurs et handlers existants.

### Phase 3 - Sidebar reduite et accessibilite

- Ajouter tooltips ou labels accessibles aux items du menu reduit.
- Corriger les noms accessibles dupliques si presents.
- Rendre l'etat actif visible avec une couleur, un fond ou un indicateur stable.
- Verifier les zones cliquables sur menu ouvert et reduit.

### Phase 4 - Bouton flottant Mounir AI

- Revoir taille, position et marges du bouton.
- Eviter les conflits avec `Refresh`, `Export`, `Reset`, KPI et compteurs.
- Ajouter un mode compact si le viewport est trop etroit.
- Verifier que l'ouverture/fermeture de l'assistant ne casse pas le scroll.

### Phase 5 - Hierarchie de page, actions et etats vides

- Ajouter ou renforcer un verdict court sur les pages de monitoring.
- Faire remonter les KPI principaux avant les textes longs.
- Standardiser les actions `Refresh`, `Export`, `Reset` dans une zone claire quand possible.
- Ameliorer les messages vides des pages Alerts, FinOps, Jobs et Monitoring Reports.

### Phase 6 - Harmonisation des libelles et accueil

- Choisir une langue cible pour les libelles principaux de l'interface.
- Harmoniser les mots frequents : `Start`, `End`, `Refresh`, `No alert`, `To handle`, `Reset`.
- Clarifier la page d'accueil non authentifiee :
  - CTA principal visible ;
  - difference claire entre connexion et initialisation si les deux restent affiches ;
  - texte court de guidance.

## Risks

- Les filtres globaux peuvent etre utilises par beaucoup de pages : un changement trop large peut provoquer des regressions visuelles.
- Le bouton `Mounir AI` peut etre positionne par un composant global : il faut verifier tous les viewports avant validation.
- Harmoniser les libelles sans i18n peut creer de la dette si plusieurs langues sont requises plus tard.
- Une reduction trop forte du header peut nuire a la comprehension du scope actif.
- Les etats vides dependent parfois de la connaissance backend : ne pas promettre une cause si le frontend ne peut pas la connaitre.

## Validation

- Lancer `npm run lint` dans `packages/dcm-frontend`.
- Lancer `npm run build` dans `packages/dcm-frontend`.
- Lancer les tests frontend si une commande existe.
- Verifier manuellement :
  - `/` non authentifie ;
  - `/dashboard` ;
  - `/databricks` ;
  - `/databricksalerts` ;
  - `/databricksfinops` ;
  - menu ouvert et reduit ;
  - `Mounir AI` sur desktop et largeur moyenne.
- Verifier qu'aucune route existante n'est cassee.
