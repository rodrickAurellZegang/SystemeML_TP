import os
import time
import warnings
warnings.filterwarnings("ignore")
import pandas as pd
import numpy as np
from sqlalchemy import create_engine
from feast import FeatureStore
from sklearn.model_selection import train_test_split
from sklearn.metrics import f1_score, roc_auc_score, accuracy_score
from sklearn.ensemble import RandomForestClassifier
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder
from sklearn.pipeline import Pipeline
import mlflow
import mlflow.sklearn
from mlflow.models import ModelSignature
from mlflow.types.schema import Schema, ColSpec

# Config
FEAST_REPO = "/repo"
MODEL_NAME = "streamflow_churn"
AS_OF = os.environ.get("TRAIN_AS_OF", "2024-01-31")
MLFLOW_TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", "http://mlflow:5000")
MLFLOW_EXPERIMENT = os.environ.get("MLFLOW_EXPERIMENT", "streamflow")

def get_sql_engine():
    uri = f"postgresql+psycopg2://{os.environ.get('POSTGRES_USER', 'streamflow')}:{os.environ.get('POSTGRES_PASSWORD', 'streamflow')}@{os.environ.get('POSTGRES_HOST', 'postgres')}:5432/{os.environ.get('POSTGRES_DB', 'streamflow')}"
    return create_engine(uri)

def fetch_entity_df(engine, as_of):
    q = "SELECT user_id, as_of FROM subscriptions_profile_snapshots WHERE as_of = %(as_of)s"
    df = pd.read_sql(q, engine, params={"as_of": as_of})
    if df.empty:
        raise RuntimeError(f"No snapshot rows found at as_of={as_of}")
    df = df.rename(columns={"as_of": "event_timestamp"})
    df["event_timestamp"] = pd.to_datetime(df["event_timestamp"])
    return df[["user_id", "event_timestamp"]]

def fetch_labels(engine, as_of):
    q = "SELECT user_id, churn_label FROM labels"
    labels = pd.read_sql(q, engine)
    if labels.empty:
        raise RuntimeError("Labels table is empty.")
    labels["event_timestamp"] = pd.to_datetime(as_of)
    return labels[["user_id", "event_timestamp", "churn_label"]]

def prep_xy(df, label_col="churn_label"):
    y = df[label_col].astype(int).values
    X = df.drop(columns=[label_col, "user_id", "event_timestamp"], errors="ignore")
    return X, y

def main():
    # TODO 1: Configurer MLflow
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment(MLFLOW_EXPERIMENT)

    engine = get_sql_engine()
    entity_df = fetch_entity_df(engine, AS_OF)
    labels_df = fetch_labels(engine, AS_OF)

    # TODO 2: Liste des features Feast
    features = [
        "subs_profile_fv:months_active",
        "subs_profile_fv:monthly_fee",
        "subs_profile_fv:paperless_billing",
        "subs_profile_fv:plan_stream_tv",
        "subs_profile_fv:plan_stream_movies",
        "subs_profile_fv:net_service",
        "usage_agg_30d_fv:watch_hours_30d",
        "usage_agg_30d_fv:avg_session_mins_7d",
        "usage_agg_30d_fv:unique_devices_30d",
        "usage_agg_30d_fv:skips_7d",
        "usage_agg_30d_fv:rebuffer_events_7d",
        "payments_agg_90d_fv:failed_payments_90d",
        "support_agg_90d_fv:support_tickets_90d",
        "support_agg_90d_fv:ticket_avg_resolution_hrs_90d"
    ]

    store = FeatureStore(repo_path=FEAST_REPO)
    feat_df = store.get_historical_features(entity_df=entity_df, features=features).to_df()

    # TODO 3: Fusion features + labels
    df = feat_df.merge(labels_df, on=["user_id", "event_timestamp"], how="inner")
    
    if df.empty:
        raise RuntimeError("Training set is empty after merge.")

    cat_cols = [c for c in df.columns if df[c].dtype == "object" and c not in ["user_id", "event_timestamp"]]
    num_cols = [c for c in df.columns if c not in cat_cols + ["user_id", "event_timestamp", "churn_label"]]
    X, y = prep_xy(df)

    # TODO 4 & 5: Preprocessing et Modèle
    preproc = ColumnTransformer(transformers=[
        ("cat", OneHotEncoder(handle_unknown="ignore"), cat_cols),
        ("num", "passthrough", num_cols)
    ])

    clf = RandomForestClassifier(n_estimators=300, n_jobs=-1, random_state=42, class_weight="balanced")

    # TODO 6: Pipeline
    pipe = Pipeline(steps=[("prep", preproc), ("clf", clf)])

    X_train, X_val, y_train, y_val = train_test_split(X, y, test_size=0.25, random_state=42, stratify=y)

    # TODO 7: Run MLflow
    with mlflow.start_run(run_name=f"rf_baseline_{AS_OF}") as run:
        start_time = time.time()
        pipe.fit(X_train, y_train)
        duration = time.time() - start_time

        y_val_proba = pipe.predict_proba(X_val)[:, 1]
        y_val_pred = pipe.predict(X_val)

        auc = roc_auc_score(y_val, y_val_proba)
        f1 = f1_score(y_val, y_val_pred)
        acc = accuracy_score(y_val, y_val_pred)

        # Log params & metrics
        mlflow.log_param("as_of", AS_OF)
        mlflow.log_metric("auc", auc)
        mlflow.log_metric("f1", f1)
        mlflow.log_metric("accuracy", acc)
        mlflow.log_metric("train_time", duration)

        # Log feature schema
        mlflow.log_dict({"categorical_cols": cat_cols, "numeric_cols": num_cols}, "feature_schema.json")

        # Signature et Registry
        signature = mlflow.models.infer_signature(X_val, y_val_pred)
        mlflow.sklearn.log_model(
            sk_model=pipe,
            artifact_path="model",
            registered_model_name=MODEL_NAME,
            signature=signature
        )

        print(f"[OK] Trained baseline RF. AUC={auc:.4f} F1={f1:.4f} ACC={acc:.4f} (run_id={run.info.run_id})")

if __name__ == "__main__":
    main()