# Agent Mounir - Proposition d'implementation

## Objectif

Transformer la page `Talk to your Data` en un vrai agent conversationnel capable d'interroger les donnees DCM et de produire des reponses contextualisees sur les couts, les pipelines, la securite, la gouvernance, Databricks et l'usage des data products.

Initialement, Mounir etait principalement une experience frontend de demonstration avec des etapes de reflexion simulees et des reponses hardcodees. La Phase 0 connecte maintenant les intentions principales aux APIs DCM existantes, avant la future V1 backend agentique.

## Etat actuel

Le frontend est implemente dans :

- `packages/dcm-frontend/src/pages/TalkToYourData.tsx`
- route exposee : `/talk-to-data`
- raccourci global : bouton flottant "Mounir AI" dans l'application

Comportement actuel en Phase 0 :

- les messages sont stockes localement en React avec `useState`;
- les questions suggerees sont definies dans `SUGGESTED_QUESTIONS`;
- `handleSend()` detecte une intention simple par mots-cles;
- les intentions supportees appellent les fonctions existantes de `dcmApiClient`;
- les reponses live affichent leurs sources APIs;
- aucun LLM n'est appele;
- aucune requete Databricks n'est declenchee par Mounir directement.

Les donnees reelles visibles dans l'application viennent deja des endpoints DCM existants, par exemple :

- `/api/v1/dashboard/overview`
- `/api/v1/pipelines`
- `/api/v1/costs/summary`
- `/api/v1/security/alerts`
- `/api/v1/standard-checks`
- `/api/v1/data-product-usage/*`
- `/api/v1/databases`
- `/api/v1/clusters`

## Phase 0 - Demo de developpement avec APIs DCM live

Avant la V1 agentique complete, Mounir peut fournir une demo plus credible en utilisant directement les APIs backend existantes depuis le frontend.

Objectif :

- afficher clairement que Mounir est en version developpement;
- remplacer les reponses hardcodees principales par des syntheses construites depuis les APIs DCM;
- garder les suggestions comme raccourcis UX;
- guider l'utilisateur vers les domaines supportes quand une question libre n'est pas encore comprise.

Message utilisateur recommande :

```text
Mounir AI est en version developpement. Aujourd'hui, il repond aux questions couvertes par les APIs DCM disponibles. Les capacites conversationnelles avancees arrivent dans une prochaine version.
```

Intentions supportees en Phase 0 :

- couts : `GET /api/v1/costs/summary` et `GET /api/v1/costs/by-service`;
- pipelines en echec : `GET /api/v1/pipelines?status=failed`;
- securite : `GET /api/v1/security/alerts`;
- gouvernance : `GET /api/v1/standard-checks/score` et `GET /api/v1/standard-checks`;
- usage data products : `GET /api/v1/data-product-usage/overview` et `GET /api/v1/data-product-usage/top-consumers`;
- clusters et compute : `GET /api/v1/clusters`;
- bases de donnees : `GET /api/v1/databases`;
- vue globale : `GET /api/v1/dashboard/overview`.

Cette phase ne doit pas pretendre etre un agent LLM complet. Elle doit afficher une indication du type `Live DCM API` sur les reponses issues du backend et retourner un message clair pour les demandes non supportees.

## Architecture cible

Le frontend ne doit pas parler directement a Databricks ni au LLM. Il doit envoyer la question utilisateur au backend. Le backend joue le role d'orchestrateur : il comprend la question, choisit les bons outils, recupere les donnees, puis demande au LLM de synthetiser une reponse.

```text
Frontend /talk-to-data
        |
        v
POST /api/v1/talk-to-data/query
        |
        v
Backend Agent Mounir
  - analyse l'intention utilisateur
  - choisit les tools DCM
  - appelle les endpoints/services existants
  - interroge Databricks si necessaire
  - demande au LLM de synthétiser
        |
        v
Reponse structuree
  - answer
  - sources
  - metrics
  - follow_up_questions
```

## Endpoint backend propose

Ajouter un endpoint dans `packages/dcm-backend` :

```http
POST /api/v1/talk-to-data/query
```

Payload propose :

```json
{
  "message": "Compare mes couts Azure et AWS ce mois-ci",
  "start_date": "2026-04-25",
  "end_date": "2026-05-25",
  "cloud_provider": "all",
  "conversation_id": "optional"
}
```

Reponse proposee :

```json
{
  "answer": "Voici la synthese...",
  "sources": [
    "costs/summary",
    "pipelines",
    "standard-checks"
  ],
  "metrics": {
    "total_cost": 11200,
    "currency": "EUR"
  },
  "follow_up_questions": [
    "Quels services expliquent la hausse des couts ?",
    "Quels pipelines ont le plus d'echecs ?"
  ]
}
```

## Tools backend recommandes

Pour une V1 robuste, Mounir doit utiliser des tools controles plutot que generer du SQL libre.

Tools proposes :

