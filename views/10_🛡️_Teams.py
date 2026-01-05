import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
from utils import run_query

st.set_page_config(page_title="Team Analyse", page_icon="🛡️", layout="wide")

# -----------------------------------------------------------------------------
# 0. NAVIGATIE LOGICA
# -----------------------------------------------------------------------------
if "pending_nav" in st.session_state:
    nav = st.session_state.pending_nav
    if nav.get("mode") == "Teams":
        try:
            st.session_state.sb_season = nav["season"]
            st.session_state.sb_competition = nav["competition"]
            st.session_state.sb_team = nav["target_name"]
        except Exception as e:
            print(f"Navigatie fout: {e}")
        del st.session_state.pending_nav

# -----------------------------------------------------------------------------
# 1. SIDEBAR
# -----------------------------------------------------------------------------
st.sidebar.header("1. Selecteer Data")
try:
    df_seasons = run_query("SELECT DISTINCT season FROM public.iterations ORDER BY season DESC;")
    seasons_list = df_seasons['season'].tolist()
    if "sb_season" not in st.session_state and seasons_list:
        st.session_state.sb_season = seasons_list[0]
    selected_season = st.sidebar.selectbox("Seizoen:", seasons_list, key="sb_season")
except Exception as e: st.error("Fout seizoenen."); st.stop()

if selected_season:
    df_competitions = run_query('SELECT DISTINCT "competitionName" FROM public.iterations WHERE season = %s ORDER BY "competitionName";', params=(selected_season,))
    competitions_list = df_competitions['competitionName'].tolist()
    if "sb_competition" not in st.session_state and competitions_list:
        st.session_state.sb_competition = competitions_list[0]
    selected_competition = st.sidebar.selectbox("Competitie:", competitions_list, key="sb_competition")
else: selected_competition = None

selected_iteration_id = None
if selected_season and selected_competition:
    df_details = run_query('SELECT season, "competitionName", id FROM public.iterations WHERE season = %s AND "competitionName" = %s LIMIT 1;', params=(selected_season, selected_competition))
    if not df_details.empty:
        selected_iteration_id = str(df_details.iloc[0]['id'])
    else: st.error("Geen ID."); st.stop() 
else: st.warning("👈 Kies competitie."); st.stop() 

# -----------------------------------------------------------------------------
# 2. TEAM LOGICA
# -----------------------------------------------------------------------------
st.title("🛡️ Team Analyse")

