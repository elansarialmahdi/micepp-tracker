# Architecture - Phases 1 à 10

## Vue d’ensemble

MICEPP-Tracker est organisé en monorepo. Le navigateur communique uniquement avec le WAF public.
Celui-ci applique ModSecurity et OWASP CRS avant de transmettre au reverse proxy applicatif, qui sert
le frontend à la racine et transmet `/api/*` à FastAPI. PostgreSQL et Redis sont isolés sur un réseau
Docker interne et ne publient aucun port sur l’hôte.

```text
Navigateur :8080/:8443
       |
WAF ModSecurity + OWASP CRS
       |
Reverse proxy Nginx interne
       |-- /       -> React/Vite
       `-- /api/*  -> FastAPI
                         |-- PostgreSQL
                         `-- Redis
```

## Arborescence retenue

```text
backend/              API, configuration, accès aux dépendances et migrations
frontend/             application React, client API et tests d’interface
infra/reverse-proxy/  point d’entrée HTTP et en-têtes de sécurité
infra/waf/            règles locales et exclusions OWASP CRS étroites
infra/siem/           pipeline optionnel d’export des journaux
scanner-worker/       emplacement réservé au worker du sprint Scans
docs/                 décisions d’architecture et documentation
scripts/              futurs scripts d’exploitation contrôlés
```

## Décisions structurantes

- FastAPI ne possède pas de préfixe `/api` : ce préfixe appartient au reverse proxy. Les routes
  internes restent ainsi utilisables par les health checks Docker (`/health/live`).
- La configuration provient uniquement de l’environnement et est validée au démarrage avec
  Pydantic Settings.
- SQLAlchemy est configuré en mode asynchrone avec `asyncpg`.
- La readiness contrôle une requête PostgreSQL, Redis et la révision Alembic attendue. Elle ne
  contacte aucun service externe.
- La migration `20260713_0001` constitue la baseline, `20260713_0002` ajoute l’authentification,
  `20260713_0003` introduit les plateformes, `20260713_0004` les catégories et services et
  `20260713_0005` les notifications et l’audit, `20260713_0006` les imports Excel et
  `20260713_0007` les jobs de scan et détections temporaires, et `20260713_0008` le cache NVD,
  les candidats CPE et l’historique des vulnérabilités, puis `20260713_0009` les paramètres et
  exécutions de protection périodique.
- Le frontend conserve des variables CSS globales et des classes sémantiques simples pour faciliter
  le remplacement ultérieur par le design Figma.
- Les journaux API et reverse proxy sont structurés en JSON et partagent un identifiant de requête.

## Flux d’authentification

```text
Login + limites Redis
       |
       |-- access JWT court -> mémoire React
       `-- refresh opaque  -> hash PostgreSQL + cookie HttpOnly
                                  |
                                  `-- rotation à chaque renouvellement
```

Les cookies d’authentification utilisent `SameSite=Strict`, `Secure` en production et une validation
CSRF double-submit. Une réutilisation de refresh token révoque sa famille complète. Les autorisations
sont recalculées depuis les relations RBAC en base et vérifiées par les dépendances FastAPI.

## Plateformes

Les valeurs utilisateur et normalisées sont conservées séparément. Les URL sont limitées à HTTP(S),
sans identifiants intégrés ; les ports par défaut, noms d’hôte et adresses IPv6 sont normalisés. La
recherche et les filtres sont exécutés par PostgreSQL avec pagination bornée et tri déterministe.
L’archivage est logique et les consultations actives excluent `archived_at` par défaut.

## Inventaire des services

Les catégories sont contraintes par `(platform_id, normalized_name)`. L’API refuse toute association
d’une catégorie à un service d’une autre plateforme. Les services sont dédupliqués par nom et version
normalisés au niveau métier, y compris à l’intérieur d’un ajout en lot. Les opérations en lot sont
atomiques et limitées à 100 lignes. Les données CPE sont déjà réservées dans le modèle, mais leur
alimentation reste isolée jusqu’à la phase NVD.

## Notifications et audit

`AuditEvent` est une table append-only protégée contre les mises à jour et suppressions ORM. Les
changements métier et d’authentification y sont inscrits avec l’acteur, l’identifiant de requête et,
quand il existe, le contexte de plateforme. `NotificationUserState` conserve séparément la lecture
et le masquage pour chaque utilisateur. `HistoryVisibilityState` applique le même principe à
l’historique : il mémorise un seuil de visibilité sans modifier les événements audités.

## Import Excel sécurisé

Le flux est découpé en upload, mapping/aperçu et confirmation. Le classeur est contrôlé comme archive
ZIP, lu avec `openpyxl` en mode lecture seule et `data_only`, puis supprimé du stockage temporaire.
Seules les valeurs nettoyées sont placées dans `ServiceImport`, avec une expiration d’une heure.
La confirmation crée catégories et services dans une transaction unique, applique la règle explicite
de doublons choisie par l’utilisateur et écrit un événement `service.import.excel` dans l’audit.

## Scanner asynchrone

L’API valide la cible et enregistre `ScanJob`, puis Celery délègue le travail au service
`scanner-worker`. La cible est résolue une seconde fois dans le worker afin de détecter un changement
DNS. Les adaptateurs partagent l’interface `ServiceDetector`; le mode mock, Nmap XML et le détecteur
HTTP interne sont isolés. Les résultats sont normalisés et fusionnés dans `DetectedService`, sans
exposer les preuves brutes au frontend. La confirmation crée les catégories et services sélectionnés
dans une transaction et inscrit `scan.confirm` dans l’audit.

## Frontières actuelles

Le scanner et le client NVD réels restent désactivés par défaut au profit d’adaptateurs mock
déterministes. Le dépôt configure l’export SIEM mais ne déploie aucun SIEM. Le certificat fourni par
l’image WAF sert uniquement au développement ; la production exige des certificats externes.

## NVD, CPE et vulnérabilités

Le backend est l’unique consommateur de l’API NVD et conserve sa clé hors du navigateur. Les
réponses CPE et CVE sont paginées, mises en cache avec expiration et rejouées après temporisation
sur les erreurs transitoires. Un CPE n’est sélectionné automatiquement qu’au-dessus du seuil de
confiance configuré et avec un écart suffisant sur le second candidat ; sinon l’interface demande
une validation humaine.

L’applicabilité d’une CVE repose sur les configurations CPE, le drapeau `vulnerable`, le statut NVD
et les bornes de version inclusives ou exclusives. Les liens service/CVE portent un état explicite
(`confirmed`, `probable`, `needs_review`, `not_affected`, `unknown`) et ne sont jamais supprimés :
une disparition lors d’une synchronisation renseigne `resolved_at`. Les notifications ne sont
créées que pour une nouvelle menace confirmée ou probable.

## Protection périodique

Celery Beat ne réalise aucun contrôle NVD directement : il vérifie qu’une exécution est due et crée
un `ProtectionJob` idempotent. Un worker dédié appelle le même pipeline que le bouton manuel. Un
verrou Redis avec jeton propriétaire interdit deux exécutions globales simultanées et son expiration
est renouvelée à chaque lot. Un heartbeat permet à l’ordonnanceur de reprendre un job abandonné
après un redémarrage.

Les compteurs du job sont validés après chaque service. Une panne limitée produit un statut
`partial` et conserve un résumé nettoyé des erreurs ; un échec global est rejoué avec backoff par
Celery. `RealtimeProtectionSetting` conserve l’intervalle, `last_run_at` et `next_run_at`, ce dernier
alimentant directement le compte à rebours React.

## Périmètre de sécurité de production

Le WAF officiel OWASP CRS est le seul conteneur qui publie des ports. Le mode développement utilise
`DetectionOnly`; la surcharge `docker-compose.prod.yml` force `On`, la redirection HTTPS et TLS 1.2
ou 1.3. Elle sélectionne aussi les images runtime/statique et exige les secrets, les origines CORS,
les clés JWT RS256 et les certificats. Les exclusions locales sont versionnées avant CRS et doivent
rester limitées à un faux positif précisément identifié.

Les limites applicatives Redis complètent le débit global Nginx : connexion par IP et identifiant,
imports, création de scans, contrôles NVD manuels et déclenchements de protection. Les dépassements
retournent `429` sans lancer le traitement coûteux.

```text
API / Nginx / WAF / workers
            |
       logs JSON stdout
            |
      Vector (profil siem)
            |
   HTTPS + jeton + tampon disque
            |
         SIEM externe
```

Les journaux techniques contiennent le service, l’environnement, l’identifiant de requête, l’acteur,
l’IP, la route, le statut et la durée lorsqu’ils sont disponibles. Les secrets sont masqués dans le
formateur API puis filtrés à nouveau par Vector. Ils restent distincts de `AuditEvent`, journal
métier append-only conservé en base.
