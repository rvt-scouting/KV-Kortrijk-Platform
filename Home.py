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
            st.error(f"Navigatie fout: {e}")
        del st.session_state.pending_nav

# -----------------------------------------------------------------------------
# 1. SIDEBAR SELECTIE (Data bron)
# -----------------------------------------------------------------------------
st.sidebar.header("1. Selecteer Data")

try:
    # Haal seizoenen op uit de bron 
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
    df_details = run_query('SELECT id FROM public.iterations WHERE season = %s AND "competitionName" = %s LIMIT 1;', params=(selected_season, selected_competition))
    if not df_details.empty:
        selected_iteration_id = str(df_details.iloc[0]['id'])
    else: st.error("Kon geen ID vinden."); st.stop() 
else: st.warning("👈 Kies eerst een seizoen en competitie."); st.stop() 

# -----------------------------------------------------------------------------
# 2. SPELER SELECTIE (RUWE BRON: player_kpis)
# -----------------------------------------------------------------------------
st.sidebar.divider()
st.sidebar.header("2. Speler Zoeken")

# Gebruik public.player_kpis om ALLE geregistreerde spelers te tonen 
players_query = """
    SELECT DISTINCT p.commonname, p.id as "playerId", sq.name as "squadName"
    FROM public.player_kpis pk
    JOIN public.players p ON CAST(pk."playerId" AS TEXT) = p.id
    LEFT JOIN public.squads sq ON pk."squadId" = sq.id
    WHERE pk."iterationId" = %s
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
except Exception as e: st.error("Fout bij ophalen spelers."); st.stop()

# -----------------------------------------------------------------------------
# 3. DASHBOARD WEERGAVE
# -----------------------------------------------------------------------------
st.title(f"🏃‍♂️ Analyse: {selected_player_name}")

# A. TRANSFER STATUS
check_offer_q = "SELECT status, makelaar, vraagprijs, opmerkingen FROM scouting.offered_players WHERE player_id = %s ORDER BY aangeboden_datum DESC LIMIT 1"
df_offer = run_query(check_offer_q, params=(str(final_player_id),))

if not df_offer.empty:
    offer = df_offer.iloc[0]
    st.warning(f"📥 **Aangeboden Speler** | Status: {offer['status']} | Makelaar: {offer['makelaar']} | Prijs: €{offer['vraagprijs'] or '?'}")

# B. BASIS INFO & SCORES
st.divider()
score_query = """
    SELECT p.*, a.*, sq_curr.name as "current_team_name"
    FROM public.players p
    LEFT JOIN analysis.final_impect_scores a ON p.id = a."playerId" AND a."iterationId" = %s
    LEFT JOIN public.squads sq_curr ON p."currentSquadId" = sq_curr.id
    WHERE p.id = %s
"""
df_scores = run_query(score_query, params=(selected_iteration_id, str(final_player_id)))

if not df_scores.empty:
    row = df_scores.iloc[0]
    c1, c2, c3, c4 = st.columns(4)
    with c1: st.metric("Team", row['current_team_name'] or "Onbekend")
    with c2: st.metric("Geboortedatum", str(row['birthdate']))
    with c3: st.metric("Geboorteplaats", row['birthplace'] or "-")
    with c4: st.metric("Voet", row['leg'] or "-")

    # Check of er data is in de analysetabel
    if pd.isna(row['position']):
        st.info("ℹ️ Deze speler heeft nog geen berekende Impect-scores (mogelijk te weinig minuten).")
    else:
        # Hier komen de Spider Charts, Metrics en KPI tabellen zoals in je originele code
        st.markdown("### 📊 Prestatie Profiel")
        # [Hier invoegen: Profile mapping, Spider chart & KPI secties uit je vorige bestand]
        st.write(f"Positie: {row['position']}")

    # C. SCOUTING RAPPORTEN (INTERN)
    st.divider()
    st.subheader("🕵️ Scouting Rapporten (Intern)")
    # [Hier invoegen: Scouting rapporten query en weergave]

    # D. DATA SCOUT RAPPORTEN (EXTERN)
    st.divider()
    st.subheader("📑 Data Scout Rapporten (Extern)")
    # [Hier invoegen: Externe rapporten query]

    # E. STRATEGISCH DOSSIER (INTELLIGENCE)
    st.divider()
    st.subheader("🧠 Strategisch Dossier (Intelligence)")
    intel_q = "SELECT * FROM scouting.speler_intelligence WHERE speler_id = %s ORDER BY laatst_bijgewerkt DESC LIMIT 1"
    df_intel = run_query(intel_q, params=(str(final_player_id),))
    
    if not df_intel.empty:
        i_row = df_intel.iloc[0]
        # Toon links
        l1, l2, l3, l4 = st.columns(4)
        with l1: 
            if i_row.get('instagram_url'): st.link_button("📸 Instagram", i_row['instagram_url'], use_container_width=True)
        with l2: 
            if i_row.get('twitter_url'): st.link_button("🐦 Twitter / X", i_row['twitter_url'], use_container_width=True)
        with l3: 
            if i_row.get('transfermarkt_url'): st.link_button("⚽ Transfermarkt", i_row['transfermarkt_url'], use_container_width=True)
        
        # Toon Intelligence vakken
        ci1, ci2 = st.columns(2)
        with ci1:
            st.info(f"**Club Info:**\n{i_row['club_informatie'] or '-'}")
            st.info(f"**Familie:**\n{i_row['familie_achtergrond'] or '-'}")
        with ci2:
            st.warning(f"**Mentaliteit:**\n{i_row['persoonlijkheid'] or '-'}")
            st.error(f"**Makelaar:**\n{i_row['makelaar_details'] or '-'}")
        st.caption(f"Laatste wijziging: {i_row['laatst_bijgewerkt']} door {i_row['toegevoegd_door']}")
    else:
        st.info("Nog geen intelligence dossier beschikbaar.")

    # F. SIMILARITY
    st.divider()
    st.subheader("👯 Vergelijkbare Spelers")
    # [Hier invoegen: Similarity logica]
