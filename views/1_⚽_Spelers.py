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
    st.error("Fout bij ophalen seizoenen."); st.stop()

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
    else: 
        st.error("Geen ID gevonden."); st.stop()
else: 
    st.warning("👈 Kies een seizoen en competitie."); st.stop()

# -----------------------------------------------------------------------------
# 2. SPELER SELECTIE (Ruwe bron voor 100% dekking)
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
    st.error("Selectie mislukt."); st.stop()

# -----------------------------------------------------------------------------
# 3. DASHBOARD WEERGAVE
# -----------------------------------------------------------------------------
st.title("🏃‍♂️ Speler Analyse")

# A. TRANSFER STATUS
check_offer_q = """
    SELECT status, makelaar, vraagprijs, opmerkingen 
    FROM scouting.offered_players 
    WHERE player_id = %s 
    ORDER BY aangeboden_datum DESC LIMIT 1
"""
df_offer = run_query(check_offer_q, params=(str(final_player_id),))

if not df_offer.empty:
    off = df_offer.iloc[0]
    status_color = "#27ae60" if off['status'] == 'Interessant' else "#c0392b" if off['status'] == 'Afgekeurd' else "#f39c12"
    st.markdown(f"""
        <div style="padding:15px; background-color:{status_color}15; border:2px solid {status_color}; border-radius:8px; margin-bottom:25px;">
            <h4 style="color:{status_color}; margin:0;">📥 Aangeboden Speler</h4>
            <p style="margin:5px 0;"><strong>Status:</strong> {off['status']} | <strong>Makelaar:</strong> {off['makelaar']} | <strong>Prijs:</strong> €{off['vraagprijs'] or 'Onbekend'}</p>
            <p style="font-style:italic; font-size:14px;">"{off['opmerkingen']}"</p>
        </div>
    """, unsafe_allow_html=True)

