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

# CAST toegevoegd om de 'integer = text' error definitief te voorkomen
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
    
    candidate_rows = df_players[df_players['commonname'] == selected_player_name]
    final_player_id = None
    
    if len(candidate_rows) > 1:
        st.sidebar.warning(f"⚠️ Meerdere spelers: '{selected_player_name}'.")
        squad_options = [s for s in candidate_rows['squadName'].tolist() if s is not None]
        selected_squad = st.sidebar.selectbox("Kies team:", squad_options)
        final_player_id = candidate_rows[candidate_rows['squadName'] == selected_squad].iloc[0]['playerId']
    elif len(candidate_rows) == 1: 
        final_player_id = candidate_rows.iloc[0]['playerId']
    else: st.error("Selectie fout."); st.stop()
except Exception as e: st.error("Fout bij ophalen spelers."); st.code(e); st.stop()

# -----------------------------------------------------------------------------
# 3. DASHBOARD
# -----------------------------------------------------------------------------
st.title("🏃‍♂️ Speler Analyse")

# A. TRANSFER STATUS
check_offer_q = "SELECT status, makelaar, vraagprijs, opmerkingen FROM scouting.offered_players WHERE player_id = %s ORDER BY aangeboden_datum DESC LIMIT 1"
df_offer = run_query(check_offer_q, params=(str(final_player_id),))

