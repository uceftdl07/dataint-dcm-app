# Spécification 007 — Améliorations UX Frontend DCM

## Objectif

Améliorer l’expérience utilisateur (UX) et le design de l’interface frontend DCM pour une navigation plus fluide, une meilleure lisibilité des rapports, et une cohérence graphique accrue.

## Problèmes constatés
- Chargement visuel peu explicite lors de la génération des rapports (spinner générique, pas de feedback contextuel)
- Cartes de rapports peu différenciées (manque de hiérarchie visuelle)
- Filtres et sélecteurs de dates perfectibles (UX, accessibilité)
- Boutons d’action (refresh, download) peu mis en valeur
- Navigation latérale dense, icônes peu explicites pour certains modules
- Manque de feedback utilisateur lors de l’actualisation ou de l’absence de données

## Propositions d’amélioration

### 1. Loader & Feedback
- Remplacer le spinner générique par un loader contextuel (ex : logo animé, message « Rapport en cours de génération… »)
- Afficher un squelette de cartes pendant le chargement
- Ajouter un message explicite en cas d’absence de données (« Aucun rapport disponible pour la période sélectionnée »)

### 2. Cartes de rapports
- Accentuer la hiérarchie visuelle (titres, sous-titres, badges de statut)
- Utiliser des couleurs et icônes pour différencier les domaines (santé, coût, gouvernance, alertes, Unity Catalog…)
- Ajouter un effet hover et une animation d’apparition

### 3. Filtres & Sélecteurs
- Améliorer l’ergonomie des sélecteurs de dates (calendrier, raccourcis 7j/30j/90j…)
- Grouper les filtres environnement, période, domaine dans une barre dédiée
- Rendre les filtres accessibles clavier et mobile

### 4. Actions principales
- Mettre en avant les boutons « Rafraîchir » et « Télécharger » (taille, couleur, placement)
- Ajouter un tooltip explicatif sur chaque action

### 5. Navigation
- Clarifier les icônes de la barre latérale (tooltips, refonte graphique si besoin)
- Ajouter un indicateur de page active

### 6. Responsive & Accessibilité
- Optimiser l’affichage sur petits écrans (cartes empilées, navigation repliable)
- Contraste renforcé pour les textes et boutons
- Support des lecteurs d’écran (aria-labels, focus management)

## Critères d’acceptation
- L’utilisateur comprend immédiatement l’état de chargement ou d’erreur
- Les rapports sont plus lisibles et différenciés visuellement
- Les actions principales sont accessibles et explicites
- L’interface est utilisable sur desktop et mobile
- Accessibilité AA respectée sur les écrans principaux

---
Rédigé le 28/05/2026 — Sprint 8 DCM
