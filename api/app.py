from fastapi import FastAPI
from feast import FeatureStore
import os

app = FastAPI()

# Initialisation globale du Feature Store
# Le repo est monté dans /repo via docker-compose
store = FeatureStore(repo_path="/repo")

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/features/{user_id}")
def get_features(user_id: str):
    features_list = [
        "subs_profile_fv:months_active",
        "subs_profile_fv:monthly_fee",
        "subs_profile_fv:paperless_billing"
    ]
    
    feature_dict = store.get_online_features(
        features=features_list,
        entity_rows=[{"user_id": user_id}],
    ).to_dict()
    
    # Conversion pour avoir un JSON propre (scalaires au lieu de listes)
    simple_features = {name: values[0] for name, values in feature_dict.items()}
    
    return {
        "user_id": user_id,
        "features": simple_features
    }