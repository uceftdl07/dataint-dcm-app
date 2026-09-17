# Feature Specification: Mounir Live API Demo

**Feature Branch**: `003-mounir-live-api-demo`  
**Created**: 2026-05-25  
**Status**: Draft  
**Input**: Transformation de `/talk-to-data` depuis une demo hardcodee vers une demo de developpement basee sur les APIs DCM existantes

---

## Compréhension du besoin

### Objectif

Rendre la page `Talk to your Data` plus credible pour une demo locale en connectant Mounir AI aux APIs DCM deja disponibles, sans attendre la V1 agentique complete avec LLM et orchestration backend.

Aujourd'hui, `/talk-to-data` donne l'impression d'un assistant complet mais repond principalement avec des textes hardcodes. L'objectif de cette Phase 0 est de clarifier le statut "version developpement" et de faire produire les reponses principales a partir de donnees backend reelles.

### Hors périmètre

- Creer un nouvel endpoint backend agentique `/api/v1/talk-to-data/query`.
- Integrer Azure OpenAI, AWS Bedrock ou Databricks Model Serving.
- Permettre du SQL libre ou du text-to-SQL.
- Stocker une memoire conversationnelle.
- Logger les questions utilisateur cote backend.
- Modifier les contrats API DCM existants.

---

## User Scenarios & Testing

### User Story 1 — Transparence sur le statut demo/dev (Priority: P1)

En tant qu'utilisateur demo, je veux comprendre que Mounir AI est encore en version developpement afin de ne pas confondre cette experience avec un agent LLM complet.

**Why this priority**: la transparence evite de survendre la fonctionnalite tout en gardant une presentation credible.

**Independent Test**: ouvrir `/talk-to-data` et verifier qu'un message visible indique que Mounir utilise les APIs DCM disponibles et que les capacites conversationnelles avancees arriveront ensuite.

**Acceptance Scenarios**:

1. **Given** l'utilisateur ouvre `/talk-to-data`, **When** la page s'affiche, **Then** un badge ou message "version developpement" est visible.
2. **Given** l'utilisateur lit le message d'accueil, **When** il pose une question, **Then** il comprend que seules les questions couvertes par les APIs DCM sont supportees.

---

### User Story 2 — Reponses live pour les questions DCM principales (Priority: P1)

En tant qu'utilisateur DCM, je veux poser des questions simples sur couts, pipelines, securite, gouvernance et usage data products afin d'obtenir une synthese issue des APIs backend existantes.

**Why this priority**: c'est le coeur de la demo utile. Les suggestions doivent afficher de vraies donnees plutot que des chiffres inventes.

**Independent Test**: cliquer sur chaque question suggeree et verifier qu'au moins un appel `dcmApiClient` correspondant est effectue avec une reponse affichee.

**Acceptance Scenarios**:

1. **Given** une question de couts, **When** elle est envoyee, **Then** Mounir appelle les endpoints couts et affiche total, repartition cloud et top services.
2. **Given** une question sur les pipelines en echec, **When** elle est envoyee, **Then** Mounir appelle l'endpoint pipelines avec `status=failed` et affiche les echecs recents.
3. **Given** une question securite, **When** elle est envoyee, **Then** Mounir appelle l'endpoint security alerts et affiche les alertes actives.
4. **Given** une question gouvernance, **When** elle est envoyee, **Then** Mounir appelle les endpoints standard checks et score.
5. **Given** une question usage data products, **When** elle est envoyee, **Then** Mounir appelle les endpoints usage disponibles et affiche KPIs et top consommateurs.

---

### User Story 3 — Fallback clair pour les demandes non supportees (Priority: P2)

En tant qu'utilisateur, je veux une reponse claire si ma question n'est pas encore supportee afin de savoir quelles demandes essayer.

**Why this priority**: le champ libre reste disponible, mais l'experience doit rester honnete et guider l'utilisateur.

