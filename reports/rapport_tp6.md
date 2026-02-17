# Rapport TP6

## EXERCICE1

Avant de commencer ce TP, redemarons la stack et vérifier que les services principaux sont Up.


![alt text](<Capture d’écran 2026-02-17 à 16.38.14.png>)

Nous vérfions aussi que nous avons bien un modèle en production en nous rendant sur MlFlow (http://localhost:5001)



![alt text](<Capture d’écran 2026-02-17 à 16.39.35.png>)

## Exercice 2

![alt text](<Capture d’écran 2026-02-17 à 21.58.57.png>)

Le nouveau modèle est ensuite évalué, mais il n’est pas promu car il a de moins bonnes performances AUC que le modèle en production (should_promote(new_auc=0.6328, prod_auc=0.9035, delta=0.01) → faux). Cela montre que même en présence de drift, le modèle actuel reste plus performant.

## Exercice 3 - Train & Compare

### Logs du flow
```
[COMPARE] candidate_auc=0.6328 vs prod_auc=0.9035 (delta=0.0100)
[SUMMARY] as_of=2024-02-29 cand_v=6 cand_auc=0.6328 prod_v=3 prod_auc=0.9035 -> skipped
```

### Capture MLflow
![alt text](<Capture d’écran 2026-02-17 à 22.27.23.png>)

### Pourquoi utiliser un delta
Le delta impose une marge minimale d’amélioration avant promotion, pour éviter de promouvoir un modèle sur une variation due au bruit ou à l’aléa d’entraînement.

## Exercice 4
Exécutez le monitoring (référence month_000 vs current month_001) avec un seuil à 0.02. docker compose exec prefect python monitor_flow.py

on voit dans les logs que drift_share=0.06 >= 0.02 donc ça déclenche un réentrainement.
Le nouveau modèle est ensuite évalué, mais il n’est pas promu car il a de moins bonnes performances AUC que le modèle en production (ex. should_promote(new175, prod_auc=0.9736, delta=0.01) → faux). Cela montre que même en présence de drift, le modèle actuel reste plus performant.
![alt text](<Capture d’écran 2026-02-17 à 22.39.11.png>)

Une capture (ou extrait) du rapport Evidently HTML (fichier reports/evidently/drift_*.html)

![alt text](<Capture d’écran 2026-02-17 à 22.46.06.png>)