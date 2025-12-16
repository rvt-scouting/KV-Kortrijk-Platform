import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
from utils import run_query, get_config_for_position, POSITION_METRICS, POSITION_KPIS

st.set_page_config(page_title="Speler Analyse", page_icon="⚽", layout="wide")

# -----------------------------------------------------------------------------
# 0. NAVIGATIE LOGICA
# -----------------------------------------------------------------------------
if "pending_nav" in st.session_state:
    nav = st.session_state.pending_nav
    if nav.get("mode") == "Spelers":
        try:
            st.session_state.sb_season = nav["season"]
            st.session_state.sb_competition = nav["competition"]
            st.session_state.sb_player = nav["target_name"]
        except Exception as e:
            print(f"Navigatie fout: {e}")
        del st.session_state.pending_nav

# -----------------------------------------------------------------------------
# 1. SIDEBAR SELECTIE
# -----------------------------------------------------------------------------
st.sidebar.header("1. Selecteer Data")

try:
    df_seasons = run_query("SELECT DISTINCT season FROM public.iterations ORDER BY season DESC;")
    seasons_list = df_seasons['season'].tolist()
    if "sb_season" not in st.session_state and seasons_list:
        st.session_state.sb_season = seasons_list[0]
    selected_season = st.sidebar.selectbox("Seizoen:", seasons_list, key="sb_season")
except Exception as e:
    st.error("Kon seizoenen niet laden."); st.stop()

if selected_season:
    df_competitions = run_query('SELECT DISTINCT "competitionName" FROM public.iterations WHERE season = %s ORDER BY "competitionName";', params=(selected_season,))
    competitions_list = df_competitions['competitionName'].tolist()
    if "sb_competition" not in st.session_state and competitions_list:
        st.session_state.sb_competition = competitions_list[0]
    selected_competition = st.sidebar.selectbox("Competitie:", competitions_list, key="sb_competition")
else: 
    selected_competition = None

selected_iteration_id = None
if selected_season and selected_competition:
    df_details = run_query('SELECT id FROM public.iterations WHERE season = %s AND "competitionName" = %s LIMIT 1;', params=(selected_season, selected_competition))
    if not df_details.empty:
        selected_iteration_id = str(df_details.iloc[0]['id'])
    else: st.error("Kon geen ID vinden."); st.stop() 

# -----------------------------------------------------------------------------
# 2. SPELER LOGICA
# -----------------------------------------------------------------------------
st.title("🏃‍♂️ Speler Analyse")

st.sidebar.divider()
st.sidebar.header("2. Speler Zoeken")
players_query = """
    SELECT p.commonname, p.id as "playerId", sq.name as "squadName"
    FROM public.players p
    JOIN analysis.final_impect_scores s ON p.id = s."playerId"
    LEFT JOIN public.squads sq ON s."squadId" = sq.id
    WHERE s."iterationId" = %s
    ORDER BY p.commonname;
"""
try:
    df_players = run_query(players_query, params=(selected_iteration_id,))
    if df_players.empty:
        st.warning("Geen spelers gevonden."); st.stop()
        
    unique_names = df_players['commonname'].unique().tolist()
    idx_p = 0
    if "sb_player" in st.session_state and st.session_state.sb_player in unique_names:
        idx_p = unique_names.index(st.session_state.sb_player)
        
    selected_player_name = st.sidebar.selectbox("Kies een speler:", unique_names, index=idx_p, key="sb_player")
    candidate_rows = df_players[df_players['commonname'] == selected_player_name]
    final_player_id = candidate_rows.iloc[0]['playerId'] if not candidate_rows.empty else None
except Exception as e: st.error("Fout bij ophalen spelers."); st.stop()

