# MICEPP-Tracker

Application de supervision MICEPP-Tracker. Les dix premières phases couvrent le socle sécurisé,
l’inventaire, les notifications, l’audit, l’import Excel, les scans, la NVD, la protection périodique
et le durcissement de production.

## Prérequis

- Docker Engine avec Docker Compose v2
- Make (optionnel)
- Pour un lancement hors Docker : Python 3.12+ et Node.js 22+

## Démarrage rapide

1. Copier `.env.example` vers `.env`.
2. Remplacer au minimum `APP_SECRET_KEY` et `POSTGRES_PASSWORD`.
3. Démarrer l’environnement :

   ```sh
   docker compose up --build
   ```

4. Ouvrir <http://localhost:8081>.

Au premier démarrage, l’API attend PostgreSQL et Redis, applique `alembic upgrade head`, initialise
les permissions et l’administrateur, puis démarre.
Les données PostgreSQL et Redis sont conservées dans des volumes Docker nommés.

## Points de contrôle

- Interface : <http://localhost:8081>
- Liveness via proxy : <http://localhost:8081/api/health/live>
- Readiness via proxy : <http://localhost:8081/api/health/ready>
- Documentation API en développement : <http://localhost:8081/api/docs>

La liveness indique que le processus API répond. La readiness retourne `503` tant que PostgreSQL,
Redis ou la migration attendue ne sont pas prêts.

## Guide complet du tracker

### Rôle de l'application

MICEPP-Tracker sert à suivre la sécurité d'un parc de plateformes. L'application permet de créer des
plateformes, d'y inventorier des services, d'importer des services depuis Excel, de lancer des scans
contrôlés, de vérifier les vulnérabilités connues et de notifier les utilisateurs lorsqu'une menace
est détectée. Elle conserve aussi un historique d'audit des opérations importantes.

### Architecture d'exécution

Le navigateur ne parle pas directement à l'API. Le trafic passe d'abord par le WAF OWASP CRS, puis
par le reverse proxy Nginx. Nginx sert le frontend React sur `/` et transmet les appels `/api/*` à
FastAPI.

