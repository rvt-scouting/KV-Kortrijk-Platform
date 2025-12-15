import streamlit as st
import pandas as pd
from sqlalchemy import create_engine

# 1. Database Connectie
@st.cache_resource
def get_db_connection():
    # Vul hier jouw gegevens in
    db_user = 'jouw_username' 
    db_pass = 'jouw_wachtwoord'
    db_host = 'localhost' # of IP van je server
    db_port = '5432'
    db_name = 'jouw_database_naam'
    
    # Let op: als je database buiten docker draait en je app lokaal, gebruik localhost. 
    # Als beide in docker zitten, gebruik de container naam.
    return create_engine(f'postgresql+psycopg2://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}')

# 2. Query uitvoeren
@st.cache_data(ttl=600)
def run_query(query, params=None):
    engine = get_db_connection()
    try:
        return pd.read_sql(query, engine, params=params)
    except Exception as e:
        st.error(f"SQL Fout: {e}")
        return pd.DataFrame()

# 3. Sidebar Filters (Seizoen -> Competitie)
def show_sidebar_filters():
    st.sidebar.header("🌍 Filters")
    
    # A. Haal seizoenen op
    q_seasons = 'SELECT DISTINCT "season" FROM public.iterations ORDER BY "season" DESC'
    df_seasons = run_query(q_seasons)
    
    if df_seasons.empty:
        st.sidebar.warning("Geen data gevonden in public.iterations")
        return None, None

    # Selectbox Seizoen
    seasons = df_seasons['season'].tolist()
    selected_season = st.sidebar.selectbox("Kies Seizoen", seasons)
    
    # B. Haal competities op basis van seizoen
    # We halen zowel de naam als het ID op, want het ID hebben we nodig voor de koppeling
    q_comps = """
        SELECT DISTINCT "competitionName", "id" 
        FROM public.iterations 
        WHERE "season" = %s
        ORDER BY "competitionName"
    """
    df_comps = run_query(q_comps, params=(selected_season,))
    
    if df_comps.empty:
        st.sidebar.warning("Geen competities gevonden voor dit seizoen.")
        return selected_season, None
        
    # Dictionary voor vertaling Naam -> ID
    comp_map = dict(zip(df_comps['competitionName'], df_comps['id']))
    
    # Selectbox Competitie
    selected_comp_name = st.sidebar.selectbox("Kies Competitie", list(comp_map.keys()))
    
    # Het ID teruggeven voor gebruik in queries
    selected_iteration_id = comp_map[selected_comp_name]
    
    return selected_season, selected_iteration_id