**Independent Test**: envoyer une question hors perimetre et verifier que Mounir ne pretend pas avoir analyse des donnees inexistantes.

**Acceptance Scenarios**:

1. **Given** une question non reconnue, **When** elle est envoyee, **Then** Mounir explique qu'il ne traite pas encore cette demande.
2. **Given** une question non reconnue, **When** la reponse s'affiche, **Then** elle propose les domaines supportes : couts, pipelines, securite, gouvernance, data products ou overview.

---

## Edge Cases

- Backend indisponible ou endpoint en erreur : afficher un message lisible et conserver le chat utilisable.
- Donnees vides : afficher une synthese vide explicite au lieu de faire croire a un probleme.
- Question en langue naturelle approximative : utiliser une detection simple par mots-cles, sans LLM.
- Requetes lentes : conserver l'indicateur de reflexion pendant l'appel API.
- Auth activee en production : passer uniquement par `dcmApiClient` pour conserver l'injection du token existante.
- Donnees potentiellement sensibles : ne pas afficher de secrets, tokens ou headers.

## Requirements

### Functional Requirements

- **FR-001**: `/talk-to-data` MUST afficher un statut "version developpement" ou equivalent.
- **FR-002**: Les questions suggerees SHOULD declencher des appels API reels via `dcmApiClient`.
- **FR-003**: Les intentions minimales supportees MUST couvrir couts, pipelines, securite, gouvernance, data product usage et overview.
- **FR-004**: Les reponses issues du backend MUST indiquer qu'elles viennent des APIs DCM live.
- **FR-005**: Les questions non reconnues MUST retourner un message de capacite non encore supportee.
- **FR-006**: Les erreurs API MUST etre affichees proprement sans exposer de details sensibles.
- **FR-007**: Le frontend MUST continuer a fonctionner sans nouvel endpoint backend.
- **FR-008**: Toute modification MUST respecter TypeScript strict, lint et build frontend.

### Non-Functional Requirements

- **NFR-001**: Aucun nouveau provider LLM ou secret ne doit etre introduit pour cette phase.
- **NFR-002**: La logique d'intention doit rester simple, explicite et facile a remplacer par le futur backend agentique.
- **NFR-003**: Les changements doivent rester scopes a la page Mounir, au client API si necessaire, aux tests et a la documentation.
- **NFR-004**: Les reponses doivent eviter d'inventer des metriques non renvoyees par le backend.

### Key Entities

- **Mounir Intent**: categorie detectee depuis la question utilisateur, par exemple `costs`, `pipelines`, `security`, `governance`, `data-product-usage`, `overview` ou `unsupported`.
- **Live API Response**: reponse construite depuis un ou plusieurs endpoints DCM existants.
- **Development Mode Banner**: message visible indiquant le statut Phase 0 de Mounir.
- **Source Badge**: indication visuelle montrant qu'une reponse vient des APIs DCM live.

## Success Criteria

### Measurable Outcomes

- **SC-001**: Les 3 questions suggerees initiales utilisent des donnees backend reelles ou un fallback API explicite.
- **SC-002**: Au moins 6 intentions sont reconnues par mots-cles sans LLM.
- **SC-003**: Une question hors perimetre affiche un message clair en moins d'une interaction.
- **SC-004**: `npm run lint`, `npm run typecheck` et les tests pertinents passent dans `packages/dcm-frontend`.
- **SC-005**: `docs/05-mounir-ai/AGENT-MOUNIR.md` reste aligne avec la Phase 0 et la future V1 agentique.

## Assumptions

- Le frontend tourne en dev sur `http://localhost:4000`.
- Le proxy Vite ou `VITE_API_BASE_URL` permet deja d'atteindre `dcm-backend`.
- Les endpoints existants documentes dans `dcmApiClient.ts` sont suffisants pour la demo transitoire.
- La future V1 agentique reutilisera cette experience comme base UX mais deplacera l'orchestration cote backend.
