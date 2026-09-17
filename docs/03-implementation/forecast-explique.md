# Prévision de consommation Databricks — fonctionnement et paramétrage

**Objet** : décrire ce que DCM projette, comment la valeur est produite, et la justification de chaque
règle de calcul.
**Périmètre** : tables `gold_dbx_compute_forecast_daily` et `gold_dbx_usage_forecast_daily`, ainsi que
leur restitution par l'API et l'interface.
**Public visé** : toute personne amenée à interpréter une valeur prévisionnelle affichée par DCM.
Aucun prérequis en séries temporelles ; chaque règle est accompagnée d'un exemple chiffré.

---

## 1. Objet de la prévision

La prévision répond à une question unique :

> À activité comparable à celle des deux dernières semaines, quelle consommation journalière attendre
> de cet objet, et dans quelle fourchette ?

### 1.1 Tables de restitution

Le résultat est stocké dans deux tables gold, une par domaine.

| Table | Métriques projetées | Grain d'une ligne |
|---|---|---|
| `gold_dbx_compute_forecast_daily` | Coût, DBU, CPU, requêtes, file d'attente des clusters / jobs / pipelines / warehouses | `(cloud_provider, workspace_id, object_type, object_id, metric_name, horizon_date)` |
| `gold_dbx_usage_forecast_daily` | Requêtes, consommateurs distincts, coût estimé, octets lus par data product (table UC) | `(cloud_provider, object_type, object_id, metric_name, horizon_date)` |

Une ligne correspond à **un objet, une métrique, un jour**. Elle porte la valeur attendue
(`predicted_value`) et son encadrement (`lower_bound`, `upper_bound`).

**Exemple**

| object_type | object_id | metric_name | horizon_date | predicted | lower | upper |
|---|---|---|---|---|---|---|
| `WAREHOUSE` | `wh-prod-bi` | `cost_usd` | 2026-09-18 | 42,10 | 31,40 | 52,80 |

Lecture : le 18 septembre, ce warehouse devrait coûter environ 42 $, très probablement entre 31 et
53 $.

### 1.2 Périmètre couvert

Côté compute, 11 combinaisons de type d'objet et de métrique :

| Type d'objet | Métriques projetées | Table source |
|---|---|---|
| `CLUSTER` (interactifs uniquement) | `cost_usd`, `dbu_quantity` | `gold_dbx_compute_cluster_cost_daily` |
| `CLUSTER` | `cpu_util_p95_pct` | `gold_dbx_compute_cluster_efficiency_daily` |
| `JOB` | `cost_usd`, `dbu_quantity` | `gold_dbx_compute_job_cluster_cost_daily` |
| `PIPELINE` | `cost_usd`, `dbu_quantity` | `gold_dbx_compute_pipeline_cost_daily` |
| `WAREHOUSE` | `cost_usd`, `dbu_quantity` | `gold_dbx_compute_warehouse_cost_daily` |
| `WAREHOUSE` | `query_count`, `queue_time_p95_ms` | `gold_dbx_compute_warehouse_query_performance_daily` |

Côté usage, un seul type d'objet (`DATA_PRODUCT`, soit une table Unity Catalog) et 4 métriques,
toutes issues de `gold_dbx_usage_table_popularity_daily`.

**Maille propre aux jobs et aux pipelines.** Un cluster de job reçoit un `cluster_id` neuf à chaque
exécution : `0912-081500-abcd` hier, `0913-081500-efgh` aujourd'hui. À la maille cluster, ces objets
n'accumulent donc jamais d'historique. La dépense d'un job est projetée à la maille **job** (`job_id`,
stable dans le temps), celle d'un pipeline à la maille **pipeline** (`dlt_pipeline_id`) ; les clusters
`JOB` et `PIPELINE` sont exclus de la maille `CLUSTER` afin qu'une même dépense ne soit pas comptée
deux fois.

---

## 2. Chaîne de production

```
  tables gold *_daily            observed              ai_forecast            table forecast
  (historique déjà        →  (fenêtre + éligibilité  →  (un modèle par   →   (futur reconstruit
   agrégé et validé)          + grille journalière)      objet)                à chaque run)
                                                                                   ↓
                                                                          backend FastAPI
                                                                                   ↓
                                                                          graphe dans l'UI
```

