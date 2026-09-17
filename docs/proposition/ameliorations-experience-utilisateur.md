# Proposition - Ameliorer l'experience utilisateur de l'interface DCM

## Objectif

Ameliorer la lisibilite, la navigation et la perception globale de l'interface DCM, sans changer le fond fonctionnel de l'application.

L'interface actuelle donne deja une impression professionnelle et coherente : design clair, cartes arrondies, navigation laterale, filtres globaux, modules metier bien identifies. Les ameliorations proposees visent surtout a rendre l'experience plus fluide pour un utilisateur qui arrive sur l'application et veut comprendre rapidement quoi regarder, ou cliquer, et quelle action effectuer.

## Diagnostic rapide

Points forts observes :

- Identite visuelle moderne et propre.
- Interface coherente entre les pages principales.
- Bon usage des cartes, compteurs et statuts.
- Navigation metier claire quand le menu lateral est ouvert.
- Page d'accueil avec une ambiance "enterprise" credible.
- Integration SSO Microsoft rassurante pour un outil interne.

Points a ameliorer :

- Le haut de page prend trop de place avant d'arriver aux donnees.
- Les filtres `Env`, `Start`, `End` et `Range` sont tres grands et repetes sur beaucoup de pages.
- Le menu lateral reduit est joli, mais pas toujours explicite sans libelles.
- Le bouton flottant `Mounir AI` masque parfois des actions ou des indicateurs.
- Certaines pages affichent beaucoup de texte avant les informations vraiment utiles.
- Les etats vides sont corrects, mais pourraient mieux guider l'utilisateur.
- Le melange francais / anglais donne une impression moins finalisee.

## Priorite 1 - Compactage du header et des filtres

Le principal probleme UX est la place prise par la zone de filtre globale. Sur plusieurs pages, l'utilisateur voit d'abord les filtres, puis doit descendre pour voir les vrais resultats.

Proposition :

- Reduire la hauteur des champs `Env`, `Start`, `End`.
- Mettre les dates sur une seule ligne quand la largeur le permet.
- Transformer `30d`, `90d`, `6m`, `1y` en petits boutons plus compacts.
- Ajouter un mode "filtres replie" apres le premier chargement.
- Garder uniquement le resume actif visible, par exemple : `All envs - 28/04/2026 - 28/05/2026 - 30d`.

Impact attendu :

- Plus de donnees visibles au premier ecran.
- Moins de sensation de lourdeur.
- Navigation plus rapide entre les pages.

## Priorite 2 - Ameliorer le menu lateral reduit

Le menu ouvert est clair, mais le menu reduit repose uniquement sur les icones. Pour un nouvel utilisateur, certaines icones ne suffisent pas a comprendre la destination.

Proposition :

- Ajouter des tooltips au survol des icones.
- Garder un indicateur actif plus visible sur la page courante.
- Eviter les libelles accessibles dupliques du type `HomeHome`, `DatabricksDatabricks`.
- Rendre les zones cliquables plus confortables.
- Verifier que les clics sur les icones ne sont pas interceptes par d'autres elements.

Impact attendu :

- Navigation plus intuitive.
- Moins d'hesitation pour les nouveaux utilisateurs.
- Meilleure accessibilite.

## Priorite 3 - Repositionner le bouton Mounir AI

Le bouton flottant `Mounir AI` est une bonne idee, car il rend l'assistant visible partout. En revanche, il est tres grand et peut cacher des boutons comme `Refresh`, des compteurs ou des actions secondaires.

Proposition :

- Reduire legerement la taille du bouton.
- Le placer plus bas ou plus a droite avec une marge de securite.
- Ajouter un etat compact, par exemple une simple icone ronde.
- Sur mobile ou petit viewport, le transformer en bouton fixe dans une barre basse.
- Eviter qu'il recouvre les actions principales.

Impact attendu :

- Assistant toujours visible, mais moins intrusif.
- Moins de conflit avec les actions de page.

## Priorite 4 - Clarifier la hierarchie des informations

Certaines pages affichent beaucoup d'informations descriptives avant les donnees. Le contenu est utile, mais l'utilisateur veut d'abord savoir si tout va bien, ce qui est en erreur, et quoi faire.

Proposition :

- En haut de page, afficher une conclusion courte : `Healthy`, `Action required`, `No data`, `To monitor`.
- Placer ensuite les 3 ou 4 KPI principaux.
- Mettre les textes explicatifs dans des blocs secondaires ou dans des tooltips.
- Donner plus de poids visuel aux anomalies et actions prioritaires.
- Standardiser les messages de resume entre les modules.

Exemple de structure recommandee :

1. Titre de page.
2. Resume du scope actif.
3. Verdict court.
4. KPI principaux.
5. Filtres avances.
6. Details, tableaux et recommandations.

Impact attendu :

