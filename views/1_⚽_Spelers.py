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
else: st.warning("👈 Kies eerst een seizoen en competitie."); st.stop() 

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
    final_player_id = None
    
    if len(candidate_rows) > 1:
        squad_options = [s for s in candidate_rows['squadName'].tolist() if s is not None]
        selected_squad = st.sidebar.selectbox("Kies team:", squad_options)
        final_player_id = candidate_rows[candidate_rows['squadName'] == selected_squad].iloc[0]['playerId']
    elif len(candidate_rows) == 1: 
        final_player_id = candidate_rows.iloc[0]['playerId']
except Exception as e: st.error("Fout bij ophalen spelers."); st.stop()

# B. CHECK TRANSFER STATUS (Scouting offered)
df_offer = run_query("SELECT status, makelaar, vraagprijs, opmerkingen FROM scouting.offered_players WHERE player_id = %s ORDER BY aangeboden_datum DESC LIMIT 1", params=(str(final_player_id),))
if not df_offer.empty:
    offer_row = df_offer.iloc[0]
    st.info(f"📥 **Aangeboden door {offer_row['makelaar']}** - Status: {offer_row['status']} - Prijs: €{offer_row['vraagprijs']:,.0f}")

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
        c1, c2, c3, c4 = st.columns(4)
        with c1: st.metric("Huidig Team", row['current_team_name'] or "Onbekend")
        with c2: st.metric("Geboortedatum", str(row['birthdate']) or "-")
        with c3: st.metric("Geboorteplaats", row['birthplace'] or "-")
        with c4: st.metric("Voet", row['leg'] or "-")
        st.divider()

        # PROFIELEN VOOR SPIDER CHART
        profile_mapping = {
            "Centrale Verdediger": row['cb_kvk_score'], "Wingback": row['wb_kvk_score'],
            "Verdedigende Mid.": row['dm_kvk_score'], "Centrale Mid.": row['cm_kvk_score'],
            "Aanvallende Mid.": row['acm_kvk_score'], "Flank Aanvaller": row['fa_kvk_score'],
            "Spits": row['fw_kvk_score']
        }
        # Filter alleen de hoofdprofielen voor een schone spider chart
        active_profiles = {k: v for k, v in profile_mapping.items() if v is not None}
        df_spider = pd.DataFrame(list(active_profiles.items()), columns=['Profiel', 'Score'])
        
        c1, c2 = st.columns([1, 2])
        with c1:
            st.write(f"**Positie:** {row['position']}")
            st.dataframe(df_spider.style.format({'Score': '{:.1f}'}), use_container_width=True, hide_index=True)
            
        with c2:
            if not df_spider.empty:
                # CREATIE SPIDER CHART
                fig = px.line_polar(df_spider, r='Score', theta='Profiel', line_close=True, 
                                    title=f'KVK Spelersprofiel: {selected_player_name}')
                fig.update_traces(fill='toself', line_color='#d71920', marker=dict(size=8))
                fig.update_layout(
                    polar=dict(
                        radialaxis=dict(visible=True, range=[0, 100], tickfont=dict(size=10)),
                        angularaxis=dict(tickfont=dict(size=12, color='gray'))
                    ),
                    showlegend=False
                )
                st.plotly_chart(fig, use_container_width=True)

        # METRIEKEN & KPIS (TABELLEN)
        st.markdown("---"); st.subheader("📊 Gedetailleerde Stats")
        metrics_config = get_config_for_position(row['position'], POSITION_METRICS)
        kpis_config = get_config_for_position(row['position'], POSITION_KPIS)
        
        col_met, col_kpi = st.columns(2)
        with col_met:
            st.write("**Metrieken (Impect)**")
            if metrics_config:
                def get_metrics_table(metric_ids):
                    if not metric_ids: return pd.DataFrame()
                    ids_tuple = tuple(str(x) for x in metric_ids)
                    q = """SELECT d.name as "Metriek", s.final_score_1_to_100 as "Score" FROM analysis.player_final_scores s JOIN public.player_score_definitions d ON CAST(s.metric_id AS TEXT) = d.id WHERE s."iterationId" = %s AND s."playerId" = %s AND s.metric_id IN %s ORDER BY s.final_score_1_to_100 DESC"""
                    return run_query(q, params=(selected_iteration_id, p_player_id, ids_tuple))
                df_aan = get_metrics_table(metrics_config.get('aan_bal', []))
                if not df_aan.empty: st.dataframe(df_aan, use_container_width=True, hide_index=True)
            else: st.info("Geen metrieken geconfigureerd voor deze positie.")

        with col_kpi:
            st.write("**KPI's**")
            if kpis_config:
                def get_kpis_table(kpi_ids):
                    if not kpi_ids: return pd.DataFrame()
                    ids_tuple = tuple(str(x) for x in kpi_ids)
                    q = """SELECT d.name as "KPI", s.final_score_1_to_100 as "Score" FROM analysis.kpis_final_scores s JOIN analysis.kpi_definitions d ON CAST(s.metric_id AS TEXT) = d.id WHERE s."iterationId" = %s AND s."playerId" = %s AND s.metric_id IN %s ORDER BY s.final_score_1_to_100 DESC"""
                    return run_query(q, params=(selected_iteration_id, p_player_id, ids_tuple))
                df_k1 = get_kpis_table(kpis_config.get('aan_bal', []))
                if not df_k1.empty: st.dataframe(df_k1, use_container_width=True, hide_index=True)

        # SIMILARITY
        st.markdown("---")
        st.subheader("👯 Vergelijkbare Spelers")
        
        reverse_mapping = {"Centrale Verdediger": 'cb_kvk_score', "Wingback": 'wb_kvk_score', "Verdedigende Mid.": 'dm_kvk_score', "Centrale Mid.": 'cm_kvk_score', "Aanvallende Mid.": 'acm_kvk_score', "Flank Aanvaller": 'fa_kvk_score', "Spits": 'fw_kvk_score'}
        db_cols = [reverse_mapping[c] for c in df_spider['Profiel'].tolist() if c in reverse_mapping]

        if db_cols:
            cols_str = ", ".join([f'a."{c}"' for c in db_cols])
            sim_query = f"""
                SELECT p.id as "playerId", p.commonname as "Naam", sq.name as "Team", i.season as "Seizoen", i."competitionName" as "Competitie", a.position, {cols_str}
                FROM analysis.final_impect_scores a
                JOIN public.players p ON CAST(a."playerId" AS TEXT) = CAST(p.id AS TEXT)
                LEFT JOIN public.squads sq ON CAST(a."squadId" AS TEXT) = CAST(sq.id AS TEXT)
                JOIN public.iterations i ON CAST(a."iterationId" AS TEXT) = CAST(i.id AS TEXT)
                WHERE a.position = %s AND i.season IN ('25/26', '2025')
            """
            try:
                df_all_p = run_query(sim_query, params=(row['position'],))
                if not df_all_p.empty:
                    df_all_p['unique_id'] = df_all_p['playerId'].astype(str) + "_" + df_all_p['Seizoen']
                    df_all_p = df_all_p.drop_duplicates(subset=['unique_id']).set_index('unique_id')
                    curr_uid = f"{p_player_id}_{selected_season}"
                    
                    if curr_uid in df_all_p.index:
                        target_vec = df_all_p.loc[curr_uid, db_cols]
                        diff = (df_all_p[db_cols] - target_vec).abs().mean(axis=1)
                        sim = (100 - diff).sort_values(ascending=False)
                        if curr_uid in sim.index: sim = sim.drop(curr_uid)
                        
                        top_10 = sim.head(10).index
                        results = df_all_p.loc[top_10].copy()
                        results['Gelijkenis %'] = sim.loc[top_10]
                        
                        st.dataframe(results[['Naam', 'Team', 'Seizoen', 'Competitie', 'Gelijkenis %']].style.format({'Gelijkenis %': '{:.1f}%'}), use_container_width=True, hide_index=True)
            except Exception as e: st.error(f"Fout bij vergelijking: {e}")
            
    else: st.error("Geen data gevonden.")
except Exception as e: st.error(f"Fout: {e}")