1. **La source est la couche gold, jamais le brut.** Le calcul lit les tables `*_daily` déjà
   agrégées, et non `system.billing.usage` en direct. Le coût prévu et le coût affiché ailleurs dans
   DCM proviennent ainsi de la **même** définition : une évolution de la règle de coût observé se
   propage automatiquement à la prévision.
2. **L'historique d'entraînement (`observed`) est construit** — cette étape porte l'essentiel de la
   logique métier (§4).
3. **`ai_forecast` ajuste un modèle par objet** et projette les jours suivants (§3).
4. **Le résultat est écrit en Delta**, puis servi par l'API et tracé dans l'interface (§6 et §7).

---

## 3. Moteur de calcul : `ai_forecast`

`ai_forecast` est une fonction SQL native de Databricks : elle reçoit un historique et retourne une
projection. **Aucun modèle statistique n'est implémenté dans DCM** — le code prépare les données en
entrée et interprète la sortie.

### 3.1 Paramètres d'appel

```sql
SELECT * FROM ai_forecast(
    observed  => TABLE(<historique préparé>),
    horizon   => DATE '2026-09-20',   -- borne haute de la projection
    time_col  => 'period_start',      -- colonne de date
    value_col => array('cost_usd', 'dbu_quantity'),
    group_col => 'object_key',        -- une série indépendante par objet
    frequency => 'D',                 -- pas journalier
    prediction_interval_width => 0.95,
    parameters => '{"global_floor": 0}'
)
```

**Une série par objet.** `group_col` n'accepte qu'**une** colonne, alors qu'un objet est identifié par
plusieurs (`cloud_provider`, `workspace_id`, `cluster_id`). Ces colonnes sont concaténées en une clé
unique séparée par `::` — `azure::adb-123::0912-081500-abcd` — puis redécoupées après l'appel. Chaque
objet disposant de son propre modèle, un warehouse en forte croissance n'influence pas la projection
d'un autre objet.

**Le pas de temps est imposé, non déduit.** `frequency => 'D'` fixe la granularité de sortie au jour.
Laissé libre, `ai_forecast` déduit le pas de l'historique fourni : une table interrogée les mardis et
jeudis peut produire un pas hebdomadaire, auquel cas un horizon de 7 jours retourne 1 ou 2 lignes au
lieu de 7.

**Les valeurs impossibles sont exclues.** `global_floor: 0` interdit une projection négative : une
série en forte décroissance franchirait sinon zéro, et un coût de −12 $ n'a pas de sens.
`cpu_util_p95_pct` reçoit en complément `global_cap: 100`, s'agissant d'un pourcentage.

**Le plafond est relatif à la série, pas seulement scalaire.** Sur une série à décrochement,
`ai_forecast` ajuste un modèle explosif sans lever d'erreur : la projection sort de plusieurs ordres de
grandeur au-dessus du réel. Un `global_cap` ne l'attrape pas, puisqu'il ignore l'échelle propre à
chaque série. Le plafond retenu est donc **10 × le maximum journalier observé de la série** : au-delà,
la ligne n'est pas publiée — pas plus qu'une `predicted_value` NULL. Les deux tables appliquent cette
borne ; `cpu_util_p95_pct` garde à la place son plafond absolu de 100.

**`upper_bound` est écrêtée à ce plafond, pas filtrée.** Une valeur projetée plausible peut porter un
intervalle qui ne l'est pas, et l'interface agrège les bornes de tous les objets pour tracer sa bande
(§7.1) : une seule borne aberrante y écrase la courbe du réalisé — la combinaison en quadrature n'y
change rien, un terme très supérieur aux autres dominant la racine. Écrêter conserve la ligne,
dont la valeur projetée reste bonne. La borne basse n'a besoin de rien : `global_floor` la tient à 0,
et elle reste sous une `predicted_value` déjà plafonnée.

