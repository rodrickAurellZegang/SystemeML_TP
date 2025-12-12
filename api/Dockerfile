# Dockerfile
# Image Docker pour l'API FastAPI
# TP1 - CSC 8613 Systèmes pour le Machine Learning

# Image de base : Python 3.11 version légère
FROM python:3.11-slim

# Définition du répertoire de travail dans le conteneur
WORKDIR /app

# Copie du code source de l'API dans le conteneur
COPY app.py .

# Installation des dépendances Python nécessaires
# - fastapi: framework web moderne et rapide
# - uvicorn: serveur ASGI pour exécuter l'application
RUN pip install --no-cache-dir fastapi uvicorn

# Commande de démarrage du serveur Uvicorn
# --host 0.0.0.0 : écoute sur toutes les interfaces réseau
# --port 8000 : port d'écoute de l'API
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]