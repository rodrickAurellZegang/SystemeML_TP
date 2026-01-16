import os
import pandas as pd
from sqlalchemy import create_engine, text
from prefect import flow, task
import great_expectations as ge

@task(log_prints=True)
def validate_with_ge(table: str):
    eng = engine()
    with eng.begin() as conn:
        # On récupère les données fraîchement insérées
        df = pd.read_sql(text(f"SELECT * FROM {table}"), conn)
    
    # On transforme le DataFrame en objet Great Expectations
    gdf = ge.from_pandas(df)
    
    print(f"Lancement de la validation pour la table : {table}")
    
    if table == "users":
        # Règle 1 : L'ID utilisateur ne doit pas être nul
        gdf.expect_column_values_to_not_be_null("user_id")
        
    elif table == "usage_agg_30d":
        # Règle 2 : Vérifier que les colonnes obligatoires sont présentes
        gdf.expect_table_columns_to_match_set([
            "user_id", "watch_hours_30d", "avg_session_mins_7d", 
            "unique_devices_30d", "skips_7d", "rebuffer_events_7d"
        ])
        # Règle 3 : Pas de valeurs négatives pour le temps de visionnage
        gdf.expect_column_values_to_be_between("watch_hours_30d", min_value=0)
        gdf.expect_column_values_to_be_between("avg_session_mins_7d", min_value=0)
    
    # Exécution du test
    result = gdf.validate()
    
    if not result.get("success", False):
        raise AssertionError(f" La validation a échoué pour la table {table}")
    
    print(f" Validation réussie pour la table {table}")
    return result

# Configuration de la base PostgreSQL (via .env)
PG = {
    "user": os.getenv("POSTGRES_USER", "streamflow"),
    "pwd": os.getenv("POSTGRES_PASSWORD", "streamflow"),
    "db": os.getenv("POSTGRES_DB", "streamflow"),
    "host": os.getenv("POSTGRES_HOST", "postgres"),
    "port": os.getenv("POSTGRES_PORT", "5432"),
}

AS_OF = os.getenv("AS_OF", "2024-01-31")
SEED_DIR = os.getenv("SEED_DIR", "/data/seeds/month_000")

def engine():
    uri = f"postgresql+psycopg2://{PG['user']}:{PG['pwd']}@{PG['host']}:{PG['port']}/{PG['db']}"
    return create_engine(uri)

@task(log_prints=True)
def snapshot_month(as_of: str):
    """
    Crée (si besoin) les tables de snapshots et insère les données
    pour la date as_of donnée. Utilise une stratégie idempotente.
    """
    ddl = """
    CREATE TABLE IF NOT EXISTS subscriptions_profile_snapshots (
      user_id TEXT,
      as_of DATE,
      months_active INT,
      monthly_fee NUMERIC,
      paperless_billing BOOLEAN,
      plan_stream_tv BOOLEAN,
      plan_stream_movies BOOLEAN,
      net_service TEXT,
      PRIMARY KEY (user_id, as_of)
    );

    CREATE TABLE IF NOT EXISTS usage_agg_30d_snapshots (
      user_id TEXT,
      as_of DATE,
      watch_hours_30d NUMERIC,
      avg_session_mins_7d NUMERIC,
      unique_devices_30d INT,
      skips_7d INT,
      rebuffer_events_7d INT,
      PRIMARY KEY (user_id, as_of)
    );

    CREATE TABLE IF NOT EXISTS payments_agg_90d_snapshots (
      user_id TEXT,
      as_of DATE,
      failed_payments_90d INT,
      PRIMARY KEY (user_id, as_of)
    );

    CREATE TABLE IF NOT EXISTS support_agg_90d_snapshots (
      user_id TEXT,
      as_of DATE,
      support_tickets_90d INT,
      ticket_avg_resolution_hrs_90d NUMERIC,
      PRIMARY KEY (user_id, as_of)
    );
    """

    sqls = [
        f"""
        INSERT INTO subscriptions_profile_snapshots
        (user_id, as_of, months_active, monthly_fee, paperless_billing,
         plan_stream_tv, plan_stream_movies, net_service)
        SELECT user_id, DATE '{as_of}', months_active, monthly_fee, paperless_billing,
               plan_stream_tv, plan_stream_movies, net_service
        FROM subscriptions
        ON CONFLICT (user_id, as_of) DO NOTHING;
        """,
        f"""
        INSERT INTO usage_agg_30d_snapshots
        (user_id, as_of, watch_hours_30d, avg_session_mins_7d,
         unique_devices_30d, skips_7d, rebuffer_events_7d)
        SELECT user_id, DATE '{as_of}', watch_hours_30d, avg_session_mins_7d,
               unique_devices_30d, skips_7d, rebuffer_events_7d
        FROM usage_agg_30d
        ON CONFLICT (user_id, as_of) DO NOTHING;
        """,
        f"""
        INSERT INTO payments_agg_90d_snapshots
        (user_id, as_of, failed_payments_90d)
        SELECT user_id, DATE '{as_of}', failed_payments_90d
        FROM payments_agg_90d
        ON CONFLICT (user_id, as_of) DO NOTHING;
        """,
        f"""
        INSERT INTO support_agg_90d_snapshots
        (user_id, as_of, support_tickets_90d, ticket_avg_resolution_hrs_90d)
        SELECT user_id, DATE '{as_of}', support_tickets_90d, ticket_avg_resolution_hrs_90d
        FROM support_agg_90d
        ON CONFLICT (user_id, as_of) DO NOTHING;
        """
    ]

    with engine().begin() as conn:
        print(f"Initialisation des tables de snapshots pour {as_of}...")
        conn.exec_driver_sql(ddl)
        for sql in sqls:
            conn.exec_driver_sql(sql)

    return f"snapshots stamped for {as_of}"

