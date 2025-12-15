import streamlit as st
import pandas as pd
from sqlalchemy import create_engine

# 1. Database Connectie via Secrets
@st.cache_resource
def get_db_connection():
    # We halen de config op uit de secrets file
    # Zorg dat je sectie in secrets.toml [postgres] heet
    db_config = st.secrets["postgres"]
    
    db_user = db_config["user"]
    db_pass = db_config["password"]
    db_host = db_config["host"]
    db_port = db_config["port"]
    db_name = db_config["dbname"]
    
    return create_engine(f'postgresql+psycopg2://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}')

# 2. Query functie (ongewijzigd, maar gebruikt nu de nieuwe connectie)
@st.cache_data(ttl=600)
def run_query(query, params=None):
    engine = get_db_connection()
    try:
        return pd.read_sql(query, engine, params=params)
    except Exception as e:
        st.error(f"SQL Fout: {e}")
        return pd.DataFrame()

# 3. Sidebar Filters (ongewijzigd)
def show_sidebar_filters():
    st.sidebar.header("🌍 Filters")
    
    # Seizoenen ophalen
    q_seasons = 'SELECT DISTINCT "season" FROM public.iterations ORDER BY "season" DESC'
    df_seasons = run_query(q_seasons)
    
    if df_seasons.empty:
        st.sidebar.warning("Geen seizoenen gevonden.")
        return None, None

    # Seizoen kiezen
    seasons = df_seasons['season'].tolist()
    selected_season = st.sidebar.selectbox("Kies Seizoen", seasons)
    
    # Competitie ophalen bij seizoen
    q_comps = """
        SELECT DISTINCT "competitionName", "id" 
        FROM public.iterations 
        WHERE "season" = %s
        ORDER BY "competitionName"
    """
    df_comps = run_query(q_comps, params=(selected_season,))
    
    if df_comps.empty:
        st.sidebar.warning("Geen competities gevonden.")
        return selected_season, None
        
    # Mapping voor dropdown (Naam -> ID)
    comp_map = dict(zip(df_comps['competitionName'], df_comps['id']))
    selected_comp_name = st.sidebar.selectbox("Kies Competitie", list(comp_map.keys()))
    
    # ID teruggeven
    selected_iteration_id = comp_map[selected_comp_name]
    
    return selected_season, selected_iteration_id
