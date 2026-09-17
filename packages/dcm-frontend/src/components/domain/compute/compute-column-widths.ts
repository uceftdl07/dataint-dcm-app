/**
 * Échelle de largeurs de colonne des tableaux compute.
 *
 * Pourquoi une échelle nommée plutôt qu'un nombre littéral par colonne : les
 * 109 colonnes des 11 tableaux ne portent qu'une douzaine de sortes de contenu.
 * Écrire `width: 108` cinquante fois rend impossible de savoir si deux colonnes
 * ont la même largeur par intention ou par coïncidence — et donc impossible de
 * les ajuster ensemble. Le nom porte l'intention ; la valeur reste ajustable en
 * un endroit.
 *
 * Les valeurs sont calibrées sur le contenu réel observé en dev, en-tête compris :
 * les en-têtes sont en 10 px `uppercase tracking-[1.2px]`, ce qui les rend plus
 * larges qu'un texte de même longueur dans le corps du tableau. Une colonne dont
 * l'en-tête serait tronqué mais la valeur lisible reste un défaut — c'est
 * l'en-tête qui porte le sens de la colonne.
 *
 * Ce ne sont que des largeurs **de départ** : l'utilisateur les ajuste, et son
 * réglage est persisté par `useColumnWidths`.
 */
export const COLUMN_WIDTH = {
  /** Bouton ou icône seule. Marquée `resizable: false` : rien à y élargir. */
  action: 72,
  /** Nombre court sans unité : un compte, un pourcentage, un percentile. */
  number: 108,
  /** Badge compact : sévérité, taux de succès, drapeau. */
  badge: 120,
  /** Métrique numérique avec unité ou signe : « 1 234 ms », « 12,34 $ », « −8 % ». */
  metric: 128,
  /**
   * Durée en composantes : « 5d 17h 28m 56s ». Plus large que `metric` parce que le
   * pire cas fait quatre composantes, soit ~102 px en 12 px `font-semibold`, contre
   * 96 px utiles dans une colonne `metric` (128 − 32 de `px-4`) : elle serait coupée.
   */
  duration: 160,
  /** Libellé court d'une valeur énumérée : type, taille, SKU, déclencheur. */
  label: 132,
  /** Badge de statut avec son libellé, plus long qu'un badge compact. */
  status: 148,
  /** Horodatage, ou type de nœud (`Standard_DS3_v2`), ou libellé composé. */
  timestamp: 168,
  /** Étiquette libre saisie par un humain : tag de propriétaire, utilisateur. */
  tag: 184,
  /** Identifiant technique, ou couple d'horodatages, ou motif d'échec. */
  identifier: 200,
  /** Cellule composite : histogramme d'historique, message d'erreur. */
  composite: 220,
  /** Nom d'entité affiché avec son identifiant en dessous. */
  name: 240,
  /** Nom long et non tronquable sans perte : job, titre de recommandation. */
  longName: 300,
} as const;