- L'utilisateur comprend plus vite la situation.
- Les pages deviennent plus decisionnelles.

## Priorite 5 - Ameliorer les etats vides

Les pages FinOps et Alerts affichent correctement qu'il n'y a pas de donnees, mais l'etat vide peut etre plus utile. Un utilisateur doit comprendre si l'absence de donnees est normale, due au filtre, ou due a une collecte incomplete.

Proposition :

- Remplacer `No alert found for this period` par un message plus explicite.
- Ajouter une cause possible : aucun signal, filtre trop restrictif, collecte non disponible.
- Ajouter une action : changer la periode, verifier le scope, ouvrir collection status.
- Distinguer `zero probleme` de `donnees non collectees`.

Exemples :

- `Aucune alerte Databricks sur cette periode. Le scope selectionne est sain.`
- `Aucune donnee de cout disponible. Verifiez que la collecte FinOps est active pour ce scope.`
- `Aucun job affiche. Essayez une periode plus large ou verifiez la collecte des pipelines.`

Impact attendu :

- Moins de confusion.
- Meilleure confiance dans les donnees affichees.

## Priorite 6 - Harmoniser la langue et les libelles

L'interface melange francais et anglais : `Home`, `Refresh`, `Start`, `End`, `Recommandations`, `No alert`, `Sous check`, `To handle`. Ce n'est pas bloquant, mais cela donne une impression moins aboutie.

Proposition :

- Choisir une langue principale pour l'interface.
- Si l'audience est interne francaise, passer les libelles principaux en francais.
- Garder les termes techniques anglais uniquement quand ils sont standards : `Databricks`, `FinOps`, `Unity Catalog`, `Landing Zone`.
- Harmoniser les etats : `Active`, `Resolved`, `Dismissed`, `To handle`.

Exemples :

- `Start` devient `Debut`.
- `End` devient `Fin`.
- `Refresh` devient `Actualiser`.
- `No alert found for this period` devient `Aucune alerte sur cette periode`.
- `To handle` devient `A traiter`.

Impact attendu :

- Interface plus professionnelle.
- Moins d'effort cognitif pour l'utilisateur.

## Priorite 7 - Rendre les actions principales plus visibles

Les actions importantes existent, mais certaines sont basses dans la page ou proches du bouton flottant.

Proposition :

- Mettre `Refresh`, `Export`, `Reset` dans une barre d'actions claire.
- Differencier les actions principales et secondaires.
- Desactiver les boutons inutilisables avec une explication courte.
- Ajouter un feedback apres clic : chargement, succes, erreur.

Impact attendu :

- L'utilisateur comprend mieux ce qu'il peut faire.
- Les boutons desactives semblent moins "casses".

## Priorite 8 - Optimiser la page d'accueil

La page d'accueil avant connexion est visuellement interessante, avec le fond reseau et le positionnement cloud. Cependant, les actions principales ne sont pas assez evidentes au premier regard.

Proposition :

- Rendre `Sign in` ou `Initialize the cockpit` plus dominant.
- Clarifier la difference entre les deux boutons si les deux restent visibles.
- Ajouter une phrase courte sous le CTA principal : `Connectez-vous pour acceder au cockpit de supervision.`
- Reduire legerement l'effet decoratif si celui-ci masque les actions.

Impact attendu :

- Parcours d'entree plus direct.
- Meilleure comprehension pour un nouvel utilisateur.

## Quick wins recommandes

Actions rapides a fort impact :

- Reduire la hauteur des champs de filtre.
- Ajouter des tooltips sur le menu reduit.
- Repositionner le bouton `Mounir AI`.
- Harmoniser `Start`, `End`, `Refresh` en francais.
- Ameliorer les messages d'etat vide.
- Afficher un resume compact du scope actif.
- Mettre les KPI plus haut dans la page.

## Proposition de roadmap

### Phase 1 - Ajustements UX rapides

- Compactage des filtres.
- Repositionnement de `Mounir AI`.
- Tooltips du menu lateral.
- Harmonisation des principaux libelles.

### Phase 2 - Lisibilite metier

- Ajout d'un verdict court sur chaque page.
- Reorganisation des KPI.
- Amelioration des etats vides.
- Clarification des actions principales.

### Phase 3 - Finition produit

- Harmonisation complete de la langue.
- Verification responsive.
- Audit accessibilite.
- Tests utilisateur sur les parcours principaux.

## Resultat attendu

L'objectif n'est pas de refaire toute l'interface. La base est bonne. Les ameliorations doivent surtout rendre l'application plus rapide a comprendre, plus compacte, et plus orientee action.

Avec ces ajustements, l'interface peut passer d'une experience visuellement propre mais un peu lourde a une experience plus fluide, plus professionnelle et plus efficace pour les utilisateurs metier et techniques.
