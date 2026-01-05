import streamlit as st
import pandas as pd
from utils import run_query

# -------------------------------------------------------------------------
# HULPFUNCTIES
# -------------------------------------------------------------------------

@st.cache_data(ttl=3600)
def get_dynamic_profiles():
    """Haalt beschikbare profiel-kolommen op uit de DB."""
    query = """
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_schema = 'analysis' 
          AND table_name = 'final_impect_scores' 
          AND column_name LIKE '%_kvk_score';
    """
    # LET OP: suppress_error is weggehaald
    df_cols = run_query(query)
    
    profiles = {}
    if not df_cols.empty:
        for col in df_cols['column_name']:
            readable_name = col.replace('_kvk_score', '').replace('_', ' ').title()
            profiles[readable_name] = col
    return profiles

@st.cache_data(ttl=3600)
def get_seasons():
    """Haalt unieke seizoenen op uit de iterations tabel."""
    query = "SELECT DISTINCT season FROM public.iterations ORDER BY season DESC;"
    # LET OP: suppress_error is weggehaald
    df = run_query(query)
    if not df.empty:
        return df['season'].tolist()
    return []

def get_iteration_ids_for_season(season):
    """Haalt alle iterationID's op die bij een specifiek seizoen horen."""
    query = "SELECT id FROM public.iterations WHERE season = %s"
    # LET OP: suppress_error is weggehaald
    df = run_query(query, params=(season,))
    if not df.empty:
        return df['id'].tolist() 
    return []

# -------------------------------------------------------------------------
# HOOFD PAGINA
# -------------------------------------------------------------------------

def show_shortlists_page():
    st.title("📋 Scouting Shortlists")

    # 1. SETUP: Haal profielen en seizoenen op
    profiles_dict = get_dynamic_profiles()
    seasons_list = get_seasons()
    
    if not profiles_dict:
        st.error("Kan geen profielen laden. Check database connectie.")
        return

    # 2. FILTERS (Bovenaan de pagina)
    
    # Rij 1: Het Seizoen
    col_season, _ = st.columns([1, 3]) 
    with col_season:
        selected_season = st.selectbox("Kies Seizoen", seasons_list)

    st.markdown("---") 

    # Rij 2: De specifieke criteria
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Check of de dictionary niet leeg is voor we keys opvragen
        if profiles_dict:
            selected_profile_name = st.selectbox("Selecteer Profiel", list(profiles_dict.keys()))
            selected_db_column = profiles_dict[selected_profile_name]
        else:
            st.warning("Geen profielen gevonden.")
            selected_db_column = None
        
    with col2:
        max_age = st.slider("Maximale Leeftijd", 15, 38, 24)
        
    with col3:
        min_score = st.number_input("Minimale Score", 0, 100, 60)

    # 3. DATA OPHALEN
    if selected_season and selected_db_column:
        # Stap A: Haal alle ID's op
        iteration_ids = get_iteration_ids_for_season(selected_season)
        
        if not iteration_ids:
            st.warning(f"Geen data gevonden voor seizoen {selected_season}")
            return

        # Stap B: Maak string voor SQL IN clause
        ids_string = ",".join(map(str, iteration_ids))

        # Stap C: De Query
        query = f"""
            SELECT 
                info."Spelersnaam" as naam,
                info."Teamnaam" as team,
                scores."iterationId" as comp_id,
                DATE_PART('year', AGE(CURRENT_DATE, TO_DATE(info."Geboortedatum", 'YYYY-MM-DD'))) as leeftijd,
                scores."{selected_db_column}" as score,
                scores."position" as positie
            FROM analysis.final_impect_scores as scores
            JOIN tabellen.players_squads_info as info 
              ON scores."playerId"::text = info."Speler_ID"::text
            WHERE 
                scores."iterationId"::int IN ({ids_string})
                AND scores."{selected_db_column}" >= %s
                AND DATE_PART('year', AGE(CURRENT_DATE, TO_DATE(info."Geboortedatum", 'YYYY-MM-DD'))) <= %s
            ORDER BY 
                scores."{selected_db_column}" DESC
            LIMIT 50;
        """
        
        # Stap D: Uitvoeren (zonder suppress_error parameter!)
        df_shortlist = run_query(query, params=(min_score, max_age))
        
        # 4. RESULTAAT TONEN
        if not df_shortlist.empty:
            st.success(f"🔍 {len(df_shortlist)} spelers gevonden in **Seizoen {selected_season}**.")
            
            st.dataframe(
                df_shortlist,
                column_config={
                    "naam": "Speler",
                    "team": "Club",
                    "leeftijd": st.column_config.NumberColumn("Leeftijd", format="%d"),
                    "score": st.column_config.ProgressColumn(
                        f"Score", 
                        format="%.1f", 
                        min_value=0, 
                        max_value=100
                    ),
                    "comp_id": None 
                },
                use_container_width=True,
                hide_index=True
            )
        else:
            st.warning("Geen spelers gevonden met deze criteria (of database toegang issue).")

# De functie aanroepen
show_shortlists_page()
