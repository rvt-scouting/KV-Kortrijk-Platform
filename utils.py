import streamlit as st
import psycopg2
import pandas as pd

# 1. DATABASE CONNECTIE
def init_connection():
    return psycopg2.connect(
        host=st.secrets["postgres"]["host"],
        port=st.secrets["postgres"]["port"],
        database=st.secrets["postgres"]["dbname"],
        user=st.secrets["postgres"]["user"],
        password=st.secrets["postgres"]["password"]
    )

def run_query(query, params=None):
    conn = init_connection()
    try:
        return pd.read_sql(query, conn, params=params)
    except Exception as e:
        st.error(f"SQL Error: {e}")
        return pd.DataFrame()
    finally:
        conn.close()

# 2. SIDEBAR FILTERS (Met KVK Defaults)
def show_sidebar_filters():
    st.sidebar.header("1. Selecteer Data")
    
    # Seizoen - Default 25/26
    df_seasons = run_query("SELECT DISTINCT season FROM public.iterations ORDER BY season DESC;")
    if df_seasons.empty: return None, None, None
    seasons_list = df_seasons['season'].tolist()
    def_s_idx = seasons_list.index('25/26') if '25/26' in seasons_list else 0
    selected_season = st.sidebar.selectbox("Seizoen:", seasons_list, index=def_s_idx)

    # Competitie - Default Challenger Pro League
    iteration_id = None
    df_comps = run_query('SELECT DISTINCT "competitionName", id FROM public.iterations WHERE season = %s', (selected_season,))
    if not df_comps.empty:
        comp_map = dict(zip(df_comps['competitionName'], df_comps['id']))
        comp_list = list(comp_map.keys())
        def_c_idx = comp_list.index('Challenger Pro League') if 'Challenger Pro League' in comp_list else 0
        selected_comp = st.sidebar.selectbox("Competitie:", comp_list, index=def_c_idx)
        iteration_id = str(comp_map[selected_comp])

    # Club - Default KV Kortrijk (ID 362)
    selected_squad_id = None
    if iteration_id:
        squad_query = """
            SELECT DISTINCT s.id, s.name FROM analysis.squads s
            JOIN analysis.player_final_scores pfs ON s.id = pfs."squadId"::text
            WHERE pfs."iterationId"::text = %s ORDER BY s.name
        """
        df_sq = run_query(squad_query, (iteration_id,))
        if not df_sq.empty:
            sq_map = dict(zip(df_sq['name'], df_sq['id']))
            sq_list = list(sq_map.keys())
            def_q_idx = sq_list.index('KV Kortrijk') if 'KV Kortrijk' in sq_list else 0
            sel_sq = st.sidebar.selectbox("Club:", sq_list, index=def_q_idx)
            selected_squad_id = sq_map[sel_sq]

    return selected_season, iteration_id, selected_squad_id

# 3. CONFIGURATIES
POSITION_METRICS = {
    "central_defender": {"aan_bal": [66, 58, 64, 10, 163], "zonder_bal": [103, 93, 32, 94, 17, 65, 92]},
    "wingback": {"aan_bal": [61, 66, 58, 54, 53, 52, 10, 9, 14], "zonder_bal": [68, 69, 17, 70]},
    "defensive_midfield": {"aan_bal": [60, 10, 163, 44], "zonder_bal": [29, 65, 17, 16, 69, 68, 67]},
    "central_midfield": {"aan_bal": [60, 61, 62, 73, 72, 64, 10, 163, 145], "zonder_bal": [65, 17, 69, 68]},
    "attacking_midfield": {"aan_bal": [60, 61, 62, 73, 58, 2, 15, 52, 72, 10, 74, 9], "zonder_bal": []},
    "winger": {"aan_bal": [60, 61, 62, 58, 54, 1, 53, 10, 9, 14, 6, 145], "zonder_bal": []},
    "center_forward": {"aan_bal": [60, 61, 62, 73, 63, 2, 64, 10, 74, 9, 92, 97, 14, 6, 145], "zonder_bal": []}
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

def check_login(email, password):
    query = "SELECT id, naam, rol, toegangsniveau FROM scouting.gebruikers WHERE email = %s AND wachtwoord = %s AND actief = TRUE"
    df = run_query(query, (email, password))
    return df.iloc[0].to_dict() if not df.empty else None