# B. DATA METRICS
st.divider()
score_query = """
    SELECT p.*, a.*, sq_curr.name as "current_team_name"
    FROM public.players p
    LEFT JOIN analysis.final_impect_scores a ON p.id = a."playerId" AND CAST(a."iterationId" AS TEXT) = %s
    LEFT JOIN public.squads sq_curr ON p."currentSquadId" = sq_curr.id
    WHERE p.id = %s
"""
try:
    df_scores = run_query(score_query, params=(selected_iteration_id, str(final_player_id)))
    
    if not df_scores.empty:
        row = df_scores.iloc[0]
        st.subheader(f"ℹ️ {selected_player_name}")
        c1, c2, c3, c4 = st.columns(4)
        with c1: st.metric("Team", row['current_team_name'] or "Onbekend")
        with c2: st.metric("Geboortedatum", str(row.get('birthdate', '-')))
        with c3: st.metric("Geboorteplaats", row.get('birthplace', '-'))
        with c4: st.metric("Voet", row.get('leg', '-'))
        st.markdown("---")

        def highlight_score(val):
            return 'color: #2ecc71; font-weight: bold' if isinstance(val, (int, float)) and val > 66 else ''

        if pd.isna(row.get('position')):
            st.info("ℹ️ Geen berekende Impect-scores beschikbaar (te weinig speelminuten).")
        else:
            profile_mapping = {
                "KVK Centrale Verdediger": row.get('cb_kvk_score'), "KVK Wingback": row.get('wb_kvk_score'),
                "KVK Verdedigende Mid.": row.get('dm_kvk_score'), "KVK Centrale Mid.": row.get('cm_kvk_score'),
                "KVK Aanvallende Mid.": row.get('acm_kvk_score'), "KVK Flank Aanvaller": row.get('fa_kvk_score'),
                "KVK Spits": row.get('fw_kvk_score'), "Voetballende CV": row.get('footballing_cb_kvk_score'),
                "Controlerende CV": row.get('controlling_cb_kvk_score'), "Verdedigende Back": row.get('defensive_wb_kvk_score'),
                "Aanvallende Back": row.get('offensive_wingback_kvk_score'), "Ballenafpakker (CVM)": row.get('ball_winning_dm_kvk_score'),
                "Spelmaker (CVM)": row.get('playmaker_dm_kvk_score'), "Box-to-Box (CM)": row.get('box_to_box_cm_kvk_score'),
                "Diepgaande '10'": row.get('deep_running_acm_kvk_score'), "Spelmakende '10'": row.get('playmaker_off_acm_kvk_score'),
                "Buitenspeler (Binnendoor)": row.get('fa_inside_kvk_score'), "Buitenspeler (Buitenom)": row.get('fa_wide_kvk_score'),
                "Targetman": row.get('fw_target_kvk_score'), "Lopende Spits": row.get('fw_running_kvk_score'), "Afmaker": row.get('fw_finisher_kvk_score')
            }
            df_chart = pd.DataFrame([{"Profiel": k, "Score": v} for k, v in profile_mapping.items() if v and v > 0])
            
            cl, cs = st.columns([1, 2])
            with cl:
                st.write(f"**Gedetecteerde Positie:** {row['position']}")
                st.dataframe(df_chart.style.map(highlight_score, subset=['Score']).format({'Score': '{:.1f}'}), use_container_width=True, hide_index=True)
            with cs:
                fig = px.line_polar(df_chart, r='Score', theta='Profiel', line_close=True, title='Spider Chart')
                fig.update_traces(fill='toself', line_color='#d71920')
                st.plotly_chart(fig, use_container_width=True)

            # KPIs
            st.subheader("📊 Impect Scores & KPIs")
            m_cfg = get_config_for_position(row['position'], POSITION_METRICS)
            k_cfg = get_config_for_position(row['position'], POSITION_KPIS)
            cm, ck = st.columns(2)
            with cm:
                st.write("**Metrieken**")
                ids = tuple(str(x) for x in (m_cfg.get('aan_bal', []) + m_cfg.get('zonder_bal', []))) if m_cfg else None
                if ids:
                    q_m = 'SELECT d.name as "Metriek", s.final_score_1_to_100 as "Score" FROM analysis.player_final_scores s JOIN public.player_score_definitions d ON CAST(s.metric_id AS TEXT) = d.id WHERE s."iterationId" = %s AND s."playerId" = %s AND s.metric_id IN %s ORDER BY s.final_score_1_to_100 DESC'
                    df_m = run_query(q_m, params=(selected_iteration_id, str(final_player_id), ids))
                    st.dataframe(df_m.style.map(highlight_score, subset=['Score']), use_container_width=True, hide_index=True)
            with ck:
                st.write("**KPIs**")
                ids_k = tuple(str(x) for x in (k_cfg.get('aan_bal', []) + k_cfg.get('zonder_bal', []))) if k_cfg else None
                if ids_k:
                    q_k = 'SELECT d.name as "KPI", s.final_score_1_to_100 as "Score" FROM analysis.kpis_final_scores s JOIN analysis.kpi_definitions d ON CAST(s.metric_id AS TEXT) = d.id WHERE s."iterationId" = %s AND s."playerId" = %s AND s.metric_id IN %s ORDER BY s.final_score_1_to_100 DESC'
                    df_k = run_query(q_k, params=(selected_iteration_id, str(final_player_id), ids_k))
                    st.dataframe(df_k.style.map(highlight_score, subset=['Score']), use_container_width=True, hide_index=True)

        # C. SKILLCORNER
        st.divider()
        st.subheader("💪 Fysieke Data (SkillCorner)")
        q_ph = 'SELECT total_matches, psv99_score as "Max Speed", timetosprint_score as "Accel", sprint_distance_full_all_score as "Sprint Dist" FROM analysis.player_physical_group_scores f JOIN public.players p ON CAST(f.player_id AS TEXT) = CAST(p."idMappings_2_skill_corner_0" AS TEXT) WHERE p.id = %s LIMIT 1'
        df_ph = run_query(q_ph, params=(str(final_player_id),))
        if not df_ph.empty:
            st.dataframe(df_ph, use_container_width=True, hide_index=True)

        # D. SCOUTING (INTERN)
        st.divider()
        st.subheader("🕵️ Scouting Rapporten (Intern)")
        q_sc = 'SELECT g.naam as "Scout", r.aangemaakt_op as "Datum", r.beoordeling as "Rating", r.advies as "Advies", r.rapport_tekst FROM scouting.rapporten r JOIN scouting.gebruikers g ON r.scout_id = g.id WHERE r.speler_id = %s ORDER BY r.aangemaakt_op DESC'
        df_sc = run_query(q_sc, params=(str(final_player_id),))
        if not df_sc.empty:
            ct, cp = st.columns([2, 1])
            with ct: st.dataframe(df_sc[['Datum', 'Scout', 'Rating', 'Advies']], use_container_width=True, hide_index=True)
            with cp:
                vc = df_sc['Advies'].value_counts().reset_index(); vc.columns=['Advies','Aantal']
                st.plotly_chart(px.pie(vc, values='Aantal', names='Advies', hole=0.4, color_discrete_sequence=['#d71920','#bdc3c7']), use_container_width=True)

        # E. DATA SCOUT (EXTERN)
        st.divider()
        st.subheader("📑 Data Scout Rapporten (Extern)")
        q_ext = 'SELECT m."scheduledDate" as "Datum", sq_h.name as "Thuis", sq_a.name as "Uit", r.label as "Verdict" FROM analysis.scouting_reports r JOIN public.matches m ON r."matchId" = m.id LEFT JOIN public.squads sq_h ON m."homeSquadId" = sq_h.id LEFT JOIN public.squads sq_a ON m."awaySquadId" = sq_a.id WHERE r."iterationId" = %s AND r."playerId" = %s ORDER BY m."scheduledDate" DESC'
        df_ext = run_query(q_ext, params=(selected_iteration_id, str(final_player_id)))
        if not df_ext.empty:
            st.dataframe(df_ext, use_container_width=True, hide_index=True)

        # F. INTELLIGENCE
        st.divider()
        st.subheader("🧠 Strategisch Dossier (Intelligence)")
        q_intel = "SELECT * FROM scouting.speler_intelligence WHERE speler_id = %s ORDER BY laatst_bijgewerkt DESC LIMIT 1"
        df_i = run_query(q_intel, params=(str(final_player_id),))
        if not df_i.empty:
            ir = df_i.iloc[0]
            l1, l2 = st.columns(2)
            with l1: 
                if ir.get('instagram_url'): st.link_button("📸 Instagram", ir['instagram_url'], use_container_width=True)
            with l2: 
                if ir.get('transfermarkt_url'): st.link_button("⚽ Transfermarkt", ir['transfermarkt_url'], use_container_width=True)
            cia, cib = st.columns(2)
            with cia:
                st.info(f"**Club/Netwerk:**\n{ir['club_informatie']}")
                st.info(f"**Familie:**\n{ir['familie_achtergrond']}")
            with cib:
                st.warning(f"**Mentaliteit:**\n{ir['persoonlijkheid']}")
                st.error(f"**Makelaar:**\n{ir['makelaar_details']}")

        # G. SIMILARITY
        st.divider()
        st.subheader("👯 Vergelijkbare Spelers")
        if not pd.isna(row.get('position')):
            rev = { "KVK Centrale Verdediger": 'cb_kvk_score', "KVK Wingback": 'wb_kvk_score', "KVK Verdedigende Mid.": 'dm_kvk_score', "KVK Centrale Mid.": 'cm_kvk_score', "KVK Aanvallende Mid.": 'acm_kvk_score', "KVK Flank Aanvaller": 'fa_kvk_score', "KVK Spits": 'fw_kvk_score', "Voetballende CV": 'footballing_cb_kvk_score', "Controlerende CV": 'controlling_cb_kvk_score', "Verdedigende Back": 'defensive_wb_kvk_score', "Aanvallende Back": 'offensive_wingback_kvk_score', "Ballenafpakker (CVM)": 'ball_winning_dm_kvk_score', "Spelmaker (CVM)": 'playmaker_dm_kvk_score', "Box-to-Box (CM)": 'box_to_box_cm_kvk_score', "Diepgaande '10'": 'deep_running_acm_kvk_score', "Spelmakende '10'": 'playmaker_off_acm_kvk_score', "Buitenspeler (Binnendoor)": 'fa_inside_kvk_score', "Buitenspeler (Buitenom)": 'fa_wide_kvk_score', "Targetman": 'fw_target_kvk_score', "Lopende Spits": 'fw_running_kvk_score', "Afmaker": 'fw_finisher_kvk_score' }
            db_cols = [rev[c] for c in profile_mapping.keys() if profile_mapping[c] and profile_mapping[c] > 0]
            if db_cols:
                with st.expander("Top 10 vergelijkbaar"):
                    c_str = ", ".join([f'a."{c}"' for c in db_cols])
                    q_s = f'SELECT p.commonname as "Naam", sq.name as "Team", i.season as "S", i."competitionName" as "C", {c_str} FROM analysis.final_impect_scores a JOIN public.players p ON CAST(a."playerId" AS TEXT) = p.id LEFT JOIN public.squads sq ON CAST(a."squadId" AS TEXT) = sq.id JOIN public.iterations i ON CAST(a."iterationId" AS TEXT) = CAST(i.id AS TEXT) WHERE a.position = %s AND i.season IN (\'25/26\', \'2025\')'
                    df_s = run_query(q_s, params=(row['position'],))
                    if not df_s.empty:
                        t_vec = df_s[df_s['Naam'] == selected_player_name].iloc[0][db_cols]
                        df_s['Gelijkenis %'] = (100 - (df_s[db_cols] - t_vec).abs().mean(axis=1))
                        res = df_s[df_s['Naam'] != selected_player_name].sort_values('Gelijkenis %', ascending=False).head(10)
                        st.dataframe(res[['Naam', 'Team', 'S', 'C', 'Gelijkenis %']].style.format({'Gelijkenis %': '{:.1f}%'}), use_container_width=True, hide_index=True)

except Exception as e: 
    st.error(f"Fout: {e}")
