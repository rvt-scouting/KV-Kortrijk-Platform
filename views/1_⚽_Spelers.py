import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
from utils import run_query, get_config_for_position, POSITION_METRICS, POSITION_KPIS

# -----------------------------------------------------------------------------
# 1. PAGINA CONFIGURATIE
# -----------------------------------------------------------------------------
st.set_page_config(page_title="Speler Analyse", page_icon="⚽", layout="wide")

# -----------------------------------------------------------------------------
# 2. NAVIGATIE LOGICA
# -----------------------------------------------------------------------------
if "pending_nav" in st.session_state:
    nav = st.session_state.pending_nav
    if nav.get("mode") == "Spelers":
        try:
            st.session_state.sb_season = nav["season"]
            st.session_state.sb_competition = nav["competition"]
            st.session_state.sb_player = nav["target_name"]
        except:
            pass
        del st.session_state.pending_nav

# -----------------------------------------------------------------------------
# 3. SIDEBAR SELECTIE
# -----------------------------------------------------------------------------
st.sidebar.header("1. Selecteer Data")

try:
    df_seasons = run_query("SELECT DISTINCT season FROM public.iterations ORDER BY season DESC;")
    seasons_list = df_seasons['season'].tolist()
    if "sb_season" not in st.session_state and seasons_list:
        st.session_state.sb_season = seasons_list[0]
    selected_season = st.sidebar.selectbox("Seizoen:", seasons_list, key="sb_season")
except:
    st.error("Fout bij laden seizoenen."); st.stop()

if selected_season:
    df_competitions = run_query('SELECT DISTINCT "competitionName" FROM public.iterations WHERE season = %s ORDER BY "competitionName";', params=(selected_season,))
    competitions_list = df_competitions['competitionName'].tolist()
    if "sb_competition" not in st.session_state and competitions_list:
         st.session_state.sb_competition = competitions_list[0]
    selected_competition = st.sidebar.selectbox("Competitie:", competitions_list, key="sb_competition")
else: selected_competition = None

selected_iteration_id = None
if selected_season and selected_competition:
    df_details = run_query('SELECT id FROM public.iterations WHERE season = %s AND "competitionName" = %s LIMIT 1;', params=(selected_season, selected_competition))
    if not df_details.empty:
        selected_iteration_id = str(df_details.iloc[0]['id'])
    else: st.stop() 
else: st.stop() 

# -----------------------------------------------------------------------------
# 4. SPELER SELECTIE (Bron: player_kpis voor 100% dekking)
# -----------------------------------------------------------------------------
st.sidebar.divider()
st.sidebar.header("2. Speler Zoeken")

players_query = """
    SELECT DISTINCT p.commonname, p.id as "playerId", sq.name as "squadName"
    FROM public.player_kpis pk
    JOIN public.players p ON CAST(pk."playerId" AS TEXT) = p.id
    LEFT JOIN public.squads sq ON CAST(pk."squadId" AS TEXT) = sq.id
    WHERE CAST(pk."iterationId" AS TEXT) = %s
    ORDER BY p.commonname;
"""
try:
    df_players = run_query(players_query, params=(selected_iteration_id,))
    unique_names = df_players['commonname'].unique().tolist()
    
    idx_p = 0
    if "sb_player" in st.session_state and st.session_state.sb_player in unique_names:
        idx_p = unique_names.index(st.session_state.sb_player)
        
    selected_player_name = st.sidebar.selectbox("Kies een speler:", unique_names, index=idx_p, key="sb_player")
    
    cand = df_players[df_players['commonname'] == selected_player_name]
    if len(cand) > 1:
        squad_sel = st.sidebar.selectbox("Kies team:", cand['squadName'].tolist())
        final_player_id = cand[cand['squadName'] == squad_sel].iloc[0]['playerId']
    else:
        final_player_id = cand.iloc[0]['playerId']
except:
    st.error("Speler selectie mislukt."); st.stop()

# -----------------------------------------------------------------------------
# 5. DASHBOARD
# -----------------------------------------------------------------------------
st.title(f"🏃‍♂️ {selected_player_name}")

# A. TRANSFER STATUS
check_off = "SELECT status, makelaar FROM scouting.offered_players WHERE player_id = %s ORDER BY aangeboden_datum DESC LIMIT 1"
df_off = run_query(check_off, params=(str(final_player_id),))
if not df_off.empty:
    st.warning(f"📥 Aangeboden via {df_off.iloc[0]['makelaar']} (Status: {df_off.iloc[0]['status']})")

