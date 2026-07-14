# Export SIEM avec Vector

Le profil Compose `siem` collecte les journaux des conteneurs, analyse les événements JSON, retire
les champs sensibles connus et les envoie à un endpoint HTTP(S). Un tampon disque absorbe les
indisponibilités temporaires et les acquittements donnent une livraison au moins une fois.

```sh
SIEM_ENDPOINT=https://siem.example.test/ingest SIEM_TOKEN=replace-me \
docker compose --profile siem up -d log-collector
```

L’endpoint doit accepter des objets JSON séparés par des retours à la ligne et un jeton Bearer.
Surveillez `docker compose logs log-collector`, la capacité du volume `vector-data` et les doublons
possibles côté SIEM. Le projet ne déploie ni le SIEM ni sa politique de rétention.

Le socket Docker, même en lecture seule, expose des métadonnées sensibles sur l’hôte. Restreignez
l’administration du collecteur, n’y ajoutez aucun outil inutile et faites tourner `SIEM_TOKEN`.

