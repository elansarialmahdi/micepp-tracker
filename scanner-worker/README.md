# Scanner worker

Le worker de phase 7 utilise l’image backend et exécute `app.worker.celery_app` avec un utilisateur
non privilégié. Le mode par défaut est `mock` : aucun trafic de scan réel n’est émis. Les modes
`nmap`, `web` et `combined` doivent être activés explicitement avec une allowlist adaptée.
