# app.py
# Mini-API FastAPI pour démonstration de conteneurisation avec Docker
# TP1 - CSC 8613 Systèmes pour le Machine Learning

from fastapi import FastAPI

# Initialisation de l'application FastAPI avec métadonnées
app = FastAPI(
    title="Simple API Demo",
    description="API de démonstration pour le TP1 sur Docker et Docker Compose",
    version="1.0.0"
)

@app.get("/health")
def health():
    """
    Endpoint de vérification de l'état de santé de l'API.
    
    Returns:
        dict: Statut de l'API ("ok" si fonctionnelle)
    """
    return {"status": "ok"}