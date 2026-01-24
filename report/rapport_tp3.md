# Rapport TP3 - Introduction à Feast et au Feature Store

## Contexte
Le système StreamFlow dispose actuellement d'un socle de données structurées stockées dans PostgreSQL, issues des étapes d'ingestion et de validation précédentes. Ces données sont organisées sous forme de snapshots mensuels couvrant deux périodes (janvier et février 2024), incluant les informations sur les utilisateurs, leur consommation (usage), leurs abonnements, l'historique des paiements et les interactions avec le support.

L'objectif de ce TP3 est de connecter cet historique au Feature Store Feast afin de centraliser la définition des caractéristiques du projet. Nous allons mettre en œuvre la récupération de features en mode "offline" pour la construction de datasets d'entraînement cohérents et en mode "online" pour l'inférence en temps réel. Enfin, nous exposerons ces données via un endpoint FastAPI minimal afin de simuler une mise en production et de garantir l'absence de training-serving skew.

## Mise en place de Feast

Le service Feast a été intégré à l'architecture via un nouveau conteneur Docker basé sur Python 3.11. Ce service est configuré pour interagir avec l'instance PostgreSQL existante, qui fait office à la fois d'Offline Store pour la récupération historique et d'Online Store pour le service basse latence. La configuration est centralisée dans le fichier `feature_store.yaml` présent dans le répertoire `/repo` du conteneur.

### Validation du service
Le service a été démarré avec succès. La commande `docker compose ps` confirme que le conteneur `feast_service` est en état "Up". 

![alt text](<captures/3-1.png>)


## Définition du Feature Store

La configuration du Feature Store repose sur une approche déclarative permettant de centraliser la définition des caractéristiques métier de StreamFlow. Cette étape permet de s'assurer que les définitions sont identiques entre la phase d'entraînement et la production.

### Entity
Nous avons défini l'entité principale `user` qui sert de pivot pour toutes nos données. La clé de jointure utilisée est `user_id`, car elle permet d'identifier de manière stable un utilisateur à travers toutes les tables de snapshots PostgreSQL.

### Data Sources
Quatre sources de données PostgreSQL ont été configurées, pointant directement vers les tables de snapshots mensuels produites lors du TP2. Pour chaque source, une requête SQL explicite sélectionne le `user_id`, le champ temporel `as_of` (utilisé comme `timestamp_field`) et les caractéristiques métier. Ces sources incluent :
* `subs_profile_source` : Informations sur l'abonnement.
* `usage_agg_30d_source` : Données comportementales de visionnage.
* `payments_agg_90d_source` : Historique des incidents de paiement.
* `support_agg_90d_source` : Statistiques sur les tickets de support.

### Feature Views
Les Feature Views regroupent les caractéristiques par domaine logique. Chaque vue définit un schéma strict avec des types de données précis (Int64, Float32, Bool, String) et est liée à l'entité `user`. Nous avons activé le paramètre `online=True` pour permettre la matérialisation future vers le Online Store. Les quatre vues créées sont :
1. `subs_profile_fv` : Profil contractuel (ex: `months_active`, `monthly_fee`).
2. `usage_agg_30d_fv` : Usage de la plateforme (ex: `watch_hours_30d`, `skips_7d`).
3. `payments_agg_90d_fv` : Risques financiers (ex: `failed_payments_90d`).
4. `support_agg_90d_fv` : Qualité de l'expérience utilisateur (ex: `support_tickets_90d`).

### Synchronisation du registre
La synchronisation a été effectuée avec succès via la commande :
```bash
docker compose exec feast feast apply
```

![alt text](<captures/3-2.png>)




## Récupération offline & online

### Récupération offline et création du jeu d'entraînement
L'objectif de cette étape était de reconstruire un dataset historique cohérent pour l'entraînement du futur modèle. Nous avons utilisé le service Prefect pour exécuter le script `build_training_dataset.py` :

```bash
docker compose exec prefect python build_training_dataset.py

```

![alt text](<captures/3-3.png>)

### Matérialisation et récupération online
La matérialisation est l'étape qui transfère les données du stockage historique vers un stockage optimisé pour la lecture rapide (Online Store). Nous avons matérialisé les données du mois de janvier 2024 avec la commande :

```bash
docker compose exec feast feast materialize 2024-01-01T00:00:00 2024-02-01T00:00:00
```

**Test de récupération online :**
L'interrogation du Online Store pour l'utilisateur `0002-ORFBO` via `get_online_features` a renvoyé les résultats suivants :

```json
{
  "user_id": ["0002-ORFBO"],
  "paperless_billing": [true],
  "monthly_fee": [65.5999984741211],
  "months_active": [9],
  "watch_hours_30d": [30.80069923400879]
}
```

![alt text](<captures/3-5.png>)


### Intégration de Feast dans l'API FastAPI
Nous avons développé un service FastAPI qui initialise un objet `FeatureStore` global pointant vers le volume partagé `/repo`. L'endpoint `/features/{user_id}` permet d'interroger le Online Store en temps réel afin de récupérer les caractéristiques les plus récentes de l'utilisateur.

**Résultat de l'appel API :**
```json
{
  "user_id": "7590-VHVEG",
  "features": {
    "user_id": "7590-VHVEG",
    "months_active": 1,
    "monthly_fee": 29.850000381469727,
    "paperless_billing": true
  }
}
```
![alt text](<captures/3-6.png>)


## Réflexion
L'utilisation de cet endpoint basé sur Feast aide à réduire le **training-serving skew** de plusieurs manières :

* **Source de vérité unique** : La logique de calcul et les schémas sont définis une seule fois dans le registre Feast et partagés entre l'entraînement et l'inférence.
* **Cohérence des données** : Le modèle en production consomme des données matérialisées issues de la même source historique que celle utilisée pour le dataset d'entraînement.
* **Élimination de la ré-implémentation** : L'API ne contient aucune logique de feature engineering ; elle se contente de servir des valeurs prêtes à l'emploi, évitant les erreurs de codage manuelles lors du passage en production.