import streamlit as st
import pandas as pd
from sqlalchemy import create_engine

# -----------------------------------------------------------------------------
# 1. DATABASE CONNECTIE (Via Secrets)
# -----------------------------------------------------------------------------
@st.cache_resource
def get_db_connection():
    if "postgres" not in st.secrets:
        st.error("Geen [postgres] sectie in .streamlit/secrets.toml")
        return None

    conf = st.secrets["postgres"]
    try:
        # Let op: f-string veiligheid is hier prima voor interne config
        url = f"postgresql+psycopg2://{conf['user']}:{conf['password']}@{conf['host']}:{conf['port']}/{conf['dbname']}"
        return create_engine(url)
    except Exception as e:
        st.error(f"DB Connectie Error: {e}")
        return None

@st.cache_data(ttl=600)
def run_query(query, params=None):
    engine = get_db_connection()
    if not engine: return pd.DataFrame()
    try:
        return pd.read_sql(query, engine, params=params)
    except Exception as e:
        st.error(f"SQL Error: {e}")
        return pd.DataFrame()

# -----------------------------------------------------------------------------
# 2. LOGIN FUNCTIE (Speciaal voor jouw Home.py)
# -----------------------------------------------------------------------------
def check_login(email, password):
    """
    Wordt aangeroepen door Home.py als: check_login(email, pwd)
    Moet een DICTIONARY teruggeven als succesvol, anders None.
    """
    # Haal het master wachtwoord uit secrets
    try:
        correct_pass = st.secrets["login"]["password"]
    except KeyError:
        st.error("Voeg [login] password = '...' toe aan secrets.toml")
        return None

    if password == correct_pass:
        # HIERONDER: Simuleer de user info die jouw Home.py nodig heeft.
        # Later kun je dit vervangen door een query naar je 'users' tabel.
        
        # Voorbeeld: Als email 'scout@kvk.be' is, geef niveau 1, anders niveau 3
        niveau = 1 if "scout" in email else 3
        
        return {
            "naam": email.split('@')[0], # Pakt het stukje voor de @ als naam
            "email": email,
            "toegangsniveau": niveau 
        }
    
    return None

# -----------------------------------------------------------------------------
# 3. FILTERS VOOR DE PAGINA'S
# -----------------------------------------------------------------------------
def show_sidebar_filters():
    st.sidebar.header("🌍 Filters")
    
    # Haal seizoenen op
    df_seasons = run_query('SELECT DISTINCT "season" FROM public.iterations ORDER BY "season" DESC')
    if df_seasons.empty: return None, None

    selected_season = st.sidebar.selectbox("Seizoen", df_seasons['season'].tolist())
    
    # Haal competities op
    q_comps = 'SELECT DISTINCT "competitionName", "id" FROM public.iterations WHERE "season" = %s'
    df_comps = run_query(q_comps, params=(selected_season,))
    
    if df_comps.empty: return selected_season, None
        
    comp_map = dict(zip(df_comps['competitionName'], df_comps['id']))
    selected_comp = st.sidebar.selectbox("Competitie", list(comp_map.keys()))
    
    return selected_season, comp_map[selected_comp]
