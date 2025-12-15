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
    # Check of de navigatie bedoeld is voor SPELERS
    if nav.get("mode") == "Spelers":
        try:
            st.session_state.sb_season = nav["season"]
            st.session_state.sb_competition = nav["competition"]
            st.session_state.sb_player = nav["target_name"]
        except Exception as e:
            print(f"Navigatie fout: {e}")
        # Verwijder de taak zodat hij niet blijft hangen
        del st.session_state.pending_nav

# -----------------------------------------------------------------------------
# 1. SIDEBAR SELECTIE
# -----------------------------------------------------------------------------
st.sidebar.header("1. Selecteer Data")

try:
    df_seasons = run_query("SELECT DISTINCT season FROM public.iterations ORDER BY season DESC;")
    seasons_list = df_seasons['season'].tolist()
    # Zorg voor default in session state
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

# Haal Iteration ID op
selected_iteration_id = None
if selected_season and selected_competition:
    df_details = run_query('SELECT season, "competitionName", id FROM public.iterations WHERE season = %s AND "competitionName" = %s LIMIT 1;', params=(selected_season, selected_competition))
    if not df_details.empty:
        selected_iteration_id = str(df_details.iloc[0]['id'])
    else: st.error("Kon geen ID vinden."); st.stop() 
else: st.warning("👈 Kies eerst een seizoen en competitie."); st.stop() 

# -----------------------------------------------------------------------------
# 2. SPELER LOGICA
# -----------------------------------------------------------------------------
st.title("🏃‍♂️ Speler Analyse")

# A. SPELER SELECTIE
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
        st.warning("Geen spelers gevonden in deze competitie."); st.stop()
        
    unique_names = df_players['commonname'].unique().tolist()
    
    # Check navigatie state voor default value
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

# B. CHECK TRANSFER STATUS
check_offer_q = """
    SELECT status, makelaar, vraagprijs, opmerkingen 
    FROM scouting.offered_players 
    WHERE player_id = %s 
    ORDER BY aangeboden_datum DESC LIMIT 1
"""
df_offer = run_query(check_offer_q, params=(str(final_player_id),))

if not df_offer.empty:
    offer_row = df_offer.iloc[0]
    status_color = "#f39c12" 
    if offer_row['status'] == 'Interessant': status_color = "#27ae60" 
    if offer_row['status'] == 'Afgekeurd': status_color = "#c0392b" 
    
    price_display = f"€ {offer_row['vraagprijs']:,.0f}" if offer_row['vraagprijs'] else "Onbekend"
    
    st.markdown(f"""
        <div style="padding: 15px; background-color: {status_color}15; border: 2px solid {status_color}; border-radius: 8px; margin-bottom: 25px;">
            <h4 style="color: {status_color}; margin:0;">📥 Aangeboden Speler</h4>
            <p style="margin: 5px 0 0 0; font-size: 16px;">
                <strong>Status:</strong> {offer_row['status']} &nbsp;|&nbsp; 
                <strong>Makelaar:</strong> {offer_row['makelaar']} &nbsp;|&nbsp; 
                <strong>Vraagprijs:</strong> {price_display}
            </p>
            <p style="margin: 5px 0 0 0; font-style: italic; font-size: 14px; color: #555;">"{offer_row['opmerkingen']}"</p>
        </div>
    """, unsafe_allow_html=True)