- `get_dashboard_overview(start_date, end_date, cloud_provider)`
- `get_cost_summary(start_date, end_date, cloud_provider)`
- `get_costs_by_service(start_date, end_date, cloud_provider)`
- `get_pipelines(start_date, end_date, cloud_provider, status)`
- `get_security_alerts(start_date, end_date, cloud_provider, status)`
- `get_standard_checks(cloud_provider)`
- `get_data_product_usage_overview(start_date, end_date)`
- `get_top_data_product_consumers(start_date, end_date, metric, limit)`
- `get_databases(cloud_provider)`
- `get_clusters(cloud_provider)`

Ces tools peuvent reutiliser la logique backend existante au lieu de dupliquer les requetes SQL.

## LLM a utiliser

Options possibles :

1. Azure OpenAI
   - adapte si l'organisation a deja une gouvernance Azure/Entra;
   - simple pour generer des reponses en francais;
   - necessite endpoint, deployment et API key.

2. AWS Bedrock
   - adapte si l'execution backend reste cote AWS/ECS;
   - authentification via IAM role possible;
   - evite de stocker une API key si le role ECS est correctement configure.

3. Databricks Model Serving
   - interessant si l'equipe veut garder l'IA proche de Databricks;
   - utile pour evoluer ensuite vers un agent plus data/SQL;
   - necessite endpoint serving et droits Databricks.

Recommandation V1 : choisir le provider deja valide par DevOps/Securite. Si aucun choix n'est impose, AWS Bedrock est coherent avec un backend sur ECS, tandis qu'Azure OpenAI est coherent si les identites et politiques IA sont deja gerees cote Microsoft.

## Secrets et configuration

Exemple pour Azure OpenAI :

```text
DCM_LLM_PROVIDER=azure_openai
DCM_AZURE_OPENAI_ENDPOINT=https://...
DCM_AZURE_OPENAI_API_KEY=...
DCM_AZURE_OPENAI_DEPLOYMENT=...
DCM_AZURE_OPENAI_API_VERSION=2024-xx-xx
```

Exemple pour AWS Bedrock :

```text
DCM_LLM_PROVIDER=bedrock
DCM_AWS_BEDROCK_REGION=eu-central-1
DCM_AWS_BEDROCK_MODEL_ID=anthropic.claude-...
```

Les secrets doivent etre stockes dans AWS Secrets Manager et injectes dans ECS via la task definition, comme pour les secrets Databricks.

## Frontend a modifier

Dans `TalkToYourData.tsx` :

- remplacer les reponses hardcodees par un appel API;
- garder les suggestions de questions comme raccourcis UX;
- afficher les `sources` renvoyees par le backend;
- afficher les erreurs backend de facon lisible;
- conserver l'effet "thinking" mais le rendre base sur les etapes reelles si le backend les renvoie.

Le frontend devrait appeler :

```text
POST /api/v1/talk-to-data/query
```

via le client API existant `packages/dcm-frontend/src/api/dcmApiClient.ts`, afin de beneficier de l'injection du token Entra ID en production.

## Securite et garde-fous

Pour eviter qu'un agent genere des requetes dangereuses ou expose trop de donnees :

- ne pas exposer Databricks directement au frontend;
- ne pas laisser le LLM executer du SQL libre en V1;
- limiter Mounir a une liste de tools autorises;
- appliquer les filtres de date, cloud provider et pagination;
- journaliser les tools appeles sans logger les secrets ni les donnees sensibles;
- retourner les sources utilisees dans chaque reponse;
- prevoir des timeouts sur les appels backend/LLM;
- refuser les questions hors perimetre DCM.

## Plan d'implementation

### V1 - Agent controle par tools

Objectif : avoir un Mounir reel, stable et securise.

Travaux :

- creer les schemas request/response backend;
- creer `POST /api/v1/talk-to-data/query`;
- implementer un routeur d'intention simple;
- connecter 4 a 6 tools existants : couts, pipelines, securite, standard checks, data product usage, dashboard;
- ajouter un client LLM;
- generer une reponse en francais avec sources;
- brancher le frontend sur l'endpoint;
- ajouter tests unitaires backend pour le routage et les payloads.

### V2 - Conversation et memoire

Objectif : permettre les questions de suivi.

Travaux :

- ajouter `conversation_id`;
- stocker l'historique court cote backend ou cache;
- permettre les follow-up questions;
- ajouter des citations de sources plus precises;
- afficher dans l'UI les datasets/endpoints consultes.

### V3 - Text-to-SQL controle sur Unity Catalog

Objectif : permettre des analyses plus libres sur les tables DCM.

Travaux :

- definir une allowlist de schemas/tables Databricks;
- generer uniquement des requetes `SELECT`;
- interdire DDL/DML et fonctions dangereuses;
- valider le SQL avant execution;
- limiter le nombre de lignes;
- tracer chaque requete generee;
- ajouter une validation humaine ou un mode preview si necessaire.

## Definition of Done V1

Mounir peut etre considere comme "reel" quand :

- une question utilisateur declenche un appel backend;
- le backend interroge au moins un tool DCM reel;
- la reponse est generee par un LLM a partir de donnees reelles;
- la reponse affiche ses sources;
- les erreurs sont gerees proprement cote UI;
- les secrets LLM sont geres via Secrets Manager/ECS;
- les tests backend couvrent les intentions principales.