# C. DATA METRICS
score_query = """
    SELECT p.commonname, a.position, p.birthdate, p.birthplace, p.leg, sq_curr.name as "current_team_name",
        a.cb_kvk_score, a.wb_kvk_score, a.dm_kvk_score, a.cm_kvk_score, a.acm_kvk_score, a.fa_kvk_score, a.fw_kvk_score,
        a.footballing_cb_kvk_score, a.controlling_cb_kvk_score, a.defensive_wb_kvk_score, a.offensive_wingback_kvk_score,
        a.ball_winning_dm_kvk_score, a.playmaker_dm_kvk_score, a.box_to_box_cm_kvk_score, a.deep_running_acm_kvk_score,
        a.playmaker_off_acm_kvk_score, a.fa_inside_kvk_score, a.fa_wide_kvk_score, a.fw_target_kvk_score,
        a.fw_running_kvk_score, a.fw_finisher_kvk_score
    FROM analysis.final_impect_scores a
    JOIN public.players p ON a."playerId" = p.id
    LEFT JOIN public.squads sq_curr ON p."currentSquadId" = sq_curr.id
    WHERE a."iterationId" = %s AND p.id = %s
"""
try:
    p_player_id = str(final_player_id)
    df_scores = run_query(score_query, params=(selected_iteration_id, p_player_id))
    
    if not df_scores.empty:
        row = df_scores.iloc[0]
        st.subheader(f"ℹ️ {selected_player_name}")
        
        # PROFIELEN MAPPER (Alle sub-profielen uit je database)
        full_profile_mapping = {
            "Centrale Verdediger": row['cb_kvk_score'], 
            "Wingback": row['wb_kvk_score'],
            "Verdedigende Mid.": row['dm_kvk_score'], 
            "Centrale Mid.": row['cm_kvk_score'],
            "Aanvallende Mid.": row['acm_kvk_score'], 
            "Flank Aanvaller": row['fa_kvk_score'],
            "Spits": row['fw_kvk_score'],
            "Voetballende CV": row['footballing_cb_kvk_score'],
            "Controlerende CV": row['controlling_cb_kvk_score'],
            "Verdedigende Back": row['defensive_wb_kvk_score'],
            "Aanvallende Back": row['offensive_wingback_kvk_score'],
            "Ballenafpakker": row['ball_winning_dm_kvk_score'],
            "Spelmaker (CVM)": row['playmaker_dm_kvk_score'],
            "Box-to-Box": row['box_to_box_cm_kvk_score'],
            "Diepgaande '10'": row['deep_running_acm_kvk_score'],
            "Spelmakende '10'": row['playmaker_off_acm_kvk_score'],
            "Buitenspeler (In)": row['fa_inside_kvk_score'],
            "Buitenspeler (Uit)": row['fa_wide_kvk_score'],
            "Targetman": row['fw_target_kvk_score'],
            "Lopende Spits": row['fw_running_kvk_score'],
            "Afmaker": row['fw_finisher_kvk_score']
        }

        # Filter: Alleen profielen tonen waar de score > 0 is
        active_profiles = {k: v for k, v in full_profile_mapping.items() if v is not None and v > 0}
        df_spider = pd.DataFrame(list(active_profiles.items()), columns=['Profiel', 'Score'])
        
        c1, c2 = st.columns([1, 2])
        with c1:
            st.write(f"**Positie:** {row['position']}")
            st.dataframe(df_spider.sort_values(by='Score', ascending=False).style.format({'Score': '{:.1f}'}), use_container_width=True, hide_index=True)
            
        with c2:
            if not df_spider.empty:
                # We voegen het eerste punt weer toe aan het einde om de cirkel te sluiten
                df_plot = pd.concat([df_spider, df_spider.iloc[[0]]])
                
                fig = px.line_polar(df_plot, r='Score', theta='Profiel', line_close=True)
                fig.update_traces(fill='toself', line_color='#d71920', marker=dict(size=6))
                fig.update_layout(
                    polar=dict(
                        radialaxis=dict(visible=True, range=[0, 100]),
                        angularaxis=dict(direction="clockwise", period=len(df_spider))
                    ),
                    margin=dict(l=80, r=80, t=20, b=20)
                )
                st.plotly_chart(fig, use_container_width=True)

        # De rest van je code (KPI's, Similars) blijft hetzelfde...
        st.divider()
        st.subheader("📊 Gedetailleerde Stats & KPI's")
        # ... (rest van de tabellen)

    else: st.error("Geen data.")
except Exception as e: st.error(f"Fout: {e}")
