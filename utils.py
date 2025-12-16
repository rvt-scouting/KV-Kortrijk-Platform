
import streamlit as st
import psycopg2
import pandas as pd

# -----------------------------------------------------------------------------
# 1. DATABASE CONNECTIE & QUERY FUNCTIE
# -----------------------------------------------------------------------------
def init_connection():
    return psycopg2.connect(
        host=st.secrets["postgres"]["host"],
        port=st.secrets["postgres"]["port"],
        database=st.secrets["postgres"]["dbname"],
        user=st.secrets["postgres"]["user"],
        password=st.secrets["postgres"]["password"]
    )

@st.cache_data(ttl=3600)
def run_query(query, params=None):
    conn = init_connection()
    try:
        return pd.read_sql(query, conn, params=params)
    except Exception as e:
        st.error(f"SQL Error: {e}")
        return pd.DataFrame()
    finally:
        conn.close()

# -----------------------------------------------------------------------------
# 2. ALGEMENE SIDEBAR
# -----------------------------------------------------------------------------
def show_sidebar_filters():
    """
    Deze functie toont de dropdowns voor Seizoen en Competitie in de sidebar
    en geeft het geselecteerde Seizoen en Iteration ID terug.
    """
    st.sidebar.header("1. Selecteer Data")
    
    # 1. Seizoen ophalen
    season_query = "SELECT DISTINCT season FROM public.iterations ORDER BY season DESC;"
    try:
        df_seasons = run_query(season_query)
        if df_seasons.empty:
            st.error("Geen seizoenen gevonden in DB.")
            return None, None
            
        seasons_list = df_seasons['season'].tolist()
        
        # Zorg dat er een standaardwaarde is in de sessie status
        if "sb_season" not in st.session_state:
            st.session_state.sb_season = seasons_list[0]
            
        selected_season = st.sidebar.selectbox("Seizoen:", seasons_list, key="sb_season")
    except Exception as e:
        st.error("Kon seizoenen niet laden.")
        return None, None

    # 2. Competitie ophalen
    selected_competition = None
    if selected_season:
        comp_query = 'SELECT DISTINCT "competitionName" FROM public.iterations WHERE season = %s ORDER BY "competitionName";'
        df_comps = run_query(comp_query, params=(selected_season,))
        comps_list = df_comps['competitionName'].tolist()
        
        if "sb_competition" not in st.session_state and comps_list:
             st.session_state.sb_competition = comps_list[0]
             
        selected_competition = st.sidebar.selectbox("Competitie:", comps_list, key="sb_competition")

    # 3. Iteration ID ophalen (nodig voor alle queries)
    iteration_id = None
    if selected_season and selected_competition:
        id_query = 'SELECT id FROM public.iterations WHERE season = %s AND "competitionName" = %s LIMIT 1;'
        df_id = run_query(id_query, params=(selected_season, selected_competition))
        if not df_id.empty:
            iteration_id = str(df_id.iloc[0]['id'])
        else:
            st.warning("Geen ID gevonden voor deze combinatie.")
            
    return selected_season, iteration_id

# -----------------------------------------------------------------------------
# 3. CONFIGURATIES & MAPPINGS
# -----------------------------------------------------------------------------
POSITION_METRICS = {
    "central_defender": {"aan_bal": [66, 58, 64, 10, 163], "zonder_bal": [103, 93, 32, 94, 17, 65, 92]},
    "wingback": {"aan_bal": [61, 66, 58, 54, 53, 52, 10, 9, 14], "zonder_bal": [68, 69, 17, 70]},
    "defensive_midfield": {"aan_bal": [60, 10, 163, 44], "zonder_bal": [29, 65, 17, 16, 69, 68, 67]},
    "central_midfield": {"aan_bal": [60, 61, 62, 73, 72, 64, 10, 163, 145], "zonder_bal": [65, 17, 69, 68]},
    "attacking_midfield": {"aan_bal": [60, 61, 62, 73, 58, 2, 15, 52, 72, 10, 74, 9], "zonder_bal": []},
    "winger": {"aan_bal": [60, 61, 62, 58, 54, 1, 53, 10, 9, 14, 6, 145], "zonder_bal": []},
    "center_forward": {"aan_bal": [60, 61, 62, 73, 63, 2, 64, 10, 74, 9, 92, 97, 14, 6, 145], "zonder_bal": []}
}

POSITION_KPIS = {
    "central_defender": {"aan_bal": [107, 106, 1534, 21, 2, 0, 1405, 1422], "zonder_bal": [1016, 1015, 1014, 24, 867, 1409]},
    "wingback": {"aan_bal": [172, 171, 2, 9, 0], "zonder_bal": [23, 27, 1409, 1536, 1523]},
    "defensive_midfield": {"aan_bal": [184, 0, 107, 87, 106, 109, 122, 1422, 1423], "zonder_bal": [21, 23, 27, 865, 867, 619, 1536, 1610]},
    "central_midfield": {"aan_bal": [0, 1405, 1425], "zonder_bal": [23, 27, 24, 1536]},
    "attacking_midfield": {"aan_bal": [77, 1350, 2, 169, 167, 467, 0, 7, 141, 1425, 1422, 1423, 1253, 1252, 1254], "zonder_bal": [1536]},
    "winger": {"aan_bal": [25, 2, 88, 172, 171, 167, 9, 87, 7, 1401, 1425], "zonder_bal": [1536]},
    "center_forward": {"aan_bal": [9, 427, 426, 1401, 82], "zonder_bal": [1536]}
}

def get_config_for_position(db_position, config_dict):
    if not db_position: return None
    pos = str(db_position).upper().strip()
    if pos == "CENTRAL_DEFENDER": return config_dict.get('central_defender')
    elif pos in ["RIGHT_WINGBACK_DEFENDER", "LEFT_WINGBACK_DEFENDER"]: return config_dict.get('wingback')
    elif pos in ["DEFENSIVE_MIDFIELD", "DEFENSE_MIDFIELD"]: return config_dict.get('defensive_midfield')
    elif pos == "CENTRAL_MIDFIELD": return config_dict.get('central_midfield')
    elif pos in ["ATTACKING_MIDFIELD", "OFFENSIVE_MIDFIELD"]: return config_dict.get('attacking_midfield')
    elif pos in ["RIGHT_WINGER", "LEFT_WINGER"]: return config_dict.get('winger')
    elif pos in ["CENTER_FORWARD", "STRIKER"]: return config_dict.get('center_forward')
    return None

# -----------------------------------------------------------------------------
# 4. LOGIN FUNCTIE
# -----------------------------------------------------------------------------
def check_login(email, password):
    """
    Checkt of gebruiker bestaat in scouting.gebruikers en haalt info op.
    """
    # Dit moet matchen met je Admin pagina tabel:
    query = """
        SELECT id, naam, rol, toegangsniveau 
        FROM scouting.gebruikers 
        WHERE email = %s AND wachtwoord = %s AND actief = TRUE
    """
    df = run_query(query, params=(email, password))
    
    if not df.empty:
        # Geeft een dictionary terug, bv: {'id': 1, 'naam': 'Jan', 'rol': 'Scout', 'toegangsniveau': 1}
        return df.iloc[0].to_dict()
    else:
        return None
