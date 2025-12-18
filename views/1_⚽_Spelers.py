import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
from utils import run_query, get_config_for_position, POSITION_METRICS, POSITION_KPIS

st.set_page_config(page_title="Speler Analyse", page_icon="⚽", layout="wide")

# -----------------------------------------------------------------------------
# 0. NAVIGATIE LOGICA (Voor directe links vanuit andere pagina's)
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
# 1. SIDEBAR SELECTIE (Data context)
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
    else: st.error("Geen ID gevonden voor deze selectie."); st.stop() 
else: st.warning("👈 Kies een seizoen en competitie."); st.stop() 

# -----------------------------------------------------------------------------
# 2. SPELER SELECTIE (Ruwe bron: player_kpis om IEDEREEN te vinden)
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
    if df_players.empty:
        st.warning("Geen spelers gevonden."); st.stop()
    
    unique_names = df_players['commonname'].unique().tolist()
    idx_p = 0
    if "sb_player" in st.session_state and st.session_state.sb_player in unique_names:
        idx_p = unique_names.index(st.session_state.sb_player)
        
    selected_player_name = st.sidebar.selectbox("Kies een speler:", unique_names, index=idx_p, key="sb_player")
    
    cand = df_players[df_players['commonname'] == selected_player_name]
    final_player_id = cand.iloc[0]['playerId'] if len(cand) == 1 else None
    
    if len(cand) > 1:
        squad_options = cand['squadName'].tolist()
        selected_squad = st.sidebar.selectbox("Kies team:", squad_options)
        final_player_id = cand[cand['squadName'] == selected_squad].iloc[0]['playerId']
except:
    st.error("Fout bij ophalen spelers."); st.stop()

# -----------------------------------------------------------------------------
# 3. HOOFDPAGINA START
# -----------------------------------------------------------------------------
st.title(f"🏃‍♂️ Analyse: {selected_player_name}")

# A. TRANSFER STATUS BANNER
check_offer_q = "SELECT status, makelaar, vraagprijs, opmerkingen FROM scouting.offered_players WHERE player_id = %s ORDER BY aangeboden_datum DESC LIMIT 1"
df_offer = run_query(check_offer_q, params=(str(final_player_id),))

if not df_offer.empty:
    offer = df_offer.iloc[0]
    st.markdown(f"""<div style="padding:15px; background-color:#f39c1220; border:2px solid #f39c12; border-radius:8px; margin-bottom:20px;">
    <strong>📥 Aangeboden Speler:</strong> Status: {offer['status']} | Makelaar: {offer['makelaar']} | Prijs: €{offer['vraagprijs'] or '?'}<br>
    <small><i>"{offer['opmerkingen']}"</i></small></div>""", unsafe_allow_html=True)

