import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
from utils import run_query, get_config_for_position, POSITION_METRICS, POSITION_KPIS

st.set_page_config(page_title="Speler Analyse", page_icon="⚽", layout="wide")

# -----------------------------------------------------------------------------
# 0. NAVIGATIE LOGICA (Voor doorklikken vanuit andere pagina's)
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
    
    if len(candidate_rows) > 1:
        squad_options = candidate_rows['squadName'].tolist()
        selected_squad = st.sidebar.selectbox("Kies team:", squad_options)
        final_player_id = candidate_rows[candidate_rows['squadName'] == selected_squad].iloc[0]['playerId']
    else:
        final_player_id = candidate_rows.iloc[0]['playerId']
except Exception as e: st.error("Fout bij ophalen spelers."); st.stop()

# --- A. BASIS INFO & SCORES ---
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
    df_scores = run_query(score_query, params=(selected_iteration_id, str(final_player_id)))
    
    if not df_scores.empty:
        row = df_scores.iloc[0]
        st.subheader(f"ℹ️ {selected_player_name}")
        c1, c2, c3, c4 = st.columns(4)
        with c1: st.metric("Team", row['current_team_name'] or "-")
        with c2: st.metric("Geboortedatum", str(row['birthdate']) or "-")
        with c3: st.metric("Geboorteplaats", row['birthplace'] or "-")
        with c4: st.metric("Voet", row['leg'] or "-")
        
        st.divider()

        # --- B. SPIDER CHART LOGICA ---
        # Alle mogelijke profielen mappen
        full_profiles = {
            "CV": row['cb_kvk_score'], "Wingback": row['wb_kvk_score'], "CVM": row['dm_kvk_score'],
            "CM": row['cm_kvk_score'], "CAM": row['acm_kvk_score'], "Flank": row['fa_kvk_score'],
            "Spits": row['fw_kvk_score'], "Voetballende CV": row['footballing_cb_kvk_score'],
            "Controlerende CV": row['controlling_cb_kvk_score'], "Box-to-Box": row['box_to_box_cm_kvk_score'],
            "Targetman": row['fw_target_kvk_score'], "Afmaker": row['fw_finisher_kvk_score'],
            "Spelmaker": row['playmaker_dm_kvk_score'], "Ballenafpakker": row['ball_winning_dm_kvk_score']
        }
        
        # Filter alleen profielen met een score > 0
        active_p = {k: float(v) for k, v in full_profiles.items() if v is not None and v > 0}
        df_spider = pd.DataFrame(list(active_p.items()), columns=['Profiel', 'Score'])

        col_table, col_chart = st.columns([1, 2])
        
        with col_table:
            st.write(f"**Positie:** {row['position']}")
            st.dataframe(
                df_spider.sort_values(by='Score', ascending=False),
                use_container_width=True, hide_index=True
            )

        with col_chart:
            if not df_spider.empty:
                # Spider chart maken
                fig = px.line_polar(df_spider, r='Score', theta='Profiel', line_close=True)
                fig.update_traces(fill='toself', line_color='#d71920', marker=dict(size=8))
                fig.update_layout(
                    polar=dict(radialaxis=dict(visible=True, range=[0, 100])),
                    showlegend=False,
                    title="KVK Data Profiel"
                )
                st.plotly_chart(fig, use_container_width=True)

        # --- C. GEDETAILLEERDE STATS (Piramide: Niveau 2) ---
        st.divider()
        st.subheader("📊 Gedetailleerde Stats & KPI's")
        
        metrics_cfg = get_config_for_position(row['position'], POSITION_METRICS)
        kpis_cfg = get_config_for_position(row['position'], POSITION_KPIS)
        
        c_m, c_k = st.columns(2)
        
        with c_m:
            st.write("**Impect Metrieken**")
            if metrics_cfg:
                m_ids = metrics_cfg.get('aan_bal', []) + metrics_cfg.get('zonder_bal', [])
                if m_ids:
                    q = """SELECT d.name as "Metriek", s.final_score_1_to_100 as "Score" 
                           FROM analysis.player_final_scores s 
                           JOIN public.player_score_definitions d ON CAST(s.metric_id AS TEXT) = d.id 
                           WHERE s."iterationId" = %s AND s."playerId" = %s AND s.metric_id IN %s"""
                    df_m = run_query(q, params=(selected_iteration_id, str(final_player_id), tuple(str(x) for x in m_ids)))
                    st.dataframe(df_m, use_container_width=True, hide_index=True)
            else: st.info("Geen metrieken voor deze positie.")

        with c_k:
            st.write("**KPI Scores**")
            if kpis_cfg:
                k_ids = kpis_cfg.get('aan_bal', []) + kpis_cfg.get('zonder_bal', [])
                if k_ids:
                    q = """SELECT d.name as "KPI", s.final_score_1_to_100 as "Score" 
                           FROM analysis.kpis_final_scores s 
                           JOIN analysis.kpi_definitions d ON CAST(s.metric_id AS TEXT) = d.id 
                           WHERE s."iterationId" = %s AND s."playerId" = %s AND s.metric_id IN %s"""
                    df_k = run_query(q, params=(selected_iteration_id, str(final_player_id), tuple(str(x) for x in k_ids)))
                    st.dataframe(df_k, use_container_width=True, hide_index=True)

        # --- D. SIMILARITY (Piramide: Niveau 3) ---
        st.divider()
        st.subheader("👯 Vergelijkbare Spelers")
        
        # Gebruik de profielen uit de spider chart voor vergelijking
        compare_cols_names = df_spider['Profiel'].tolist()
        # Mapping terug naar database kolomnamen
        db_map = {
            "CV": "cb_kvk_score", "Wingback": "wb_kvk_score", "CVM": "dm_kvk_score",
            "CM": "cm_kvk_score", "CAM": "acm_kvk_score", "Flank": "fa_kvk_score",
            "Spits": "fw_kvk_score", "Voetballende CV": "footballing_cb_kvk_score"
        }
        db_cols = [db_map[n] for n in compare_cols_names if n in db_map]

        if db_cols:
            cols_sql = ", ".join([f'a."{c}"' for c in db_cols])
            sim_q = f"""
                SELECT p.commonname as "Naam", sq.name as "Team", i.season as "Seizoen", 
                       i."competitionName" as "Competitie", {cols_sql}
                FROM analysis.final_impect_scores a
                JOIN public.players p ON a."playerId" = p.id
                LEFT JOIN public.squads sq ON a."squadId" = sq.id
                JOIN public.iterations i ON a."iterationId" = i.id
                WHERE a.position = %s AND i.season IN ('25/26', '2025')
            """
            df_sim = run_query(sim_q, params=(row['position'],))
            if not df_sim.empty:
                # Bereken Euclidische afstand (eenvoudige gelijkenis)
                target_values = row[db_cols].values.astype(float)
                sim_scores = []
                for idx, r_sim in df_sim.iterrows():
                    comp_values = r_sim[db_cols].values.astype(float)
                    dist = np.linalg.norm(target_values - comp_values)
                    sim_pct = max(0, 100 - dist)
                    sim_scores.append(sim_pct)
                
                df_sim['Gelijkenis %'] = sim_scores
                df_sim = df_sim[df_sim['Naam'] != selected_player_name]
                st.dataframe(
                    df_sim[['Naam', 'Team', 'Seizoen', 'Gelijkenis %']].sort_values(by='Gelijkenis %', ascending=False).head(10),
                    use_container_width=True, hide_index=True
                )

    else:
        st.error("Geen data gevonden voor deze selectie.")

except Exception as e:
    st.error(f"Fout bij laden pagina: {e}")