**Exemple.** Maximum journalier observé de 5 000 requêtes, donc plafond à 50 000. Une projection de
8 000 est publiée telle quelle : la hausse est peut-être réelle. Une projection de 10 millions est
écartée, là où un plafond scalaire calibré sur les plus grosses tables du parc l'aurait laissée passer.
Une projection de 8 000 encadrée par `[0, 900 000]` est publiée avec sa borne haute ramenée à 50 000 —
une `upper_bound` égale au plafond est donc une valeur **tronquée**, pas la sortie du modèle. Une borne
que le modèle n'a pas calculée, elle, reste NULL : jamais remplacée par le plafond.

**Environnement d'exécution.** `ai_forecast` requiert un SQL Warehouse Pro ou Serverless ; le compute
générique d'un job Databricks n'en est pas un. Le SQL est donc **construit** en Python par une
fonction pure, puis **exécuté** sur le warehouse via l'API Statement Execution. Cette séparation rend
le calcul testable : les tests portent sur le texte SQL produit, sans warehouse.

### 3.2 Paramétrage retenu

| Paramètre | Valeur | Justification |
|---|---|---|
| Fenêtre d'entraînement | **14 jours** | Deux semaines complètes : le modèle observe deux fois chaque jour de la semaine, donc le motif semaine / week-end |
| Horizon | **7 jours** | Inférieur à la fenêtre : la projection ne dépasse pas la profondeur d'observation |
| Intervalle de prédiction | **0,95** | Valeur par défaut de `ai_forecast`, déclarée en configuration plutôt que laissée implicite |
| Historique minimum | **8 jours d'activité réelle** (compute et usage) | Strictement supérieur à l'horizon : on ne projette pas plus loin qu'on n'observe. En deçà, la série n'existe pas (§4.2) |
| Jour en cours | **exclu** (compute et usage) | Chargé partiellement, il se lit comme un effondrement et décale l'horizon d'un jour (§4.2) |
| Plafond de plausibilité | **10 × le maximum journalier de la série** | Filtre `predicted_value`, écrête `upper_bound` (§3.1) |

La fenêtre de 14 jours remplit **deux fonctions avec un seul filtre** : elle borne l'entraînement et
elle exclut de la prévision tout objet sans activité récente.

**Exemple.** Un cluster supprimé en mars n'a aucune ligne dans les 14 derniers jours. Il n'entre donc
pas dans `observed` et aucune ligne de prévision n'est produite pour lui, sans qu'aucune liste
d'exclusion soit à maintenir.

---

## 4. Constitution de l'historique d'entraînement

La qualité de la projection est déterminée par le contenu d'`observed`, régi par quatre règles.

### 4.1 Unicité du couple (objet, jour)

Certaines sources livrent **plusieurs lignes pour le même objet le même jour**, leur grain comportant
une dimension supplémentaire.

**Exemple.** Un pipeline DLT exécuté le matin en serverless et l'après-midi en classic apparaît deux
fois le 12 septembre dans `pipeline_cost_daily`, la colonne `compute_kind` faisant partie du grain :
12 $ puis 8 $. Le modèle lirait deux points à la même date. Une agrégation explicite ramène donc la
journée à **20 $ le 12 septembre**, soit une prévision par pipeline, toutes formes de compute
confondues.

Une prévision **par forme de compute** supposerait d'ajouter `compute_kind` à la clé d'objet, et non
de retirer l'agrégation.

