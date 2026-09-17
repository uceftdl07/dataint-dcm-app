# Requirements checklist — 016 Project registration & roles

## Clarté & complétude
- [ ] Chaque FR est vérifiable (Given/When/Then ou critère binaire)
- [ ] Les 3 rôles cibles sont nommés sans ambiguïté (project admin / project viewer / platform admin)
- [ ] Le mapping des rôles hérités → 3 rôles est spécifié (FR-007, via migration 015)
- [ ] Formulaire Register : champs listés (email, BA-list, membres+rôles, LZ+workspaces défauts BA)
- [ ] Formulaire Join : champs listés (email, projet dans liste DCM)

## Cohérence
- [ ] Aucun rôle plat hérité ré-exposé en création (FR-006/FR-007)
- [ ] Suppression « My Landing Zones » couvre nav + route + page + parcours login LZ (FR-005)
- [ ] Contrainte 1:1 BA→projet (409) alignée avec 015 FR-011a

## Périmètre
- [ ] DataEng explicitement hors Epic (tables/migration = 015 T001)
- [ ] Dépendance 015 (endpoints `/projects*`) tracée en Prerequisites
- [ ] 2 Stories max, une par domaine (frontend, backend)

## Testabilité
- [ ] Story Frontend testable réseau mocké (Vitest)
- [ ] Story Backend testable pytest (201/202, 409, 403, énum rôles)

> Max 3 marqueurs `[NEEDS CLARIFICATION]` autorisés dans spec.md.