```text
Navigateur :8081/:8443
       |
WAF ModSecurity + OWASP CRS
       |
Reverse proxy Nginx interne
       |-- /       -> React/Vite
       `-- /api/*  -> FastAPI
                         |-- PostgreSQL
                         `-- Redis
```

Les workers Celery utilisent la même base PostgreSQL et Redis pour traiter les scans et la protection
périodique en arrière-plan. Les données persistantes restent dans les volumes Docker
`postgres-data`, `redis-data`, `frontend-node-modules` et `vector-data`.

### Technologies utilisées

- Backend : Python 3.12, FastAPI, Uvicorn, SQLAlchemy asynchrone, asyncpg, Alembic, Pydantic
  Settings, Redis, Celery, PyJWT, argon2-cffi, httpx et openpyxl.
- Frontend : React 19, TypeScript, Vite, React Router, TanStack React Query, react-hook-form, zod,
  lucide-react et CSS applicatif.
- Infrastructure : Docker Compose, PostgreSQL 17, Redis 7.4, Nginx, OWASP ModSecurity CRS et Vector
  pour l'export SIEM optionnel.
- Scan et sécurité : mode mock, Nmap, WhatWeb, détecteur web interne, NVD, CVE/MITRE, OSV et deps.dev.
- Tests et qualité : pytest, ruff, Vitest, Testing Library et Playwright.
- Lanceur Windows : .NET 8 Windows Forms, publié sous le nom `MICEPP-Manager.exe`.

### Services Docker

- `postgres` stocke les utilisateurs, plateformes, services, imports, scans, vulnérabilités,
  notifications et événements d'audit.
- `redis` sert au courtier Celery, au backend de résultats et aux verrous/limites de débit.
- `api` démarre les migrations Alembic, initialise l'administrateur, puis lance FastAPI sur le port
  interne `8000`.
- `frontend` lance Vite en développement ou sert le build statique en production.
- `scanner-worker` exécute les jobs de scan dans la file Celery `scans`.
- `protection-worker` exécute les contrôles périodiques de vulnérabilités dans la file `protection`.
- `scheduler` lance Celery Beat et crée les jobs de protection lorsque leur prochaine exécution est
  due.
- `reverse-proxy` route `/` vers le frontend et `/api/*` vers l'API.
- `waf` est l'unique point d'entrée publié. Par défaut, HTTP est publié sur
  <http://localhost:8081> et HTTPS sur <https://localhost:8443>.
- `log-collector` est optionnel et s'active avec le profil `siem` pour envoyer les logs vers un SIEM.

### Démarrer, arrêter et reconstruire

Pour démarrer l'environnement complet :

```sh
docker compose up --build
```

Pour démarrer en arrière-plan :

```sh
docker compose up -d
```

Pour arrêter sans supprimer les conteneurs ni les volumes :

```sh
docker compose stop
```

Pour arrêter et supprimer les conteneurs/réseaux Compose tout en gardant les volumes :

```sh
docker compose down
```

Pour reconstruire les images après modification du code ou des dépendances :

```sh
docker compose up -d --build
```

### Configuration principale

La configuration est lue depuis l'environnement, avec `.env` comme fichier local conseillé. Les
valeurs importantes sont :

- `APP_ENV`, `APP_SECRET_KEY`, `APP_NAME`, `APP_VERSION`, `APP_LOG_LEVEL` pour l'environnement
  applicatif.
- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `DATABASE_URL` pour PostgreSQL.
- `REDIS_URL` pour Redis et Celery.
- `ALLOWED_ORIGINS`, `HTTP_PORT`, `HTTPS_PORT`, `SERVER_NAME` pour l'exposition réseau.
- `JWT_ALGORITHM`, `JWT_PRIVATE_KEY`, `JWT_PUBLIC_KEY`, `JWT_ACCESS_TTL_SECONDS`,
  `JWT_REFRESH_TTL_SECONDS` pour l'authentification.
- `BOOTSTRAP_ADMIN_USERNAME`, `BOOTSTRAP_ADMIN_PASSWORD`, `BOOTSTRAP_ADMIN_DISPLAY_NAME` pour le
  premier administrateur.
- `SCAN_DETECTOR_MODE`, `ALLOWED_SCAN_NETWORKS`, `ALLOW_PRIVATE_NETWORK_SCANS`, `NMAP_BINARY`,
  `WHATWEB_ENABLED` et `WHATWEB_BINARY` pour les scans.
- `NVD_MODE`, `NVD_API_KEY`, `OSV_MODE`, `CVE_API_URL` pour les sources de vulnérabilités.
- `REALTIME_DEFAULT_INTERVAL_SECONDS`, `REALTIME_BATCH_SIZE`, `REALTIME_MAX_CONCURRENCY` pour la
  protection périodique.
- `WAF_MODE`, `WAF_BLOCKING_PARANOIA`, `WAF_DETECTION_PARANOIA`, `WAF_CORS_ALLOW_ORIGIN` pour le WAF.

En développement, `NVD_MODE=mock` et `SCAN_DETECTOR_MODE=mock` évitent les appels ou scans réels par
défaut. En production, le projet exige des secrets explicites, RS256, des clés JWT et des certificats
TLS.

### Fonctionnement métier

- Authentification : l'utilisateur se connecte avec un identifiant et un mot de passe. L'access token
  reste en mémoire dans React, le refresh token est stocké en cookie HttpOnly, et les endpoints
  sensibles utilisent un jeton CSRF.
- Plateformes : une plateforme représente une application, un site, un serveur ou une cible à suivre.
  Elle peut avoir une URL, une adresse IP ou aucune cible.
- Services et catégories : les services représentent les technologies ou composants présents sur une
  plateforme. Ils peuvent être ajoutés manuellement, importés depuis Excel ou confirmés après scan.
- Import Excel : le fichier `.xlsx` est lu en mode sécurisé, transformé en aperçu, puis confirmé
  explicitement avant création des services.
- Scans contrôlés : l'API valide la cible, crée un job, puis `scanner-worker` détecte des services.
  Aucun résultat n'entre dans l'inventaire sans confirmation utilisateur.
- Vulnérabilités : les services sont rapprochés de CPE, CVE, NVD et OSV. Les résultats actifs créent
  ou mettent à jour des liens service/vulnérabilité.
- Protection périodique : `scheduler` vérifie si une exécution est due, `protection-worker` traite les
  services par lots et Redis empêche deux exécutions globales simultanées.
- Notifications et audit : les notifications sont propres à chaque utilisateur, tandis que les
  événements d'audit sont conservés comme historique immuable.

### Lanceur Windows `MICEPP-Manager.exe`

Le lanceur est une application Windows Forms qui exécute `docker.exe` dans le dossier contenant
`docker-compose.yml`. Il évite d'avoir à taper les commandes Docker à la main.

- `Démarrer` exécute `docker compose up -d`. Il démarre les services en arrière-plan.
- `Arrêter` exécute `docker compose stop`. Il arrête les conteneurs sans supprimer les volumes.
- `Redémarrer` exécute `docker compose restart`. Il relance les conteneurs existants.
- `Reconstruire` exécute `docker compose up -d --build`. Il reconstruit les images puis relance
  l'application.
- `Ouvrir le site` ouvre <http://localhost:8081> dans le navigateur.
- `Actualiser l'état` exécute `docker compose ps --format "{{.Service}}|{{.State}}"` et affiche le
  nombre de services actifs.
- `Afficher les logs` exécute
  `docker compose logs --tail 120 api frontend protection-worker scanner-worker` et affiche les
  derniers logs utiles.

Le lanceur actualise l'état toutes les cinq secondes. Pendant une opération, il désactive les boutons
principaux pour éviter de lancer deux commandes Docker en même temps.

## Commandes utiles

```sh
make up
make down
make logs
make migrate
make bootstrap-admin
make test
make lint
```

Sans Make :

```sh
docker compose run --rm api pytest
docker compose run --rm frontend npm run test -- --run
docker compose run --rm frontend npm run build
```

## Développement local hors Docker

Backend :

```sh
cd backend
python -m venv .venv
.venv/Scripts/activate
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload
```

Frontend :

```sh
cd frontend
npm install
npm run dev
```

Le proxy Vite transmet `/api` vers `http://localhost:8000` en développement local.

## Configuration

Toutes les valeurs sont lues depuis l’environnement. `.env.example` documente les variables du
socle et réserve celles des prochains sprints. Aucun secret réel ne doit être commité.

Variables actives :

- `APP_ENV`, `APP_NAME`, `APP_VERSION`, `APP_LOG_LEVEL`
- `APP_SECRET_KEY`
- `DATABASE_URL`, `REDIS_URL`
- `ALLOWED_ORIGINS`
- `EXPECTED_DATABASE_REVISION`
- `JWT_ALGORITHM`, `JWT_PRIVATE_KEY`, `JWT_PUBLIC_KEY`
- `JWT_ACCESS_TTL_SECONDS`, `JWT_REFRESH_TTL_SECONDS`, `JWT_REMEMBER_REFRESH_TTL_SECONDS`
- `BOOTSTRAP_ADMIN_USERNAME`, `BOOTSTRAP_ADMIN_PASSWORD`, `BOOTSTRAP_ADMIN_DISPLAY_NAME`
- `LOGIN_MAX_ATTEMPTS`, `LOGIN_RATE_WINDOW_SECONDS`, `LOGIN_LOCK_SECONDS`
- `IMPORT_MAX_FILE_BYTES`, `IMPORT_MAX_UNCOMPRESSED_BYTES`, `IMPORT_MAX_ROWS`
- `IMPORT_MAX_COLUMNS`, `IMPORT_TIMEOUT_SECONDS`, `AI_PROVIDER`
- `SCAN_DETECTOR_MODE`, `ALLOWED_SCAN_NETWORKS`, `ALLOW_PRIVATE_NETWORK_SCANS`
- `MAX_SCAN_DURATION_SECONDS`, `SCAN_MAX_PORTS`, `SCAN_MAX_REDIRECTS`
- `WEB_SCAN_MAX_BODY_BYTES`, `WEB_SCAN_MAX_ASSETS`, `WEB_SCAN_MAX_ASSET_BYTES`, `NMAP_BINARY`
- `WHATWEB_ENABLED`, `WHATWEB_BINARY`, `WHATWEB_TIMEOUT_SECONDS`
- `NVD_MODE`, `NVD_API_KEY`, `NVD_CPE_URL`, `NVD_CVE_URL`, `CVE_API_URL`, `NVD_CACHE_TTL_SECONDS`
- `REALTIME_DEFAULT_INTERVAL_SECONDS`, `REALTIME_MIN_INTERVAL_SECONDS`, `REALTIME_BATCH_SIZE`
- `REALTIME_MAX_CONCURRENCY`, `REALTIME_LOCK_TTL_SECONDS`, `REALTIME_SCHEDULER_POLL_SECONDS`
- `EXPENSIVE_RATE_WINDOW_SECONDS`, `MANUAL_SERVICE_CHECK_RATE_LIMIT`, `SCAN_CREATE_RATE_LIMIT`
- `IMPORT_UPLOAD_RATE_LIMIT`, `REALTIME_RUN_RATE_LIMIT`
- `WAF_MODE`, `WAF_BLOCKING_PARANOIA`, `WAF_DETECTION_PARANOIA`
- `WAF_ANOMALY_INBOUND`, `WAF_ANOMALY_OUTBOUND`, `WAF_CORS_ALLOW_ORIGIN`
- `SERVER_NAME`, `HTTP_PORT`, `HTTPS_PORT`, `TLS_CERT_PATH`, `TLS_KEY_PATH`
- `SIEM_ENDPOINT`, `SIEM_TOKEN`
- `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `VITE_API_BASE_URL`

En production, RS256 et une paire de clés sont obligatoires, le secret de développement est refusé
et la documentation OpenAPI est désactivée.

## Authentification et administrateur initial

Le bootstrap est idempotent. Si la base ne contient aucun utilisateur, il crée le rôle
`Administrateur`, toutes les permissions initiales et le compte configuré. Le changement du mot de
passe initial est imposé.

- Si `BOOTSTRAP_ADMIN_PASSWORD` est fourni, il doit respecter la politique de robustesse.
- Sans mot de passe en développement, une valeur aléatoire est affichée une seule fois dans les logs.
- Sans mot de passe en production, le démarrage échoue.

Endpoints disponibles via le proxy :

```text
POST /api/v1/auth/login
POST /api/v1/auth/refresh
POST /api/v1/auth/logout
POST /api/v1/auth/logout-all
GET  /api/v1/auth/me
POST /api/v1/auth/change-password
```

L’access token reste uniquement en mémoire dans React. Le refresh token est opaque, haché en base et
stocké dans un cookie HttpOnly. Chaque renouvellement effectue une rotation ; la réutilisation d’un
ancien token révoque toute sa famille. Les endpoints utilisant les cookies exigent également un jeton
CSRF. Les tentatives de connexion sont limitées dans Redis par IP et par identifiant.

## Plateformes

Une plateforme peut être créée avec une URL HTTP(S), une adresse IPv4/IPv6 ou sans cible. Les cibles
sont validées et normalisées côté serveur. Une plateforme sans cible reste valide mais ne pourra pas
lancer de scan automatique dans les phases ultérieures.

```text
GET    /api/v1/platforms
POST   /api/v1/platforms
GET    /api/v1/platforms/{platform_id}
PATCH  /api/v1/platforms/{platform_id}
DELETE /api/v1/platforms/{platform_id}
```

La liste accepte `q`, `target_type`, `sort`, `page`, `page_size` et `include_archived`. `DELETE`
renseigne `archived_at` et ne supprime jamais la ligne. Les endpoints contrôlent respectivement
`platform.read`, `platform.create`, `platform.update` et `platform.archive`.

## Services et catégories

Les catégories appartiennent à une seule plateforme et leur nom est normalisé pour éviter les
doublons de casse ou d’espacement. Un même nom reste autorisé sur deux plateformes différentes.

```text
GET    /api/v1/platforms/{platform_id}/categories
POST   /api/v1/platforms/{platform_id}/categories
PATCH  /api/v1/categories/{category_id}
DELETE /api/v1/categories/{category_id}
GET    /api/v1/platforms/{platform_id}/services
POST   /api/v1/platforms/{platform_id}/services
POST   /api/v1/platforms/{platform_id}/services/bulk
GET    /api/v1/services/{service_id}
PATCH  /api/v1/services/{service_id}
DELETE /api/v1/services/{service_id}
```

L’ajout manuel accepte jusqu’à 100 lignes atomiques et rejette les doublons nom/version avant
écriture. La liste prend en charge recherche, catégorie, services non catégorisés, tri et pagination.
Les archivages conservent les lignes en base.

## Notifications et historique d’audit

Les notifications disposent d’un état de lecture et de visibilité propre à chaque utilisateur.
Masquer une notification, toutes les notifications ou l’historique d’une plateforme ne supprime
aucune donnée source. Les événements d’audit sont immuables et enregistrent les opérations
d’authentification ainsi que les changements de plateformes, catégories et services.

```text
GET  /api/v1/notifications
POST /api/v1/notifications/hide-all
POST /api/v1/notifications/{notification_id}/read
POST /api/v1/notifications/{notification_id}/hide
GET  /api/v1/platforms/{platform_id}/history
POST /api/v1/platforms/{platform_id}/history/hide
```

## Import Excel

L’assistant accepte les classeurs `.xlsx` et sépare strictement l’upload, le mapping, l’aperçu et la
confirmation. Il limite la taille compressée et décompressée, le nombre de lignes et de colonnes,
n’exécute aucune formule et supprime immédiatement le fichier temporaire. Les services et catégories
ne sont créés qu’à la confirmation atomique ; les doublons peuvent être ignorés ou fusionnés sans
écrasement silencieux.

```text
POST /api/v1/platforms/{platform_id}/service-imports
POST /api/v1/service-imports/{import_id}/preview
POST /api/v1/service-imports/{import_id}/confirm
```

## Scans contrôlés

Un scan nécessite la permission `platform.scan` et une confirmation explicite d’autorisation. Les
cibles passent par une validation SSRF/DNS qui bloque loopback, link-local, métadonnées cloud et
réseaux privés par défaut. Celery exécute les jobs dans un worker non privilégié ; le mode `mock` ne
produit aucun trafic réseau et reste la configuration par défaut. Les adaptateurs Nmap et web ne
s’activent qu’explicitement. Aucun service détecté n’entre dans l’inventaire avant correction et
confirmation par l’utilisateur.

```text
POST /api/v1/platforms/{platform_id}/scans
GET  /api/v1/scans/{scan_id}
POST /api/v1/scans/{scan_id}/cancel
POST /api/v1/scans/{scan_id}/confirm
```

## Architecture et sécurité

Le conteneur WAF OWASP CRS est l’unique service publié. Le reverse proxy applicatif, l’API,
PostgreSQL et Redis restent sur des réseaux Docker internes. Les réponses reçoivent un
`X-Request-ID`; les logs API, proxy et WAF sont structurés. Les requêtes sont limitées à 10 Mio et
les réponses publiques portent CSP, HSTS, protection anti-clickjacking et politiques de référent.

Les détails et limites sont décrits dans [docs/architecture.md](docs/architecture.md).

### Sécurité applicative détaillée

MICEPP-Tracker applique plusieurs couches de sécurité complémentaires. Le navigateur n'accède jamais
directement à PostgreSQL, Redis, l'API ou aux workers : le WAF est le seul point d'entrée publié,
puis Nginx relaie le trafic vers les services internes. Les réseaux Docker `backend` et `frontend`
limitent les communications entre conteneurs ; PostgreSQL et Redis ne publient aucun port hôte.

L'authentification repose sur un access token JWT court et un refresh token opaque. L'access token
reste uniquement en mémoire côté React. Le refresh token est stocké dans un cookie `HttpOnly`,
`SameSite=Strict`, et `Secure` en production. En base, le refresh token brut n'est jamais conservé :
seul son hash SHA-256 est stocké. À chaque renouvellement, le refresh token est remplacé ; si un
ancien refresh token est réutilisé, toute sa famille de sessions est révoquée.

Les mots de passe sont hashés avec Argon2 (`argon2-cffi`). La politique de robustesse impose au
minimum 12 caractères, une majuscule, une minuscule, un chiffre et un caractère spécial. Le compte
administrateur initial est créé uniquement si aucun utilisateur n'existe, et le changement du mot de
passe initial est imposé.

Les actions applicatives passent par un contrôle RBAC. Les permissions comme `platform.read`,
`platform.create`, `platform.scan`, `service.import`, `settings.update` ou `user.manage` sont
associées aux rôles et vérifiées côté API. Un utilisateur qui doit encore changer son mot de passe
initial ne peut pas accéder aux routes métier protégées.

Les endpoints sensibles utilisent une protection CSRF double-submit : le frontend envoie le jeton
`X-CSRF-Token`, et l'API le compare au cookie CSRF. Les tentatives de connexion, refresh token,
imports, scans, contrôles manuels et lancements de protection périodique sont limités avec Redis. Un
dépassement retourne `429` et évite de lancer un traitement coûteux.

Les scans sont protégés contre les usages dangereux. Les cibles doivent être des URL HTTP(S) ou des
adresses IP valides. Les identifiants intégrés dans les URL sont interdits. Par défaut, les adresses
loopback, link-local, multicast, réservées et privées sont bloquées. Les réseaux privés ne sont
autorisés que via `ALLOW_PRIVATE_NETWORK_SCANS=true` ou une allowlist `ALLOWED_SCAN_NETWORKS`. Le
worker revérifie aussi la résolution DNS afin de limiter les attaques de type DNS rebinding.

Nginx ajoute des en-têtes de sécurité publics : `Content-Security-Policy`,
`Strict-Transport-Security`, `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`,
`Permissions-Policy`, `Cross-Origin-Opener-Policy`, `Cross-Origin-Resource-Policy` et
`X-Request-ID`. En développement, le WAF est en `DetectionOnly`; en production, la surcharge Compose
force le mode bloquant, la redirection HTTPS et TLS 1.2/1.3.

### Journaux, audit et consultation

Il existe deux familles de traces : les logs techniques Docker et l'audit métier stocké en base.

Les logs techniques sont écrits sur `stdout`/`stderr` par les conteneurs, puis collectés par Docker.
Ils ne sont donc pas stockés dans un fichier du dépôt. On les consulte avec `docker compose logs`.
L'API produit des logs JSON avec timestamp, niveau, service, environnement, logger, message,
`request_id`, `user_id`, IP client, méthode HTTP, chemin, statut et durée. Les valeurs sensibles
comme `Authorization`, cookies, mots de passe, secrets, tokens, API keys et identifiants dans les URL
sont masquées avant écriture.

Le reverse proxy Nginx écrit aussi des logs JSON avec timestamp, service `reverse-proxy`,
`request_id`, adresse distante, méthode, chemin, statut et temps de requête. Le WAF ModSecurity écrit
ses audits JSON sur `stdout`, ce qui permet de voir les règles OWASP CRS déclenchées et les éventuels
faux positifs.

Commandes utiles :

```sh
docker compose logs -f
docker compose logs -f api
docker compose logs -f reverse-proxy
docker compose logs -f waf
docker compose logs -f api frontend scanner-worker protection-worker
docker compose logs --tail 120 api frontend protection-worker scanner-worker
```

Le bouton `Afficher les logs` du lanceur Windows exécute la dernière commande et affiche les 120
dernières lignes des services applicatifs principaux.

L'audit métier est différent des logs techniques. Il est stocké dans PostgreSQL, dans la table
`audit_events`. Il conserve les événements importants comme les connexions réussies ou échouées, les
déconnexions, changements de mot de passe, modifications de plateformes, imports, confirmations de
scan et exécutions de protection périodique. Chaque événement peut contenir l'acteur, l'IP, le
`request_id`, le type d'entité, l'identifiant d'entité, le contexte de plateforme, un résumé et des
données avant/après lorsque c'est utile.

Vector peut être activé avec le profil `siem` pour exporter les logs Docker vers un SIEM externe. Il
parse les logs JSON, retire une seconde fois les champs sensibles connus, conserve un tampon disque
dans le volume `vector-data`, puis envoie les événements en HTTPS avec un jeton Bearer.

```sh
SIEM_ENDPOINT=https://siem.example.test/ingest SIEM_TOKEN=replace-me \
docker compose --profile siem up -d log-collector
```

## NVD et suivi des vulnérabilités

La fiche d’un service permet de rechercher les CPE NVD, valider manuellement un candidat ambigu,
contrôler les CVE applicables et consulter leur score CVSS, leur justification et leurs références.
Une vulnérabilité peut être ignorée avec un motif audité ; elle reste conservée dans l’historique.

```text
POST  /api/v1/services/{service_id}/check
GET   /api/v1/services/{service_id}/cpe-candidates
POST  /api/v1/services/{service_id}/cpe-candidates/{candidate_id}/select
GET   /api/v1/services/{service_id}/vulnerabilities
GET   /api/v1/service-vulnerabilities/{link_id}
PATCH /api/v1/service-vulnerabilities/{link_id}/ignore
```

`NVD_MODE=mock` est le mode local par défaut. Pour utiliser la NVD réelle, définissez
`NVD_MODE=live` et, de préférence, `NVD_API_KEY` dans l’environnement du backend.

## Protection périodique

Celery Beat vérifie régulièrement si une exécution est due. Le service `scheduler` crée un job
idempotent, puis `protection-worker` traite les services actifs par lots avec un verrou Redis global.
Une reprise après redémarrage récupère les jobs dont le heartbeat est devenu obsolète. Les résultats,
erreurs partielles, notifications et prochaines dates d’exécution sont conservés en base.

Le lancement manuel utilise exactement le même pipeline que l’ordonnanceur :

```text
GET   /api/v1/settings/realtime-protection
PATCH /api/v1/settings/realtime-protection
POST  /api/v1/settings/realtime-protection/run-now
GET   /api/v1/settings/realtime-protection/current-job
```

Avec Docker Compose, `docker compose up --build` lance l’API, le worker de scan, le worker de
protection et Celery Beat. Hors Docker, les processus correspondants sont :

```sh
celery -A app.worker.celery_app worker --loglevel=INFO --queues=protection
celery -A app.worker.celery_app beat --loglevel=INFO
```

## Durcissement, TLS et WAF (phase 10)

En développement, `docker compose up --build` publie HTTP sur le port 8081 et HTTPS sur 8443 avec
le certificat local fourni par l’image WAF. ModSecurity fonctionne en `DetectionOnly` : les règles
OWASP CRS journalisent les détections sans bloquer. Consultez-les avec :

```sh
docker compose logs -f waf
```

Le profil de production active obligatoirement le blocage, redirige HTTP vers HTTPS, refuse TLS 1.0
et 1.1, utilise le frontend statique et désactive le rechargement automatique de l’API :

```sh
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Avant ce lancement, configurez au minimum `SERVER_NAME`, `WAF_CORS_ALLOW_ORIGIN`,
`TLS_CERT_PATH`, `TLS_KEY_PATH`, `APP_SECRET_KEY`, `POSTGRES_PASSWORD`, `ALLOWED_ORIGINS`,
`JWT_PRIVATE_KEY`, `JWT_PUBLIC_KEY` et `BOOTSTRAP_ADMIN_PASSWORD`. Les chemins TLS pointent vers
des fichiers PEM lisibles par Docker. Après un renouvellement atomique des certificats, rechargez le
point d’entrée avec `docker compose restart waf`. N’utilisez jamais le certificat autosigné local en
production.

Les éventuelles exclusions CRS se placent dans
`infra/waf/REQUEST-900-EXCLUSION-RULES-BEFORE-CRS.conf`. Elles doivent cibler une règle, une route et
un paramètre reproductibles ; ne désactivez jamais globalement le moteur, l’inspection du corps ou
une famille entière de règles. Testez d’abord en `DetectionOnly`, puis rejouez les parcours métier
avant le passage en blocage.

### Export des journaux vers un SIEM

Vector est optionnel et s’active par profil. Il lit les journaux JSON Docker, supprime une seconde
fois les champs sensibles, conserve un tampon disque et les transmet par HTTPS :

```sh
SIEM_ENDPOINT=https://siem.example.test/ingest SIEM_TOKEN=replace-me \
docker compose --profile siem up -d log-collector
```

Le SIEM lui-même n’est pas déployé par ce projet. Le socket Docker reste monté en lecture seule,
mais donne une visibilité importante sur l’hôte : limitez l’accès au conteneur Vector et faites
tourner son jeton régulièrement.

### Sauvegarde et restauration PostgreSQL

```sh
docker compose exec -T postgres pg_dump -U micepp -Fc micepp > micepp.backup
docker compose exec -T postgres pg_restore -U micepp -d micepp --clean --if-exists < micepp.backup
```

Testez la restauration dans un environnement isolé avant toute opération de production. Les volumes
Docker ne remplacent pas une sauvegarde externalisée et chiffrée.

### Contrôles de sécurité

```sh
cd backend
pytest tests/test_security_hardening.py
cd ..
powershell -File scripts/security-smoke.ps1 -BaseUrl http://localhost:8081
```

Le script vérifie les en-têtes publics et les limites de base. Les tests de blocage CRS doivent être
exécutés sur un environnement autorisé, après observation des faux positifs en mode détection.
