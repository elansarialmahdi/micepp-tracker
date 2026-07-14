# WAF OWASP CRS

Le service `waf` est l’unique entrée publique. Il utilise l’image officielle OWASP ModSecurity CRS
et transmet le trafic accepté au reverse proxy interne.

- Développement : `MODSEC_RULE_ENGINE=DetectionOnly` par défaut.
- Production : `docker-compose.prod.yml` force `MODSEC_RULE_ENGINE=On`.
- Les audits ModSecurity sont émis en JSON sur stdout : `docker compose logs -f waf`.
- TLS de production accepte uniquement TLS 1.2 et 1.3 et utilise les PEM montés par
  `TLS_CERT_PATH` et `TLS_KEY_PATH`.

## Traitement d’un faux positif

1. Reproduire la requête en environnement de test et relever l’identifiant de règle dans l’audit.
2. Vérifier que la donnée est légitime et que sa validation applicative est suffisante.
3. Ajouter une exclusion étroite dans `REQUEST-900-EXCLUSION-RULES-BEFORE-CRS.conf`, limitée à
   l’identifiant de règle, la route et le paramètre concernés.
4. Rejouer les tests fonctionnels et de sécurité en `DetectionOnly`.
5. Faire relire la modification avant son activation en mode bloquant.

Il est interdit de désactiver globalement ModSecurity, l’inspection des corps ou une catégorie CRS.

