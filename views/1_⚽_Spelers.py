import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np
from utils import run_query, get_config_for_position, POSITION_METRICS, POSITION_KPIS

st.set_page_config(page_title="Speler Analyse", page_icon="⚽", layout="wide")

# -----------------------------------------------------------------------------
# 0. NAVIGATIE LOGICA (Redirect afhandeling)
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
else: selected_competition = None

selected_iteration_id = None
if selected_season and selected_competition:
    df_details = run_query('SELECT season, "competitionName", id FROM public.iterations WHERE season = %s AND "competitionName" = %s LIMIT 1;', params=(selected_season, selected_competition))
    if not df_details.empty:
        selected_iteration_id = str(df_details.iloc[0]['id'])
    else: st.error("Kon geen ID vinden."); st.stop() 
else: st.warning("👈 Kies eerst een seizoen en competitie."); st.stop() 

# -----------------------------------------------------------------------------
# 2. SPELER SELECTIE (RUWE BRON: player_kpis voor 100% dekking)
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
    idx_p = unique_names.index(st.session_state.sb_player) if "sb_player" in st.session_state and st.session_state.sb_player in unique_names else 0
    selected_player_name = st.sidebar.selectbox("Kies een speler:", unique_names, index=idx_p, key="sb_player")
    
    candidate_rows = df_players[df_players['commonname'] == selected_player_name]
    final_player_id = None
    if len(candidate_rows) > 1:
        squad_options = [s for s in candidate_rows['squadName'].tolist() if s is not None]
        selected_squad = st.sidebar.selectbox("Kies team:", squad_options)
        final_player_id = candidate_rows[candidate_rows['squadName'] == selected_squad].iloc[0]['playerId']
    else: final_player_id = candidate_rows.iloc[0]['playerId']
except Exception as e: st.error(f"Fout spelers: {e}"); st.stop()

# -----------------------------------------------------------------------------
# 3. ANALYSE WEERGAVE
# -----------------------------------------------------------------------------
st.title("🏃‍♂️ Speler Analyse")

# A. TRANSFER STATUS
check_offer_q = "SELECT status, makelaar, vraagprijs, opmerkingen FROM scouting.offered_players WHERE player_id = %s ORDER BY aangeboden_datum DESC LIMIT 1"
df_offer = run_query(check_offer_q, params=(str(final_player_id),))

if not df_offer.empty:
    off = df_offer.iloc[0]
    status_color = "#27ae60" if off['status'] == 'Interessant' else "#c0392b" if off['status'] == 'Afgekeurd' else "#f39c12"
    price_display = f"€ {off['vraagprijs']:,.0f}" if off['vraagprijs'] else "Onbekend"
    st.markdown(f"""<div style="padding: 15px; background-color: {status_color}15; border: 2px solid {status_color}; border-radius: 8px; margin-bottom: 25px;"><h4 style="color: {status_color}; margin:0;">📥 Aangeboden Speler</h4><p style="margin: 5px 0 0 0; font-size: 16px;"><strong>Status:</strong> {off['status']} &nbsp;|&nbsp; <strong>Makelaar:</strong> {off['makelaar']} &nbsp;|&nbsp; <strong>Vraagprijs:</strong> {price_display}</p><p style="margin: 5px 0 0 0; font-style: italic; font-size: 14px; color: #555;">"{off['opmerkingen']}"</p></div>""", unsafe_allow_html=True)