# C. DATA METRICS
st.divider()
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
        st.markdown("---")

        # PROFIELEN
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
        
        def highlight_high_scores(val):
            return 'color: #2ecc71; font-weight: bold' if isinstance(val, (int, float)) and val > 66 else ''

        top_profile_name = df_chart.sort_values(by='Score', ascending=False).iloc[0]['Profiel'] if not df_chart.empty and df_chart.iloc[0]['Score'] > 66 else None
        if top_profile_name: st.success(f"### ✅ Speler is POSITIEF op data profiel: {top_profile_name}")
        
        c1, c2 = st.columns([1, 2])
        with c1:
            st.write(f"**Positie:** {row['position']}")
            st.dataframe(df_chart.style.applymap(highlight_high_scores, subset=['Score']).format({'Score': '{:.1f}'}), use_container_width=True, hide_index=True)
        with c2:
            if not df_chart.empty:
                fig = px.pie(df_chart, values='Score', names='Profiel', title=f'KVK Profielverdeling', hole=0.4, color_discrete_sequence=['#d71920', '#ecf0f1', '#bdc3c7', '#c0392b'])
                fig.update_traces(textinfo='value', textfont_size=15, marker=dict(line=dict(color='#000000', width=1)))
                st.plotly_chart(fig, use_container_width=True)

        # METRIEKEN & KPIS
        st.markdown("---"); st.subheader("📊 Impect Scores & KPIs")
        metrics_config = get_config_for_position(row['position'], POSITION_METRICS)
        kpis_config = get_config_for_position(row['position'], POSITION_KPIS)
        
        col_met, col_kpi = st.columns(2)
        
        with col_met:
            st.write("**Metrieken**")
            if metrics_config:
                def get_metrics_table(metric_ids):
                    if not metric_ids: return pd.DataFrame()
                    ids_tuple = tuple(str(x) for x in metric_ids)
                    q = """SELECT d.name as "Metriek", d.details_label as "Detail", s.final_score_1_to_100 as "Score" FROM analysis.player_final_scores s JOIN public.player_score_definitions d ON CAST(s.metric_id AS TEXT) = d.id WHERE s."iterationId" = %s AND s."playerId" = %s AND s.metric_id IN %s ORDER BY s.final_score_1_to_100 DESC"""
                    return run_query(q, params=(selected_iteration_id, p_player_id, ids_tuple))
                
                df_aan = get_metrics_table(metrics_config.get('aan_bal', []))
                df_zonder = get_metrics_table(metrics_config.get('zonder_bal', []))
                
                if not df_aan.empty: st.caption("Aan de Bal"); st.dataframe(df_aan.style.applymap(highlight_high_scores, subset=['Score']), use_container_width=True, hide_index=True)
                if not df_zonder.empty: st.caption("Zonder Bal"); st.dataframe(df_zonder.style.applymap(highlight_high_scores, subset=['Score']), use_container_width=True, hide_index=True)
            else: st.info("Geen configuratie.")

        with col_kpi:
            st.write("**KPIs**")
            if kpis_config:
                def get_kpis_table(kpi_ids):
                    if not kpi_ids: return pd.DataFrame()
                    ids_tuple = tuple(str(x) for x in kpi_ids)
                    q = """SELECT d.name as "KPI", d.context as "Context", s.final_score_1_to_100 as "Score" FROM analysis.kpis_final_scores s JOIN analysis.kpi_definitions d ON CAST(s.metric_id AS TEXT) = d.id WHERE s."iterationId" = %s AND s."playerId" = %s AND s.metric_id IN %s ORDER BY s.final_score_1_to_100 DESC"""
                    return run_query(q, params=(selected_iteration_id, p_player_id, ids_tuple))
                
                df_k1 = get_kpis_table(kpis_config.get('aan_bal', []))
                df_k2 = get_kpis_table(kpis_config.get('zonder_bal', []))
                
                if not df_k1.empty: st.caption("Aan de Bal"); st.dataframe(df_k1.style.applymap(highlight_high_scores, subset=['Score']), use_container_width=True, hide_index=True)
                if not df_k2.empty: st.caption("Zonder Bal"); st.dataframe(df_k2.style.applymap(highlight_high_scores, subset=['Score']), use_container_width=True, hide_index=True)

        # INTERNE RAPPORTEN
        st.markdown("---")
        st.subheader("🕵️ Scouting Rapporten (Intern)")
        scouting_query = """
            SELECT s.naam as "Scout", r.aangemaakt_op as "Datum", r.positie_gespeeld as "Positie", r.profiel_code as "Profiel",
                r.beoordeling as "Rating", r.advies as "Advies", r.rapport_tekst, r.gouden_buzzer, COALESCE(m.id::text, r.custom_wedstrijd_naam) as "Wedstrijd_Ref"
            FROM scouting.rapporten r
            LEFT JOIN scouting.gebruikers s ON r.scout_id = s.id
            LEFT JOIN public.matches m ON r.wedstrijd_id = m.id
            WHERE r.speler_id = %s
            ORDER BY r.aangemaakt_op DESC
        """
        try:
            df_internal = run_query(scouting_query, params=(str(final_player_id),))
            if not df_internal.empty:
                display_cols = ["Datum", "Scout", "Positie", "Profiel", "Rating", "Advies"]
                df_disp = df_internal.copy()
                df_disp['Datum'] = pd.to_datetime(df_disp['Datum']).dt.strftime('%d-%m-%Y')
                
                def highlight_rows(row):
                    return ['background-color: #fff9c4'] * len(row) if row.name in df_internal[df_internal['gouden_buzzer']==True].index else [''] * len(row)

                st.dataframe(df_disp[display_cols], use_container_width=True, hide_index=True)
                
                with st.expander("📖 Lees volledige rapport teksten"):