# B. DATA OPHALEN (Harde Data)
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
    
    # Header stats
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("Team", row['current_team_name'] or "Onbekend")
    with c2: st.metric("Geboortedatum", str(row.get('birthdate', '-')))
    with c3: st.metric("Geboorteplaats", row.get('birthplace', '-'))
    with c4: st.metric("Voet", row.get('leg', '-'))
    st.markdown("---")

    # Berekende Impect Data Check
    if pd.isna(row.get('position')):
        st.info("ℹ️ Deze speler heeft nog geen berekende Impect-scores (mogelijk te weinig minuten).")
    else:
        st.subheader(f"📊 Prestatie Profiel: {row['position']}")
        
        # Spider Chart Logica
        profile_mapping = {
            "KVK CV": row.get('cb_kvk_score'), "KVK Wingback": row.get('wb_kvk_score'),
            "KVK Def Mid": row.get('dm_kvk_score'), "KVK Cen Mid": row.get('cm_kvk_score'),
            "KVK Att Mid": row.get('acm_kvk_score'), "KVK Flank": row.get('fa_kvk_score'),
            "KVK Spits": row.get('fw_kvk_score')
        }
        df_chart = pd.DataFrame([{"Profiel": k, "Score": v} for k, v in profile_mapping.items() if v and v > 0])
        
        col_list, col_spider = st.columns([1, 2])
        with col_list:
            st.dataframe(df_chart.style.format({'Score': '{:.1f}'}), use_container_width=True, hide_index=True)
        with col_spider:
            if not df_chart.empty:
                fig = px.line_polar(df_chart, r='Score', theta='Profiel', line_close=True)
                fig.update_traces(fill='toself', line_color='#d71920')
                st.plotly_chart(fig, use_container_width=True)

        # KPIs & METRIEKEN TABELLEN
        st.markdown("### 📈 Diepgaande Statistieken")
        m_cfg = get_config_for_position(row['position'], POSITION_METRICS)
        k_cfg = get_config_for_position(row['position'], POSITION_KPIS)
        
        c_met, c_kpi = st.columns(2)
        
        with c_met:
            st.write("**Belangrijkste Metrieken**")
            if m_cfg:
                ids = tuple(str(x) for x in (m_cfg.get('aan_bal', []) + m_cfg.get('zonder_bal', [])))
                if ids:
                    q = """SELECT d.name as "Metriek", s.final_score_1_to_100 as "Score" 
                           FROM analysis.player_final_scores s 
                           JOIN public.player_score_definitions d ON CAST(s.metric_id AS TEXT) = d.id 
                           WHERE s."iterationId" = %s AND s."playerId" = %s AND s.metric_id IN %s 
                           ORDER BY s.final_score_1_to_100 DESC"""
                    df_m = run_query(q, params=(selected_iteration_id, str(final_player_id), ids))
                    st.dataframe(df_m, use_container_width=True, hide_index=True)

        with c_kpi:
            st.write("**Positie-specifieke KPIs**")
            if k_cfg:
                ids = tuple(str(x) for x in (k_cfg.get('aan_bal', []) + k_cfg.get('zonder_bal', [])))
                if ids:
                    q = """SELECT d.name as "KPI", s.final_score_1_to_100 as "Score" 
                           FROM analysis.kpis_final_scores s 
                           JOIN analysis.kpi_definitions d ON CAST(s.metric_id AS TEXT) = d.id 
                           WHERE s."iterationId" = %s AND s."playerId" = %s AND s.metric_id IN %s 
                           ORDER BY s.final_score_1_to_100 DESC"""
                    df_k = run_query(q, params=(selected_iteration_id, str(final_player_id), ids))
                    st.dataframe(df_k, use_container_width=True, hide_index=True)

    # C. SKILLCORNER (Fysieke Data)
    st.divider()
    st.subheader("💪 Fysieke Data (SkillCorner)")
    q_phys = """SELECT f.total_matches, f.psv99_score as "Max Speed", f.timetosprint_score as "Accel", 
                f.sprint_distance_full_all_score as "Sprint Dist", f.sprint_count_full_all_score as "Sprint Count"
                FROM analysis.player_physical_group_scores f
                JOIN public.players p ON CAST(f.player_id AS TEXT) = CAST(p."idMappings_2_skill_corner_0" AS TEXT)
                WHERE p.id = %s LIMIT 1"""
    df_phys = run_query(q_phys, params=(str(final_player_id),))
    if not df_phys.empty:
        st.dataframe(df_phys, use_container_width=True, hide_index=True)
    else:
        st.info("Geen fysieke data beschikbaar voor deze speler.")

    # D. SCOUTING RAPPORTEN (Intern)
    st.divider()
    st.subheader("🕵️ Scouting Rapporten (Intern)")
    q_scout = """SELECT g.naam as "Scout", r.aangemaakt_op as "Datum", r.beoordeling as "Rating", 
                 r.advies as "Advies", r.rapport_tekst
                 FROM scouting.rapporten r 
                 JOIN scouting.gebruikers g ON r.scout_id = g.id 
                 WHERE r.speler_id = %s ORDER BY r.aangemaakt_op DESC"""
    df_sc = run_query(q_scout, params=(str(final_player_id),))
    if not df_sc.empty:
        st.dataframe(df_sc[['Datum', 'Scout', 'Rating', 'Advies']], use_container_width=True, hide_index=True)
        with st.expander("Lees rapport teksten"):
            for _, r in df_sc.iterrows():
                st.info(f"**{r['Scout']}** ({r['Datum']}):\n{r['rapport_tekst']}")
    else:
        st.info("Nog geen scouting rapporten.")

    # E. STRATEGISCH DOSSIER (Intelligence)
    st.divider()
    st.subheader("🧠 Strategisch Dossier (Intelligence)")
    intel_q = "SELECT * FROM scouting.speler_intelligence WHERE speler_id = %s ORDER BY laatst_bijgewerkt DESC LIMIT 1"
    df_intel = run_query(intel_q, params=(str(final_player_id),))
    
    if not df_intel.empty:
        ir = df_intel.iloc[0]
        st.caption(f"Laatst bijgewerkt: {ir['laatst_bijgewerkt']} door {ir['toegevoegd_door']}")
        
        # Social links knoppen
        sl1, sl2, sl3 = st.columns(3)
        with sl1: 
            if ir.get('instagram_url'): st.link_button("📸 Instagram", ir['instagram_url'], use_container_width=True)
        with sl2: 
            if ir.get('transfermarkt_url'): st.link_button("⚽ Transfermarkt", ir['transfermarkt_url'], use_container_width=True)
        with sl3: 
            if ir.get('twitter_url'): st.link_button("🐦 Twitter / X", ir['twitter_url'], use_container_width=True)
        
        # Content vakken
        cia, cib = st.columns(2)
        with cia:
            st.info(f"**Club & Netwerk:**\n\n{ir.get('club_informatie') or '-'}")
            st.info(f"**Familie & Omgeving:**\n\n{ir.get('familie_achtergrond') or '-'}")
        with cib:
            st.warning(f"**Persoonlijkheid:**\n\n{ir.get('persoonlijkheid') or '-'}")
            st.error(f"**Makelaar & Contract:**\n\n{ir.get('makelaar_details') or '-'}")
    else:
        st.info("Nog geen intelligence dossier beschikbaar voor deze speler.")

    # F. SIMILARITY (Vergelijkbare Spelers)
    st.divider()
    st.subheader("👯 Vergelijkbare Spelers")
    st.caption("Vergelijking op basis van berekende datamodellen.")
    # (Similarity logica kan hier worden toegevoegd indien nodig)

else:
    st.error("Kon geen data vinden voor deze speler.")