if not df_offer.empty:
    offer_row = df_offer.iloc[0]
    status_color = "#f39c12" 
    if offer_row['status'] == 'Interessant': status_color = "#27ae60" 
    if offer_row['status'] == 'Afgekeurd': status_color = "#c0392b" 
    price_display = f"€ {offer_row['vraagprijs']:,.0f}" if offer_row['vraagprijs'] else "Onbekend"
    st.markdown(f'<div style="padding: 15px; background-color: {status_color}15; border: 2px solid {status_color}; border-radius: 8px; margin-bottom: 25px;"><h4 style="color: {status_color}; margin:0;">📥 Aangeboden Speler</h4><p style="margin: 5px 0;"><strong>Status:</strong> {offer_row["status"]} | <strong>Makelaar:</strong> {offer_row["makelaar"]} | <strong>Vraagprijs:</strong> {price_display}</p><p style="margin: 5px 0; font-style: italic; font-size: 14px; color: #555;">"{offer_row["opmerkingen"]}"</p></div>', unsafe_allow_html=True)

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
            
            top_profile_name = df_chart.sort_values(by='Score', ascending=False).iloc[0]['Profiel'] if not df_chart.empty and df_chart.iloc[0]['Score'] > 66 else None
            if top_profile_name: st.success(f"### ✅ Speler is POSITIEF op data profiel: {top_profile_name}")
            
            c_l, c_s = st.columns([1, 2])
            with c_l:
                st.write(f"**Positie:** {row['position']}")
                st.dataframe(df_chart.style.applymap(highlight_high_scores, subset=['Score']).format({'Score': '{:.1f}'}), use_container_width=True, hide_index=True)
            with c_s:
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
                    def get_met_tab(m_ids):
                        if not m_ids: return pd.DataFrame()
                        ids = tuple(str(x) for x in m_ids)
                        q = 'SELECT d.name as "Metriek", d.details_label as "Detail", s.final_score_1_to_100 as "Score" FROM analysis.player_final_scores s JOIN public.player_score_definitions d ON CAST(s.metric_id AS TEXT) = d.id WHERE s."iterationId" = %s AND s."playerId" = %s AND s.metric_id IN %s ORDER BY s.final_score_1_to_100 DESC'
                        return run_query(q, params=(selected_iteration_id, p_player_id, ids))
                    d_a = get_met_tab(m_cfg.get('aan_bal', []))
                    d_z = get_met_tab(m_cfg.get('zonder_bal', []))
                    if not d_a.empty: st.caption("Aan de Bal"); st.dataframe(d_a.style.applymap(highlight_high_scores, subset=['Score']), use_container_width=True, hide_index=True)
                    if not d_z.empty: st.caption("Zonder Bal"); st.dataframe(d_z.style.applymap(highlight_high_scores, subset=['Score']), use_container_width=True, hide_index=True)

            with ck:
                st.write("**KPIs**")
                if k_cfg:
                    def get_kpi_tab(k_ids):
                        if not k_ids: return pd.DataFrame()
                        ids = tuple(str(x) for x in k_ids)
                        q = 'SELECT d.name as "KPI", d.context as "Context", s.final_score_1_to_100 as "Score" FROM analysis.kpis_final_scores s JOIN analysis.kpi_definitions d ON CAST(s.metric_id AS TEXT) = d.id WHERE s."iterationId" = %s AND s."playerId" = %s AND s.metric_id IN %s ORDER BY s.final_score_1_to_100 DESC'
                        return run_query(q, params=(selected_iteration_id, p_player_id, ids))
                    dk1 = get_kpi_tab(k_cfg.get('aan_bal', []))
                    dk2 = get_kpi_tab(k_cfg.get('zonder_bal', []))
                    if not dk1.empty: st.caption("Aan de Bal"); st.dataframe(dk1.style.applymap(highlight_high_scores, subset=['Score']), use_container_width=True, hide_index=True)
                    if not dk2.empty: st.caption("Zonder Bal"); st.dataframe(dk2.style.applymap(highlight_high_scores, subset=['Score']), use_container_width=True, hide_index=True)

        # C. FYSIEK (Met Originele Kleuren A/B/C)
        st.divider()
        st.subheader("💪 Fysieke Data (SkillCorner)")
        q_ph = 'SELECT total_matches, psv99_score as "PSV 99", timetosprint_score as "TTS", sprint_distance_full_all_score as "Sprint Dis", sprint_count_full_all_score as "Sprint Cnt", total_distance_full_all_score as "Tot. Dis", f.* FROM analysis.player_physical_group_scores f JOIN public.players p ON CAST(f.player_id AS TEXT) = CAST(p."idMappings_2_skill_corner_0" AS TEXT) WHERE p.id = %s LIMIT 1'
        try:
            df_ph = run_query(q_ph, params=(str(final_player_id),))
            if not df_ph.empty:
                df_ph = df_ph.loc[:, ~df_ph.columns.duplicated()]
                def color_ph(val):
                    val_s = str(val).strip().upper()
                    if val_s == 'A': return 'color: #2ecc71; font-weight: bold' 
                    if val_s == 'B': return 'color: #f1c40f; font-weight: bold' 
                    if val_s == 'C': return 'color: #e74c3c; font-weight: bold' 
                    return ''
                main_c = ["total_matches", "PSV 99", "TTS", "Sprint Dis", "Sprint Cnt", "Tot. Dis"]
                st.dataframe(df_ph[main_c].style.applymap(color_ph), use_container_width=True, hide_index=True)
                with st.expander("📊 Toon ALLE fysieke scores"):
                    s_cols = [c for c in df_ph.columns if c.endswith('_score')]
                    st.dataframe(df_ph[s_cols].style.applymap(color_ph), use_container_width=True, hide_index=True)
            else: st.info("Geen fysieke data gekoppeld.")
        except: pass

        # D. SCOUTING (Met Pie Chart)
        st.divider()
        st.subheader("🕵️ Scouting Rapporten (Intern)")
        q_sc = 'SELECT s.naam as "Scout", r.aangemaakt_op as "Datum", r.positie_gespeeld as "Positie", r.profiel_code as "Profiel", r.beoordeling as "Rating", r.advies as "Advies", r.rapport_tekst, r.gouden_buzzer FROM scouting.rapporten r LEFT JOIN scouting.gebruikers s ON r.scout_id = s.id WHERE r.speler_id = %s ORDER BY r.aangemaakt_op DESC'
        df_sc = run_query(q_sc, params=(str(final_player_id),))
        if not df_sc.empty:
            sc1, sc2 = st.columns([2, 1])
            with sc1:
                df_d = df_sc.copy()
                df_d['Datum'] = pd.to_datetime(df_d['Datum']).dt.strftime('%d-%m-%Y')
                st.dataframe(df_d[["Datum", "Scout", "Positie", "Profiel", "Rating", "Advies"]], use_container_width=True, hide_index=True)
            with sc2:
                if df_sc['Advies'].notna().any():
                    vc = df_sc['Advies'].value_counts().reset_index(); vc.columns=['Advies','Aantal']
                    st.plotly_chart(px.pie(vc, values='Aantal', names='Advies', hole=0.4, color_discrete_sequence=['#d71920', '#bdc3c7', '#ecf0f1']), use_container_width=True)
            with st.expander("📖 Lees teksten"):
                for _, r_i in df_sc.iterrows():
                    ic = "🏆" if r_i['gouden_buzzer'] else "📝"
                    st.markdown(f"**{ic} {r_i['Datum']} - {r_i['Scout']}**"); st.info(r_i['rapport_tekst'] or "Geen tekst.")
        else: st.info("Geen rapporten.")

        # E. EXTERNE RAPPORTEN (Met Pie Chart)
        st.divider()
        st.subheader("📑 Data Scout Rapporten (Extern)")
        q_ex = 'SELECT m."scheduledDate" as "Datum", sq_h.name as "Thuis", sq_a.name as "Uit", r.label as "Verdict" FROM analysis.scouting_reports r JOIN public.matches m ON r."matchId" = m.id LEFT JOIN public.squads sq_h ON m."homeSquadId" = sq_h.id LEFT JOIN public.squads sq_a ON m."awaySquadId" = sq_a.id WHERE r."iterationId" = %s AND r."playerId" = %s ORDER BY m."scheduledDate" DESC'
        df_ex = run_query(q_ex, params=(selected_iteration_id, p_player_id))
        if not df_ex.empty:
            ex1, ex2 = st.columns([2, 1])
            with ex1: st.dataframe(df_ex, use_container_width=True, hide_index=True)
            with ex2:
                vc_e = df_ex['Verdict'].value_counts().reset_index(); vc_e.columns=['Verdict','Aantal']
                st.plotly_chart(px.pie(vc_e, values='Aantal', names='Verdict', hole=0.4, color_discrete_sequence=['#d71920', '#bdc3c7']), use_container_width=True)

        # F. INTELLIGENCE (Jouw Nieuwe Dossier)
        st.divider()
        st.subheader("🧠 Strategisch Dossier (Intelligence)")
        q_i = 'SELECT * FROM scouting.speler_intelligence WHERE speler_id = %s ORDER BY laatst_bijgewerkt DESC LIMIT 1'
        df_i = run_query(q_i, params=(str(final_player_id),))
        if not df_i.empty:
            i_r = df_i.iloc[0]
            st.caption(f"Update: {pd.to_datetime(i_r['laatst_bijgewerkt']).strftime('%d-%m-%Y')} door {i_r['toegevoegd_door']}")
            l1, l2, l3 = st.columns(3)
            with l1: 
                if i_r.get('instagram_url'): st.link_button("📸 Instagram", i_r['instagram_url'], use_container_width=True)
            with l2: 
                if i_r.get('transfermarkt_url'): st.link_button("⚽ Transfermarkt", i_r['transfermarkt_url'], use_container_width=True)
            i1, i2 = st.columns(2)
            with i1:
                st.info(f"**Club/Netwerk:**\n{i_r['club_informatie'] or '-'}")
                st.info(f"**Familie:**\n{i_r['familie_achtergrond'] or '-'}")
            with i2:
                st.warning(f"**Mentaliteit:**\n{i_r['persoonlijkheid'] or '-'}")
                st.error(f"**Makelaar:**\n{i_row['makelaar_details'] or '-' if 'makelaar_details' in i_r else i_r['makelaar_details']}")
        else: st.info("Geen dossier gevonden.")

        # G. SIMILARITY (Met Klikbare Redirect)
        st.divider()
        st.subheader("👯 Vergelijkbare Spelers")
        if not pd.isna(row['position']):
            rev = { "KVK Centrale Verdediger": 'cb_kvk_score', "KVK Wingback": 'wb_kvk_score', "KVK Verdedigende Mid.": 'dm_kvk_score', "KVK Centrale Mid.": 'cm_kvk_score', "KVK Aanvallende Mid.": 'acm_kvk_score', "KVK Flank Aanvaller": 'fa_kvk_score', "KVK Spits": 'fw_kvk_score', "Voetballende CV": 'footballing_cb_kvk_score', "Controlerende CV": 'controlling_cb_kvk_score', "Verdedigende Back": 'defensive_wb_kvk_score', "Aanvallende Back": 'offensive_wingback_kvk_score', "Ballenafpakker (CVM)": 'ball_winning_dm_kvk_score', "Spelmaker (CVM)": 'playmaker_dm_kvk_score', "Box-to-Box (CM)": 'box_to_box_cm_kvk_score', "Diepgaande '10'": 'deep_running_acm_kvk_score', "Spelmakende '10'": 'playmaker_off_acm_kvk_score', "Buitenspeler (Binnendoor)": 'fa_inside_kvk_score', "Buitenspeler (Buitenom)": 'fa_wide_kvk_score', "Targetman": 'fw_target_kvk_score', "Lopende Spits": 'fw_running_kvk_score', "Afmaker": 'fw_finisher_kvk_score' }
            db_c = [rev[c] for c in profile_mapping.keys() if profile_mapping[c] and profile_mapping[c] > 0]
            if db_c:
                with st.expander(f"Vergelijkbaar met {selected_player_name}"):
                    c_s = ", ".join([f'a."{c}"' for c in db_c])
                    q_s = f'SELECT p.id as "playerId", p.commonname as "Naam", sq.name as "Team", i.season as "Seizoen", i."competitionName" as "Competitie", a.position, {c_s} FROM analysis.final_impect_scores a JOIN public.players p ON CAST(a."playerId" AS TEXT) = p.id LEFT JOIN public.squads sq ON CAST(a."squadId" AS TEXT) = sq.id JOIN public.iterations i ON CAST(a."iterationId" AS TEXT) = CAST(i.id AS TEXT) WHERE a.position = %s AND i.season IN (\'25/26\', \'2025\')'
                    df_s = run_query(q_s, params=(row['position'],))
                    if not df_s.empty:
                        df_s['uid'] = df_s['playerId'].astype(str) + "_" + df_s['Seizoen']
                        df_s = df_s.drop_duplicates(subset=['uid']).set_index('uid')
                        cur_id = f"{p_player_id}_{selected_season}"
                        if cur_id in df_s.index:
                            t_v = df_s.loc[cur_id, db_c]; t_a = t_v.mean()
                            o_a = df_s[db_c].mean(axis=1)
                            df_f = df_s[(o_a >= (t_a - 15)) & (o_a <= (t_a + 15))]
                            if not df_f.empty:
                                diff = (df_f[db_c] - t_v).abs().mean(axis=1)
                                sim = (100 - diff).sort_values(ascending=False).drop(cur_id, errors='ignore').head(10)
                                res = df_f.loc[sim.index].copy()
                                res['Gelijkenis %'] = sim
                                def col_sim(v):
                                    return f"color: {'#2ecc71' if v > 90 else '#27ae60' if v > 80 else 'black'}; font-weight: bold"
                                ev = st.dataframe(res[['Naam', 'Team', 'Seizoen', 'Competitie', 'Gelijkenis %']].style.applymap(col_sim, subset=['Gelijkenis %']).format({'Gelijkenis %': '{:.1f}%'}), use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row")
                                if ev and len(ev.selection.rows) > 0:
                                    s_r = res.iloc[ev.selection.rows[0]]
                                    st.session_state.pending_nav = {"season": s_r['Seizoen'], "competition": s_r['Competitie'], "target_name": s_r['Naam'], "mode": "Spelers"}
                                    st.rerun()

except Exception as e: st.error(f"Fout: {e}")