st.sidebar.divider()
st.sidebar.header("2. Team Selectie")
teams_query = """SELECT DISTINCT sq.name, sq.id as "squadId" FROM public.squads sq JOIN analysis.squad_final_scores s ON sq.id = s."squadId" WHERE s."iterationId" = %s ORDER BY sq.name;"""
try:
    df_teams = run_query(teams_query, params=(selected_iteration_id,))
    if df_teams.empty: st.warning("Geen teams."); st.stop()
    
    team_names = df_teams['name'].tolist()
    
    idx_t = 0
    if "sb_team" in st.session_state and st.session_state.sb_team in team_names:
        idx_t = team_names.index(st.session_state.sb_team)
        
    selected_team_name = st.sidebar.selectbox("Kies een team:", team_names, index=idx_t, key="sb_team")
    candidate = df_teams[df_teams['name'] == selected_team_name]
    
    final_squad_id = None
    if len(candidate) > 1:
        st.sidebar.warning("Meerdere teams gevonden.")
        opts = candidate.apply(lambda x: f"{x['name']} (ID: {x['squadId']})", axis=1).tolist()
        sel = st.sidebar.selectbox("Specifieer:", opts)
        final_squad_id = sel.split("ID: ")[1].replace(")", "")
    elif len(candidate) == 1: final_squad_id = candidate.iloc[0]['squadId']
    else: st.error("Geen team gevonden."); st.stop()
    
    if final_squad_id:
        st.divider()
        t_dets = run_query('SELECT name, "imageUrl" FROM public.squads WHERE id = %s', params=(final_squad_id,))
        if not t_dets.empty:
            t_row = t_dets.iloc[0]
            c1, c2 = st.columns([1, 5])
            with c1: 
                if t_row['imageUrl']: st.image(t_row['imageUrl'], width=100)
            with c2: st.header(f"🛡️ {t_row['name']}")
            
            # Profielen
            st.divider(); st.subheader("📊 Team Profiel Scores")
            prof_q = 'SELECT profile_name as "Profiel", score as "Score" FROM analysis.squad_profile_scores WHERE "squadId" = %s AND "iterationId" = %s ORDER BY score DESC'
            try:
                df_p = run_query(prof_q, params=(final_squad_id, selected_iteration_id))
                if not df_p.empty:
                    c1, c2 = st.columns([1, 2])
                    def hl(v): return 'color: #2ecc71; font-weight: bold' if isinstance(v, (int,float)) and v > 66 else ''
                    with c1: st.dataframe(df_p.style.applymap(hl, subset=['Score']).format({'Score': '{:.1f}'}), use_container_width=True, hide_index=True)
                    with c2: 
                        fig = px.bar(df_p, x='Profiel', y='Score', color_discrete_sequence=['#d71920'])
                        st.plotly_chart(fig, use_container_width=True)
                else: st.info("Geen profielen.")
            except: st.error("Fout profielen.")

            # Metrieken & KPIs
            def hl_inv(v): return 'background-color: #e74c3c; color: white; font-weight: bold' if str(v).lower().strip() == 'true' else ''
            
            with st.expander("📊 Team Impect Scores (Metrieken)", expanded=False):
                q = 'SELECT d.name as "Metriek", d.details_label as "Detail", d.inverted as "Inverted", s.final_score_1_to_100 as "Score" FROM analysis.squad_final_scores s JOIN public.squad_score_definitions d ON d.id = REPLACE(s.metric_id, \'s\', \'\') WHERE s."squadId" = %s AND s."iterationId" = %s ORDER BY s.final_score_1_to_100 DESC'
                try:
                    df = run_query(q, params=(final_squad_id, selected_iteration_id))
                    if not df.empty: st.dataframe(df.style.applymap(hl, subset=['Score']).applymap(hl_inv, subset=['Inverted']).format({'Score': '{:.1f}'}), use_container_width=True, hide_index=True)
                    else: st.info("Geen data.")
                except: st.error("Fout metrieken.")

            with st.expander("📉 Team Impect KPIs (Details)", expanded=False):
                q = 'SELECT d.name as "KPI", s.final_score_1_to_100 as "Score" FROM analysis.squadkpi_final_scores s JOIN analysis.kpi_definitions d ON d.id = REPLACE(s.metric_id, \'k\', \'\') WHERE s."squadId" = %s AND s."iterationId" = %s ORDER BY s.final_score_1_to_100 DESC'
                try:
                    df = run_query(q, params=(final_squad_id, selected_iteration_id))
                    if not df.empty: st.dataframe(df.style.applymap(hl, subset=['Score']).format({'Score': '{:.1f}'}), use_container_width=True, hide_index=True)
                    else: st.info("Geen data.")
                except: st.error("Fout KPIs.")

            # SIMILARITY
            st.markdown("---"); st.subheader("🤝 Vergelijkbare Teams")
            st.caption("Vergelijkt enkel met teams uit seizoenen '25/26' en '2025'.")
            
            all_prof_q = """
                SELECT s."squadId", sq.name as "Team", i.season as "Seizoen", i."competitionName" as "Competitie", s.profile_name, s.score 
                FROM analysis.squad_profile_scores s 
                JOIN public.squads sq ON s."squadId" = sq.id 
                JOIN public.iterations i ON s."iterationId" = i.id
                WHERE i.season IN ('25/26', '2025')
            """
            try:
                df_all = run_query(all_prof_q)
                if not df_all.empty:
                    df_piv = df_all.pivot_table(index=['squadId', 'Team', 'Seizoen', 'Competitie'], columns='profile_name', values='score').fillna(0)
                    curr_idx = (final_squad_id, t_row['name'], selected_season, selected_competition)
                    
                    if curr_idx in df_piv.index:
                        target = df_piv.loc[curr_idx]
                        diff = (df_piv - target).abs().mean(axis=1)
                        sim = (100 - diff).sort_values(ascending=False)
                        sim = sim[sim.index != curr_idx]
                        
                        top5 = sim.head(15).reset_index(); top5.columns = ['ID', 'Team', 'Seizoen', 'Competitie', 'Gelijkenis %']
                        def c_sim(v): 
                            c = '#2ecc71' if v > 90 else '#27ae60' if v > 80 else 'black'
                            return f'color: {c}; font-weight: {"bold" if v > 80 else "normal"}'
                        
                        disp = top5[['Team', 'Seizoen', 'Competitie', 'Gelijkenis %']]
                        ev = st.dataframe(disp.style.applymap(c_sim, subset=['Gelijkenis %']).format({'Gelijkenis %': '{:.1f}%'}), use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")
                        
                        if len(ev.selection.rows) > 0:
                            idx = ev.selection.rows[0]; cr = disp.iloc[idx]
                            st.session_state.pending_nav = {"season": cr['Seizoen'], "competition": cr['Competitie'], "target_name": cr['Team'], "mode": "Teams"}
                            st.rerun()
                    else: st.warning("Huidig team niet in vergelijkingsset.")
                else: st.info("Geen teams.")
            except Exception as e: st.error("Fout similarity."); st.code(e)
except Exception as e: st.error("Teamlijst fout."); st.code(e)