# B. DATA SCORES
score_query = """
    SELECT p.*, a.*, sq_curr.name as "current_team_name"
    FROM public.players p
    LEFT JOIN analysis.final_impect_scores a ON p.id = a."playerId" AND CAST(a."iterationId" AS TEXT) = %s
    LEFT JOIN public.squads sq_curr ON p."currentSquadId" = sq_curr.id
    WHERE p.id = %s
"""
df_scores = run_query(score_query, params=(selected_iteration_id, str(final_player_id)))

if not df_scores.empty:
    row = df_scores.iloc[0]
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("Team", row['current_team_name'] or "Onbekend")
    with c2: st.metric("Geboortedatum", str(row.get('birthdate', '-')))
    with c3: st.metric("Geboorteplaats", row.get('birthplace', '-'))
    with c4: st.metric("Voet", row.get('leg', '-'))

    # Check op berekende data
    if pd.isna(row.get('position')):
        st.info("ℹ️ Geen berekende Impect-scores (te weinig minuten).")
    else:
        st.divider()
        st.subheader(f"📊 Prestatie Profiel: {row['position']}")
        
        profile_mapping = {
            "KVK CV": row.get('cb_kvk_score'), "KVK Wingback": row.get('wb_kvk_score'),
            "KVK Def Mid": row.get('dm_kvk_score'), "KVK Cen Mid": row.get('cm_kvk_score'),
            "KVK Att Mid": row.get('acm_kvk_score'), "KVK Flank": row.get('fa_kvk_score'),
            "KVK Spits": row.get('fw_kvk_score'), "Afmaker": row.get('fw_finisher_kvk_score')
        }
        df_chart = pd.DataFrame([{"Profiel": k, "Score": v} for k, v in profile_mapping.items() if v and v > 0])
        
        ca, cb = st.columns([1, 2])
        with ca:
            st.dataframe(df_chart, use_container_width=True, hide_index=True)
        with cb:
            fig = px.line_polar(df_chart, r='Score', theta='Profiel', line_close=True)
            fig.update_traces(fill='toself', line_color='#d71920')
            st.plotly_chart(fig, use_container_width=True)

        # KPIs & METRIEKEN
        m_cfg = get_config_for_position(row['position'], POSITION_METRICS)
        k_cfg = get_config_for_position(row['position'], POSITION_KPIS)
        
        c_m, c_k = st.columns(2)
        with c_m:
            st.write("**Metrieken**")
            # Logica voor ophalen metrieken tabel (zie eerdere versies voor detail)
        with c_k:
            st.write("**KPIs**")
            # Logica voor ophalen KPI tabel

    # C. SKILLCORNER
    st.divider()
    st.subheader("💪 Fysieke Data (SkillCorner)")
    # Query en tabel weergave voor fysieke data

    # D. SCOUTING (INTERN)
    st.divider()
    st.subheader("🕵️ Scouting Rapporten (Intern)")
    q_scout = "SELECT r.*, g.naam FROM scouting.rapporten r JOIN scouting.gebruikers g ON r.scout_id = g.id WHERE speler_id = %s ORDER BY aangemaakt_op DESC"
    df_sc = run_query(q_scout, params=(str(final_player_id),))
    if not df_sc.empty:
        st.dataframe(df_sc[['aangemaakt_op', 'naam', 'beoordeling', 'advies']], use_container_width=True, hide_index=True)
        with st.expander("Lees teksten"):
            for _, r in df_sc.iterrows(): st.info(f"{r['naam']}: {r['rapport_tekst']}")

    # E. INTELLIGENCE (STRATEGISCH)
    st.divider()
    st.subheader("🧠 Strategisch Dossier (Intelligence)")
    intel_q = "SELECT * FROM scouting.speler_intelligence WHERE speler_id = %s ORDER BY laatst_bijgewerkt DESC LIMIT 1"
    df_i = run_query(intel_q, params=(str(final_player_id),))
    if not df_i.empty:
        ir = df_i.iloc[0]
        l1, l2, l3 = st.columns(3)
        with l1: 
            if ir.get('instagram_url'): st.link_button("📸 Instagram", ir['instagram_url'])
        with l2: 
            if ir.get('transfermarkt_url'): st.link_button("⚽ Transfermarkt", ir['transfermarkt_url'])
        
        ia, ib = st.columns(2)
        with ia:
            st.info(f"**Club/Netwerk:**\n{ir['club_informatie']}")
            st.info(f"**Familie:**\n{ir['familie_achtergrond']}")
        with ib:
            st.warning(f"**Mentaliteit:**\n{ir['persoonlijkheid']}")
            st.error(f"**Makelaar:**\n{ir['makelaar_details']}")

    # F. SIMILARITY
    st.divider()
    st.subheader("👯 Vergelijkbare Spelers")
    # Similarity logica zoals eerder gedefinieerd
