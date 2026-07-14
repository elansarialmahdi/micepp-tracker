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

4. Ouvrir <http://localhost:8080>.

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

En développement, `docker compose up --build` publie HTTP sur le port 8080 et HTTPS sur 8443 avec
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
powershell -File scripts/security-smoke.ps1 -BaseUrl http://localhost:8080
```

Le script vérifie les en-têtes publics et les limites de base. Les tests de blocage CRS doivent être
exécutés sur un environnement autorisé, après observation des faux positifs en mode détection.
