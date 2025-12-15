import streamlit as st
import pandas as pd
from sqlalchemy import create_engine

# --- DATABASE FUNCTIES ---

# 1. Database Connectie via Secrets
@st.cache_resource
def get_db_connection():
    # Zorg dat je secrets.toml correct is ingevuld!
    if "postgres" not in st.secrets:
        st.error("Geen [postgres] sectie gevonden in .streamlit/secrets.toml")
        return None

    db_config = st.secrets["postgres"]
    
    try:
        return create_engine(f'postgresql+psycopg2://{db_config["user"]}:{db_config["password"]}@{db_config["host"]}:{db_config["port"]}/{db_config["dbname"]}')
    except Exception as e:
        st.error(f"Fout bij maken connectie string: {e}")
        return None

# 2. Query uitvoeren
@st.cache_data(ttl=600)
def run_query(query, params=None):
    engine = get_db_connection()
    if engine is None:
        return pd.DataFrame()
        
    try:
        return pd.read_sql(query, engine, params=params)
    except Exception as e:
        st.error(f"SQL Fout: {e}")
        return pd.DataFrame()

# --- FILTER FUNCTIES ---

def show_sidebar_filters():
    st.sidebar.header("🌍 Filters")
    
    # Seizoenen ophalen
    q_seasons = 'SELECT DISTINCT "season" FROM public.iterations ORDER BY "season" DESC'
    df_seasons = run_query(q_seasons)
    
    if df_seasons.empty:
        st.sidebar.warning("Geen seizoenen gevonden.")
        return None, None

    seasons = df_seasons['season'].tolist()
    selected_season = st.sidebar.selectbox("Kies Seizoen", seasons)
    
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
        
    comp_map = dict(zip(df_comps['competitionName'], df_comps['id']))
    selected_comp_name = st.sidebar.selectbox("Kies Competitie", list(comp_map.keys()))
    selected_iteration_id = comp_map[selected_comp_name]
    
    return selected_season, selected_iteration_id

# --- LOGIN FUNCTIE (DEZE MISTE JE) ---

def check_login():
    """
    Zorgt voor een simpele wachtwoordbeveiliging.
    Zet je wachtwoord in secrets.toml onder [login] password = "..."
    of pas het hieronder hardcoded aan.
    """
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False

    if st.session_state["logged_in"]:
        # Voeg eventueel een uitlogknop toe in de sidebar
        if st.sidebar.button("Uitloggen"):
            st.session_state["logged_in"] = False
            st.rerun()
        return True

    # Als niet ingelogd, toon login formulier
    st.sidebar.header("🔒 Login")
    password_input = st.sidebar.text_input("Wachtwoord", type="password")
    
    if st.sidebar.button("Inloggen"):
        # OPTIE A: Haal wachtwoord uit secrets (Beste manier)
        # Zorg dat in secrets.toml staat:
        # [login]
        # password = "JeWachtwoord"
        
        secret_pass = st.secrets.get("login", {}).get("password")
        
        # OPTIE B: Hardcoded (voor nu even snel testen, haal dit later weg)
        # secret_pass = "admin123" 

        if secret_pass and password_input == secret_pass:
            st.session_state["logged_in"] = True
            st.rerun()
        elif not secret_pass:
            st.error("Geen wachtwoord ingesteld in secrets.toml!")
        else:
            st.error("Onjuist wachtwoord")
            
    return False
