from feast import FeatureStore


def main() -> None:
    # Connexion au store (le repo est monté dans /repo dans le conteneur)
    store = FeatureStore(repo_path="/repo")

    # On choisit un user_id présent dans tes données de janvier ( seeds month_000)
    # Par exemple '0002-ORFBO' ou un autre ID que tu as vu dans ton training_df.csv
    user_id = "0002-ORFBO"

    features = [
        "subs_profile_fv:months_active",
        "subs_profile_fv:monthly_fee",
        "subs_profile_fv:paperless_billing",
        "usage_agg_30d_fv:watch_hours_30d",
    ]

    feature_dict = store.get_online_features(
        features=features,
        entity_rows=[{"user_id": user_id}],
    ).to_dict()

    print(f"--- Online features for user: {user_id} ---")
    print(feature_dict)


if __name__ == "__main__":
    main()