@task(log_prints=True)
def upsert_csv(table: str, csv_path: str, pk_cols: list[str]):
    print(f"Processing {table} from {csv_path}")
    df = pd.read_csv(csv_path)
    print(f"Loaded {len(df)} rows")
    
    if "signup_date" in df.columns:
        df["signup_date"] = pd.to_datetime(df["signup_date"], errors="coerce")
    
    # Convertir en booléen les colonnes plan_stream_tv, plan_stream_movies, paperless_billing
    bool_cols = ['plan_stream_tv', 'plan_stream_movies', 'paperless_billing']
    for col in bool_cols:
        if col in df.columns:
            df[col] = df[col].astype(bool)

    eng = engine()
    with eng.begin() as conn:
        tmp = f"tmp_{table}"
        conn.exec_driver_sql(f"DROP TABLE IF EXISTS {tmp}")
        df.head(0).to_sql(tmp, conn, if_exists="replace", index=False)
        df.to_sql(tmp, conn, if_exists="append", index=False)
        
        cols = list(df.columns)
        collist = ", ".join(cols)
        pk = ", ".join(pk_cols)
        
        # Construire la partie "SET col = EXCLUDED.col" pour toutes les colonnes non PK
        updates = ", ".join([f"{c} = EXCLUDED.{c}" for c in cols if c not in pk_cols])
        
        sql = text(f"""
            INSERT INTO {table} ({collist})
            SELECT {collist} FROM {tmp}
            ON CONFLICT ({pk}) DO UPDATE SET {updates}
        """)
        conn.execute(sql)
        conn.exec_driver_sql(f"DROP TABLE IF EXISTS {tmp}")
    print(f"✓ Upserted {len(df)} rows into {table}")
    return f"upserted {len(df)} rows into {table}"

@flow(name="ingest_month", log_prints=True)
def ingest_month_flow(seed_dir: str = SEED_DIR, as_of: str = AS_OF):
    print(f"Starting ingestion for {as_of} from {seed_dir}")
    
    # 1. Ingestion (Tes étapes actuelles)
    upsert_csv("users", f"{seed_dir}/users.csv", ["user_id"])
    upsert_csv("subscriptions", f"{seed_dir}/subscriptions.csv", ["user_id"])
    upsert_csv("usage_agg_30d", f"{seed_dir}/usage_agg_30d.csv", ["user_id"])
    upsert_csv("payments_agg_90d", f"{seed_dir}/payments_agg_90d.csv", ["user_id"])
    upsert_csv("support_agg_90d", f"{seed_dir}/support_agg_90d.csv", ["user_id"])
    upsert_csv("labels", f"{seed_dir}/labels.csv", ["user_id"])
    
    # 2. Validation de la qualité (Nouvelles étapes de l'exercice 4)
    # On valide la table users et la table usage_agg_30d
    validate_with_ge("users")
    validate_with_ge("usage_agg_30d")
    # Appel de la tâche de snapshot
    
    snapshot_month(as_of)
    
    print(f"Pipeline completed with snapshots for {as_of}")
    return f"Ingestion + validation + snapshots terminés pour {as_of}"

if __name__ == "__main__":
    ingest_month_flow()