**Choix de l'agrégat.** `SUM` pour les métriques additives — deux demi-journées composent une journée
— et `MAX` pour les métriques de distribution. Sur les sources de distribution actuelles
(`cluster_efficiency_daily`, `warehouse_query_performance_daily`), ce `MAX` ne combine en réalité
jamais deux valeurs : leur grain est déjà `(cloud_provider, workspace_id, cluster_id | warehouse_id,
period_start)`, soit exactement celui du regroupement, qui reçoit donc une ligne unique par jour. Il
satisfait l'exigence du `GROUP BY` — toute colonne de valeur regroupée requiert une fonction — et
préserve la justesse du calcul si l'une de ces sources acquérait une dimension de grain
supplémentaire. Dans cette hypothèse, aucun agrégat n'est pleinement correct, un p95 ne se
reconstituant pas à partir de deux p95 sans la distribution complète : `SUM` serait absurde (deux p95
de 60 % n'en font pas 120 %), `AVG` lisserait le pic (8 000 ms et 200 ms donneraient 4 100 ms), tandis
que `MAX` fournit une borne supérieure interprétable — au moins un sous-ensemble a atteint cette
valeur ce jour-là. C'est l'approximation prudente attendue d'un outil de surveillance.

### 4.2 Condition d'éligibilité

Un objet doit présenter au moins **8 jours d'activité réelle** dans la fenêtre, soit strictement plus
que l'horizon : on ne projette pas plus loin qu'on n'observe. Les séries plus courtes ne portent
qu'une part marginale du coût et des requêtes d'un parc — le filtre écarte donc beaucoup de bruit pour
peu de couverture perdue. Il s'applique sur la source, **avant** remplissage de la grille journalière :
un jour ajouté à 0 ne constitue pas un jour d'activité.

**Le jour en cours est exclu de la fenêtre.** Les tables source le portent dès la première exécution de
la journée, mais partiellement : lu tel quel, ce creux se lirait comme un effondrement réel, et
l'horizon s'ancrerait sur un jour incomplet — la prévision ne commencerait qu'au lendemain, laissant le
jour courant sans valeur ni observée ni prédite.

**Exemple.** Un cluster interactif lancé une seule fois, un mardi, pour 50 $. À partir d'un point
unique, un modèle ne peut que prolonger une droite constante : 50 $ par jour, soit **350 $ projetés
sur 7 jours** pour un cluster susceptible de ne jamais redémarrer. La très grande majorité des
`cluster_id` d'un parc ne comptant qu'un seul jour d'historique, la table de prévision serait sans ce
filtre majoritairement composée d'objets de ce type, et le total surévalué d'autant.

Un objet non éligible **n'a aucune ligne** en table, et non une ligne à zéro : « aucune prévision » et
« prévision nulle » sont deux affirmations distinctes, que l'interface différencie (§7).

### 4.3 Métriques additives et métriques de distribution

Cette distinction constitue la règle structurante du calcul.

| Nature | Métriques | Signification d'un jour sans ligne source | Agrégat | Jours manquants complétés à 0 |
|---|---|---|---|---|
| **Additive** | `cost_usd`, `dbu_quantity`, `query_count`, et les 4 métriques usage | **0** — le cluster était éteint, il a coûté 0 $ | `SUM` | **Oui** |
| **Distribution** | `cpu_util_p95_pct`, `queue_time_p95_ms` | **aucune valeur** — un cluster éteint n'a pas 0 % de CPU, il n'a pas de CPU | `MAX` | **Non** |

Densifier consiste à créer une ligne pour chaque objet éligible et chaque jour de la fenêtre, valorisée
à 0 lorsque la source n'en fournit pas.

**Exemple, métrique additive.** Un cluster actif du lundi au vendredi, 20 $ par jour, sur une fenêtre
de 14 jours, soit 10 jours actifs et 4 jours de week-end :

| Historique lu par le modèle | Niveau ajusté | Projection sur 7 jours |
|---|---|---|
| 10 points à 20 $ (jours actifs seuls) | 20 $/jour | **140 $** |
| 14 points : 10 × 20 $ + 4 × 0 $ | 200 $ / 14 ≈ 14,3 $/jour | **100 $** |

Les deux niveaux sont exacts mais ne répondent pas à la même question : le premier s'exprime par jour
**actif**, le second par jour **calendaire**. L'interface plaçant la valeur sur un axe de dates, le
second est celui attendu. Lire un niveau par jour actif sur un axe calendaire surévalue la dépense du
rapport `jours_calendaires / jours_actifs`, soit **+40 %** dans cet exemple, écart qui se cumule à
l'échelle du parc.

**Exemple, métrique de distribution.** Un warehouse interrogé 3 jours sur 14, avec un
`queue_time_p95_ms` de 8 000 ms ces jours-là. Compléter les 11 autres jours à 0 produirait un p95
proche de 0 et un tableau de bord concluant à l'absence d'attente, alors que le constat exact est
« lorsqu'il est interrogé, l'attente atteint 8 secondes ». Un percentile ne s'additionne ni ne se
moyenne avec des zéros : la série reste creuse et l'agrégat est `MAX`.

Cette distinction explique une particularité du code : `query_count` (additive) et `queue_time_p95_ms`
(distribution) proviennent de la **même** table source mais font l'objet de **deux appels distincts** à
`ai_forecast`. Un appel unique imposerait le même historique aux deux métriques, donc soit des zéros
sur un percentile, soit l'absence de zéros sur un décompte.

### 4.4 Calendrier de densification

Les jours de la grille sont les dates **distinctes présentes dans la source**, jamais une suite de
dates générée (`sequence()`).

**Exemple.** Le pipeline gold du 13 septembre n'a pas encore été exécuté au moment du calcul de la
prévision. Une suite générée créerait un 13 septembre à 0 $ **pour l'ensemble du parc** : le modèle
interpréterait un effondrement général de l'activité juste avant la projection et tirerait toutes les
prévisions vers le bas. En suivant les dates effectivement chargées, la grille s'arrête au dernier
jour disponible.

---

## 5. Détermination de l'horizon

`ai_forecast` projette **du lendemain de la dernière observation jusqu'à l'horizon demandé**.
L'horizon étant une date absolue (`aujourd'hui + 7`), le nombre de jours produits dépend de la
fraîcheur de la source.

**Exemple.** Au 13 septembre, horizon demandé au 20.

| Fraîcheur de la source | Sortie de `ai_forecast` | Dont jours déjà écoulés | Conservé après plafonnement |
|---|---|---|---|
| Chargée jusqu'au 12 | 13 → 20 sept., soit 8 jours | 0 | 13 → 19 sept. = **7 jours** |
| En retard de 2 jours (chargée jusqu'au 10) | 11 → 20 sept., soit 10 jours | 2 (11 et 12) | 11 → 17 sept. = **7 jours** |

Chaque passe est donc plafonnée sur **son propre** dernier jour observé, soit `dernier jour observé +
7`. Le nombre de jours conservés reste constant, et une source en retard le demeure visiblement — sa
projection s'arrête plus tôt — au lieu de produire des prévisions pour des jours déjà écoulés. Ce
plafonnement est nécessaire parce que les 6 tables sources compute n'ont pas la même fraîcheur : sans
lui, une passe en retard livrerait davantage de jours qu'une autre et les totaux ne seraient pas
comparables d'un type d'objet à l'autre.

Cette hétérogénéité justifie également les **7 passes** côté compute : une par table source, leur
fraîcheur et leur maille différant, à quoi s'ajoute la séparation additif / distribution du §4.3. Côté
usage, une table source unique et 4 métriques de même nature ne requièrent qu'un seul appel.

---

## 6. Cycle de vie de la table entre deux exécutions

La table de prévision est recalculée à chaque exécution selon une règle unique :

> **Le futur est reconstruit à chaque exécution, le passé est conservé.**

- Les lignes dont `horizon_date` est à venir et que l'exécution courante ne produit plus sont
  **supprimées**.
- Les lignes dont `horizon_date` est déjà écoulé **subsistent** : elles conservent la trace de la
  prévision émise, ce qui autorise une comparaison ultérieure entre prévision et réalisé.

**Nécessité de la suppression.** L'exécution du lundi projette le cluster X du mardi à lundi + 7. Le
mardi, X est arrêté : il passe sous le seuil d'éligibilité et l'exécution du jour ne le produit plus.
Sans suppression, ses lignes du lundi demeurent en base et l'API — qui additionne toutes les lignes du
jour demandé — les intègre au total. La prévision du jeudi cumulerait alors deux exécutions, dont un
objet qui n'existe plus.

**Garde-fou.** Lorsque le calcul retourne un résultat vide (warehouse indisponible, source en échec),
la suppression est désactivée pour cette exécution : un incident ne doit pas vider la table.

---

## 7. Restitution dans l'interface

L'interface agrège les objets du périmètre sélectionné : un workspace, un type d'objet, ou l'ensemble
du parc. Quatre précautions encadrent cette agrégation.

### 7.0 Deux natures de métrique, deux agrégations

L'agrégation dépend de la nature de la métrique, **la même distinction que celle appliquée à
l'entraînement** (§ densification) :

| Nature | Métriques | Agrégation multi-objets |
|---|---|---|
| Additive | `cost_usd`, `dbu_quantity`, `query_count` | **somme** |
| Distribution | `cpu_util_p95_pct`, `queue_time_p95_ms` | **moyenne** |

Sommer une métrique de distribution n'a pas de sens : 50 clusters à 40 % afficheraient 2000 %, et des
p95 de temps d'attente additionnés sur 30 warehouses donneraient une durée que personne n'a attendue.
La courbe du réalisé n'existe de toute façon que pour `cost_usd` et `dbu_quantity`
(`_ACTUAL_COST_METRICS`), les seules reconstructibles depuis les tables de coût : pour les trois
autres, le trait plein est l'ajustement du modèle, sur la même base agrégée.

### 7.1 Interprétation de la bande

La valeur projetée s'agrège selon le tableau ci-dessus, **les bornes jamais par simple somme**.
L'espérance d'un total est le total des espérances, quelle que soit la corrélation entre objets ; en
revanche chaque borne porte le même 95 %, et en additionner N décrirait le jour où tous les objets
atteignent leur borne **en même temps** — bien moins probable que 95 %.

**Exemple.** 10 clusters, chacun prévu dans `[8 $, 12 $]`, soit une demi-largeur de 2 $. La somme des
bornes vaudrait `[80 $, 120 $]`, alors qu'atteindre 120 $ suppose les **10** maximums le même jour.
L'interface combine donc les demi-largeurs en **quadrature** — `√Σ demi²`, l'erreur type d'une somme
de termes indépendants : `√(10 × 2²) ≈ 6,3 $`, soit `[93,7 $, 106,3 $]` autour de 100 $. La bande
croît en `√N` là où la somme croissait en `N`, et redevient un intervalle à ~95 % du total.

Sur une métrique de **distribution**, la demi-largeur reçoit le même `1/N` que sa valeur centrale :
`√Σ demi² / N`. Deux clusters à 30 % et 50 %, chacun à ±10, donnent 40 % encadré par
`√(2 × 10²) / 2 ≈ 7,1`, soit `[33 %, 47 %]`.

Sur un seul objet, la racine d'un carré unique redonne exactement la demi-largeur du modèle : la bande
est alors son intervalle propre, sans approximation, pour l'une comme pour l'autre nature.

**L'hypothèse d'indépendance est une approximation, et elle sous-estime.** Des objets pilotés par une
même charge bougent ensemble ; un parc parfaitement corrélé justifierait la somme d'origine. La bande
est donc un plancher d'incertitude, pas un majorant. L'interface distingue les deux cas :
« Confidence interval » sur un objet, « Confidence interval over N objects (combined) » au-delà.

### 7.2 Cohérence de périmètre entre réalisé et projection

Sur le graphique compute, le trait plein (réalisé) et le trait pointillé (projection) partagent un
axe : ils doivent couvrir exactement les mêmes objets. La projection somme **clusters interactifs,
jobs, pipelines et warehouses** ; la courbe du réalisé lit les **quatre** rollups correspondants, en
excluant les clusters `JOB` et `PIPELINE` de la branche cluster afin de ne compter aucun objet deux
fois.

**Exemple.** Un job serverless à 30 $ par jour n'exploite aucun cluster, donc n'apparaît dans aucune
table cluster. Une courbe de réalisé limitée aux clusters et aux warehouses passerait
systématiquement 30 $ par jour **sous** le pointillé, ce qui se lirait comme une surévaluation par DCM
alors qu'il s'agirait d'un écart de périmètre.

### 7.3 Absence de donnée

Un jour connu du réalisé mais absent de la table de prévision n'est **pas** tracé à 0 : le point est
omis. Un point à 0 signifierait « dépense nulle prévue », alors que l'information exacte est « aucune
prévision pour ce jour ». La même règle s'applique aux valeurs affichées, où l'absence est rendue par
« — ».

---

## 8. Lecture du graphique

| Élément | Signification |
|---|---|
| Trait plein | Le **réalisé** observé ou, à défaut, l'ajustement du modèle sur le passé |
| Valeur affichée | La **somme** du parc pour une métrique additive, sa **moyenne** pour une métrique de distribution (§7.0) |
| Trait pointillé | La **projection**, qui repart du dernier point effectivement tracé |
| Bande colorée | Intervalle à ~95 % : la borne du modèle sur **un** objet, la combinaison en quadrature sur plusieurs (§7.1) |
| Interruption de la courbe | Aucune donnée pour ce jour, en aucun cas un zéro implicite |
| « — » à la place d'une valeur | La métrique n'existe pas pour ce point |

---

## 9. Limites d'usage

- **La prévision n'est pas un budget.** 7 jours projetés à partir de 14 jours d'historique : le modèle
  prolonge une tendance récente. Il n'anticipe ni une migration, ni la création d'un job, ni une
  décision de gel des dépenses.
- **Un objet trop récent n'y figure pas.** Moins de 8 jours d'activité implique l'absence de ligne. Un
  cluster créé la veille apparaît dans les coûts observés, mais pas dans la prévision.
- **Une série qui change brutalement de niveau n'est pas projetée.** Si le modèle dépasse 10 × le
  maximum journalier observé de la série, la ligne n'est pas publiée : la somme d'un périmètre est
  donc un **minorant**, jamais un total exhaustif.
- **Une `upper_bound` égale au plafond est une valeur tronquée.** Elle marque l'endroit où le modèle
  annonçait davantage, pas la borne qu'il a calculée : lue comme un pire cas, elle le sous-estime.
- **Les percentiles ne s'additionnent pas.** La somme de plusieurs `p95` donne un ordre de grandeur,
  jamais le p95 du parc.
- **La bande agrégée est pessimiste par construction.** Elle décrit le cas où tous les objets dévient
  dans le même sens le même jour.
- **Une prévision n'est pas une mesure.** Lorsque le réalisé existe pour un jour, c'est lui qui est mis
  en avant dans les chiffres clés, jamais la projection.

---

## 10. Références dans le code

| Rôle | Fichier |
|---|---|
| SQL du forecast compute (7 passes, fonction pure) | [pipelines/gold_dbx_compute/forecast.py](../../packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/forecast.py) |
| Paramétrage compute (fenêtre, horizon, éligibilité, purge) | [pipelines/gold_dbx_compute/specs.py](../../packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/specs.py) |
| Écriture compute et garde-fou d'exécution vide | [pipelines/gold_dbx_compute/entrypoint.py](../../packages/dcm-databricks-pipeline/pipelines/gold_dbx_compute/entrypoint.py) |
| SQL du forecast usage (1 passe, 4 métriques) et écriture | [pipelines/gold_dbx_usage/forecast_daily.py](../../packages/dcm-databricks-pipeline/pipelines/gold_dbx_usage/forecast_daily.py) |
| Paramétrage usage | [pipelines/gold_dbx_usage/specs.py](../../packages/dcm-databricks-pipeline/pipelines/gold_dbx_usage/specs.py) |
| API compute (projection et courbe du réalisé) | [app/api/services/compute_metrics_forecast.py](../../packages/dcm-backend/app/api/services/compute_metrics_forecast.py) |
| Widget compute (tracé, bornes, libellés) | [components/domain/compute/forecast-widget.tsx](../../packages/dcm-frontend/src/components/domain/compute/forecast-widget.tsx) |
| Cartes de tendance usage | `components/domain/uc-usage/uc-usage-trend-cards.tsx`, livré avec les pages Usage des tables UC |

Le SQL est produit par des **fonctions pures** (`render_forecast_query`, `render_forecast_write_sql`) :
elles construisent un texte sans l'exécuter, ce qui permet de tester le calcul par assertion sur le
SQL généré, sans SQL Warehouse.

Côté usage, le calcul **et** l'écriture Delta s'exécutent intégralement sur le warehouse
(`CREATE TABLE AS SELECT` à la première exécution, `MERGE INTO` ensuite) : à l'échelle du parc réel,
soit environ 530 000 data products × 4 métriques × horizon, le transit des lignes par le driver Python
n'est pas viable.