# B. DATA METRICS
st.divider()
score_query = """
    SELECT p.commonname, a.position, p.birthdate, p.birthplace, p.leg, sq_curr.name as "current_team_name",
        a.cb_kvk_score, a.wb_kvk_score, a.dm_kvk_score, a.cm_kvk_score, a.acm_kvk_score, a.fa_kvk_score, a.fw_kvk_score,
        a.footballing_cb_kvk_score, a.controlling_cb_kvk_score, a.defensive_wb_kvk_score, a.offensive_wingback_kvk_score,
        a.ball_winning_dm_kvk_score, a.playmaker_dm_kvk_score, a.box_to_box_cm_kvk_score, a.deep_running_acm_kvk_score,
        a.playmaker_off_acm_kvk_score, a.fa_inside_kvk_score, a.fa_wide_kvk_score, a.fw_target_kvk_score,
        a.fw_running_kvk_score, a.fw_finisher_kvk_score
    FROM public.players p
    LEFT JOIN analysis.final_impect_scores a ON p.id = a."playerId" AND CAST(a."iterationId" AS TEXT) = %s
    LEFT JOIN public.squads sq_curr ON p."currentSquadId" = sq_curr.id
    WHERE p.id = %s
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
        st.markdown("---")

        def highlight_high_scores(val):
            return 'color: #2ecc71; font-weight: bold' if isinstance(val, (int, float)) and val > 66 else ''

        if pd.isna(row['position']):
            st.info("ℹ️ Deze speler heeft nog geen berekende Impect-scores (mogelijk te weinig speelminuten).")
        else:
            profile_mapping = {
                "KVK Centrale Verdediger": row['cb_kvk_score'], "KVK Wingback": row['wb_kvk_score'],
                "KVK Verdedigende Mid.": row['dm_kvk_score'], "KVK Centrale Mid.": row['cm_kvk_score'],
                "KVK Aanvallende Mid.": row['acm_kvk_score'], "KVK Flank Aanvaller": row['fa_kvk_score'],
                "KVK Spits": row['fw_kvk_score'], "Voetballende CV": row['footballing_cb_kvk_score'],
                "Controlerende CV": row['controlling_cb_kvk_score'], "Verdedigende Back": row['defensive_wb_kvk_score'],
                "Aanvallende Back": row['offensive_wingback_kvk_score'], "Ballenafpakker (CVM)": row['ball_winning_dm_kvk_score'],
                "Spelmaker (CVM)": row['playmaker_dm_kvk_score'], "Box-to-Box (CM)": row['box_to_box_cm_kvk_score'],
                "Diepgaande '10'": row['deep_running_acm_kvk_score'], "Spelmakende '10'": row['playmaker_off_acm_kvk_score'],
                "Buitenspeler (Binnendoor)": row['fa_inside_kvk_score'], "Buitenspeler (Buitenom)": row['fa_wide_kvk_score'],
                "Targetman": row['fw_target_kvk_score'], "Lopende Spits": row['fw_running_kvk_score'], "Afmaker": row['fw_finisher_kvk_score']
            }
            active_profiles = {k: v for k, v in profile_mapping.items() if v is not None and v > 0}
            df_chart = pd.DataFrame(list(active_profiles.items()), columns=['Profiel', 'Score'])
            
            top_profile_name = df_chart.sort_values(by='Score', ascending=False).iloc[0]['Profiel'] if not df_chart.empty and df_chart.sort_values(by='Score', ascending=False).iloc[0]['Score'] > 66 else None
            if top_profile_name: st.success(f"### ✅ Speler is POSITIEF op data profiel: {top_profile_name}")
            
            cl, cs = st.columns([1, 2])
            with cl:
                st.write(f"**Positie:** {row['position']}")
                st.dataframe(df_chart.style.applymap(highlight_high_scores, subset=['Score']).format({'Score': '{:.1f}'}), use_container_width=True, hide_index=True)
            with cs:
                fig = px.line_polar(df_chart, r='Score', theta='Profiel', line_close=True, title='KVK Profiel Spider Chart')
                fig.update_traces(fill='toself', line_color='#d71920', marker=dict(size=8))
                fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 100])))
                st.plotly_chart(fig, use_container_width=True)

            st.markdown("---"); st.subheader("📊 Impect Scores & KPIs")
            m_cfg = get_config_for_position(row['position'], POSITION_METRICS)
            k_cfg = get_config_for_position(row['position'], POSITION_KPIS)
            cm, ck = st.columns(2)
            with cm:
                st.write("**Metrieken**")
                if m_cfg:
                    ids = tuple(str(x) for x in (m_cfg.get('aan_bal', []) + m_cfg.get('zonder_bal', [])))
                    if ids:
                        q_m = 'SELECT d.name as "Metriek", d.details_label as "Detail", s.final_score_1_to_100 as "Score" FROM analysis.player_final_scores s JOIN public.player_score_definitions d ON CAST(s.metric_id AS TEXT) = d.id WHERE s."iterationId" = %s AND s."playerId" = %s AND s.metric_id IN %s ORDER BY s.final_score_1_to_100 DESC'
                        df_m = run_query(q_m, params=(selected_iteration_id, p_player_id, ids))
                        st.dataframe(df_m.style.applymap(highlight_high_scores, subset=['Score']), use_container_width=True, hide_index=True)
            with ck:
                st.write("**KPIs**")
                if k_cfg:
                    ids_k = tuple(str(x) for x in (k_cfg.get('aan_bal', []) + k_cfg.get('zonder_bal', [])))
                    if ids_k:
                        q_k = 'SELECT d.name as "KPI", d.context as "Context", s.final_score_1_to_100 as "Score" FROM analysis.kpis_final_scores s JOIN analysis.kpi_definitions d ON CAST(s.metric_id AS TEXT) = d.id WHERE s."iterationId" = %s AND s."playerId" = %s AND s.metric_id IN %s ORDER BY s.final_score_1_to_100 DESC'
                        df_k = run_query(q_k, params=(selected_iteration_id, p_player_id, ids_k))
                        st.dataframe(df_k.style.applymap(highlight_high_scores, subset=['Score']), use_container_width=True, hide_index=True)

        # C. SKILLCORNER (Fysiek met kleuren A/B/C)
        st.divider()
        st.subheader("💪 Fysieke Data (SkillCorner)")
        q_ph = """SELECT f.total_matches, f.psv99_score as "PSV 99", f.timetosprint_score as "TTS", f.sprint_distance_full_all_score as "Sprint Dis", f.sprint_count_full_all_score as "Sprint Cnt", f.total_distance_full_all_score as "Tot. Dis", f.* FROM analysis.player_physical_group_scores f JOIN public.players p ON CAST(f.player_id AS TEXT) = CAST(p."idMappings_2_skill_corner_0" AS TEXT) WHERE p.id = %s LIMIT 1"""
        try:
            df_ph = run_query(q_ph, params=(p_player_id,))
            if not df_ph.empty:
                df_ph = df_ph.loc[:, ~df_ph.columns.duplicated()]
                def color_ph(val):
                    v = str(val).strip().upper()
                    if v == 'A': return 'color: #2ecc71; font-weight: bold' 
                    if v == 'B': return 'color: #f1c40f; font-weight: bold' 
                    if v == 'C': return 'color: #e74c3c; font-weight: bold' 
                    return ''
                main_c = ["total_matches", "PSV 99", "TTS", "Sprint Dis", "Sprint Cnt", "Tot. Dis"]
                st.dataframe(df_ph[main_c].style.applymap(color_ph), use_container_width=True, hide_index=True)
                with st.expander("📊 Toon ALLE fysieke scores"):
                    st.dataframe(df_ph[[c for c in df_ph.columns if c.endswith('_score')]].style.applymap(color_ph), use_container_width=True, hide_index=True)
            else: st.info("Geen fysieke data gekoppeld.")
        except Exception as e: st.error(f"Fysiek fout: {e}")

        # D. INTERNE SCOUTING (Met Pie Chart)
        st.divider()
        st.subheader("🕵️ Scouting Rapporten (Intern)")
        q_sc = 'SELECT s.naam as "Scout", r.aangemaakt_op as "Datum", r.positie_gespeeld as "Positie", r.profiel_code as "Profiel", r.beoordeling as "Rating", r.advies as "Advies", r.rapport_tekst, r.gouden_buzzer FROM scouting.rapporten r LEFT JOIN scouting.gebruikers s ON r.scout_id = s.id WHERE r.speler_id = %s ORDER BY r.aangemaakt_op DESC'
        df_sc = run_query(q_sc, params=(p_player_id,))
        if not df_sc.empty:
            c_sc1, c_sc2 = st.columns([2, 1])
            with c_sc1:
                df_disp = df_sc.copy()
                df_disp['Datum'] = pd.to_datetime(df_disp['Datum']).dt.strftime('%d-%m-%Y')
                st.dataframe(df_disp[["Datum", "Scout", "Positie", "Profiel", "Rating", "Advies"]], use_container_width=True, hide_index=True)
            with c_sc2:
                if df_sc['Advies'].notna().any():
                    vc = df_sc['Advies'].value_counts().reset_index(); vc.columns=['Advies','Aantal']
                    st.plotly_chart(px.pie(vc, values='Aantal', names='Advies', hole=0.4, color_discrete_sequence=['#d71920', '#bdc3c7', '#ecf0f1']), use_container_width=True)
            with st.expander("📖 Lees volledige rapport teksten"):
                for _, r in df_sc.iterrows():
                    st.markdown(f"**{'🏆' if r['gouden_buzzer'] else '📝'} {pd.to_datetime(r['Datum']).strftime('%d-%m-%Y')} - {r['Scout']}**")
                    st.info(r['rapport_tekst'] or "Geen tekst.")
        else: st.info("Geen interne rapporten.")

        # E. EXTERNE DATA RAPPORTEN (Met Pie Chart)
        st.divider()
        st.subheader("📑 Data Scout Rapporten (Extern)")
        q_ext = 'SELECT m."scheduledDate" as "Datum", sq_h.name as "Thuis", sq_a.name as "Uit", r.label as "Verdict" FROM analysis.scouting_reports r JOIN public.matches m ON r."matchId" = m.id LEFT JOIN public.squads sq_h ON m."homeSquadId" = sq_h.id LEFT JOIN public.squads sq_a ON m."awaySquadId" = sq_a.id WHERE r."iterationId" = %s AND r."playerId" = %s ORDER BY m."scheduledDate" DESC'
        df_ex = run_query(q_ext, params=(selected_iteration_id, p_player_id))
        if not df_ex.empty:
            ce1, ce2 = st.columns([2, 1])
            with ce1: st.dataframe(df_ex, use_container_width=True, hide_index=True)
            with ce2:
                vc_e = df_ex['Verdict'].value_counts().reset_index(); vc_e.columns=['Verdict','Aantal']
                st.plotly_chart(px.pie(vc_e, values='Aantal', names='Verdict', hole=0.4, color_discrete_sequence=['#d71920', '#bdc3c7']), use_container_width=True)
        else: st.info("Geen externe rapporten.")

        # F. STRATEGISCH DOSSIER (INTELLIGENCE) - Gecorrigeerde variabelen
        st.divider()
        st.subheader("🧠 Strategisch Dossier (Intelligence)")
        q_intel = "SELECT * FROM scouting.speler_intelligence WHERE speler_id = %s ORDER BY laatst_bijgewerkt DESC LIMIT 1"
        df_intel = run_query(q_intel, params=(p_player_id,))
        if not df_intel.empty:
            intel = df_intel.iloc[0]
            st.caption(f"Update: {pd.to_datetime(intel['laatst_bijgewerkt']).strftime('%d-%m-%Y')} door {intel['toegevoegd_door']}")
            l1, l2, l3 = st.columns(3)
            with l1: 
                if intel.get('instagram_url'): st.link_button("📸 Instagram", intel['instagram_url'], use_container_width=True)
            with l2: 
                if intel.get('transfermarkt_url'): st.link_button("⚽ Transfermarkt", intel['transfermarkt_url'], use_container_width=True)
            with l3:
                if intel.get('twitter_url'): st.link_button("🐦 Twitter / X", intel['twitter_url'], use_container_width=True)
            ci1, ci2 = st.columns(2)
            with ci1:
                st.info(f"**Club & Netwerk:**\n\n{intel.get('club_informatie') or '-'}")
                st.info(f"**Familie & Achtergrond:**\n\n{intel.get('familie_achtergrond') or '-'}")
            with ci2:
                st.warning(f"**Persoonlijkheid:**\n\n{intel.get('persoonlijkheid') or '-'}")
                st.error(f"**Makelaar & Contract:**\n\n{intel.get('makelaar_details') or '-'}")
        else: st.info("Geen dossier gevonden.")

        # G. SIMILARITY (Met klikbare selectie)
        st.divider()
        st.subheader("👯 Vergelijkbare Spelers")
        if not pd.isna(row['position']):
            rev_map = { "KVK Centrale Verdediger": 'cb_kvk_score', "KVK Wingback": 'wb_kvk_score', "KVK Verdedigende Mid.": 'dm_kvk_score', "KVK Centrale Mid.": 'cm_kvk_score', "KVK Aanvallende Mid.": 'acm_kvk_score', "KVK Flank Aanvaller": 'fa_kvk_score', "KVK Spits": 'fw_kvk_score', "Voetballende CV": 'footballing_cb_kvk_score', "Controlerende CV": 'controlling_cb_kvk_score', "Verdedigende Back": 'defensive_wb_kvk_score', "Aanvallende Back": 'offensive_wingback_kvk_score', "Ballenafpakker (CVM)": 'ball_winning_dm_kvk_score', "Spelmaker (CVM)": 'playmaker_dm_kvk_score', "Box-to-Box (CM)": 'box_to_box_cm_kvk_score', "Diepgaande '10'": 'deep_running_acm_kvk_score', "Spelmakende '10'": 'playmaker_off_acm_kvk_score', "Buitenspeler (Binnendoor)": 'fa_inside_kvk_score', "Buitenspeler (Buitenom)": 'fa_wide_kvk_score', "Targetman": 'fw_target_kvk_score', "Lopende Spits": 'fw_running_kvk_score', "Afmaker": 'fw_finisher_kvk_score' }
            db_cols = [rev_map[c] for c in profile_mapping.keys() if profile_mapping[c] and profile_mapping[c] > 0]
            if db_cols:
                with st.expander(f"Top 10 vergelijkbaar met {selected_player_name}"):
                    c_str = ", ".join([f'a."{c}"' for c in db_cols])
                    q_sim = f'SELECT p.id as "playerId", p.commonname as "Naam", sq.name as "Team", i.season as "S", i."competitionName" as "C", a.position, {c_str} FROM analysis.final_impect_scores a JOIN public.players p ON CAST(a."playerId" AS TEXT) = p.id LEFT JOIN public.squads sq ON CAST(a."squadId" AS TEXT) = sq.id JOIN public.iterations i ON CAST(a."iterationId" AS TEXT) = CAST(i.id AS TEXT) WHERE a.position = %s AND i.season IN (\'25/26\', \'2025\')'
                    df_s = run_query(q_sim, params=(row['position'],))
                    if not df_s.empty:
                        df_s['uid'] = df_s['playerId'].astype(str) + "_" + df_s['S']
                        df_s = df_s.drop_duplicates(subset=['uid']).set_index('uid')
                        cur_uid = f"{p_player_id}_{selected_season}"
                        if cur_uid in df_s.index:
                            target_vec = df_s.loc[cur_uid, db_cols]
                            sim = (100 - (df_s[db_cols] - target_vec).abs().mean(axis=1)).sort_values(ascending=False).drop(cur_uid, errors='ignore').head(10)
                            res = df_s.loc[sim.index].copy(); res['Gelijkenis %'] = sim
                            def col_sim(v): return f"color: {'#2ecc71' if v > 90 else '#27ae60' if v > 80 else 'black'}; font-weight: bold"
                            event = st.dataframe(res[['Naam', 'Team', 'S', 'C', 'Gelijkenis %']].style.applymap(col_sim, subset=['Gelijkenis %']).format({'Gelijkenis %': '{:.1f}%'}), use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")
                            if event and len(event.selection.rows) > 0:
                                sel_r = res.iloc[event.selection.rows[0]]
                                st.session_state.pending_nav = {"season": sel_r['S'], "competition": sel_r['C'], "target_name": sel_r['Naam'], "mode": "Spelers"}
                                st.rerun()

except Exception as e: st.error(f"Fout in analyse: {e}")
