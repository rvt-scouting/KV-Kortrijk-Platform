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
    df_cols = run_query(query, suppress_error=True)
    
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
    df = run_query(query, suppress_error=True)
    if not df.empty:
        return df['season'].tolist()
    return []

def get_iteration_ids_for_season(season):
    """Haalt alle iterationID's op die bij een specifiek seizoen horen."""
    query = "SELECT id FROM public.iterations WHERE season = %s"
    df = run_query(query, params=(season,), suppress_error=True)
    if not df.empty:
        return df['id'].tolist() # Geeft bijv [155, 156, 160] terug
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

    # 2. FILTERS (Bovenaan de pagina, in 2 rijen)
    
    # Rij 1: Het Seizoen (De 'Hoofd' filter)
    col_season, _ = st.columns([1, 3]) # Kleine kolom voor seizoen, rest leeg
    with col_season:
        selected_season = st.selectbox("Kies Seizoen", seasons_list)

    st.markdown("---") # Lijntje voor scheiding

    # Rij 2: De specifieke criteria
    col1, col2, col3 = st.columns(3)
    
    with col1:
        selected_profile_name = st.selectbox("Selecteer Profiel", list(profiles_dict.keys()))
        selected_db_column = profiles_dict[selected_profile_name]
        
    with col2:
        max_age = st.slider("Maximale Leeftijd", 15, 38, 24)
        
    with col3:
        min_score = st.number_input("Minimale Score", 0, 100, 60)

    # 3. DATA OPHALEN
    if selected_season:
        # Stap A: Haal alle ID's op die bij dit seizoen horen (alle competities)
        iteration_ids = get_iteration_ids_for_season(selected_season)
        
        if not iteration_ids:
            st.warning(f"Geen data gevonden voor seizoen {selected_season}")
            return

        # Stap B: Maak een string voor de SQL query (bijv: "155, 156")
        # Dit is veilig omdat iteration_ids integers zijn die uit onze eigen DB komen
        ids_string = ",".join(map(str, iteration_ids))

        # Stap C: De Query
        # Let op: We gebruiken nu IN (...) in plaats van =
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
        
        # Voer uit (met suppress_error=True om rode balken te voorkomen)
        df_shortlist = run_query(
            query, 
            params=(min_score, max_age), 
            suppress_error=True
        )
        
        # 4. RESULTAAT TONEN
        if not df_shortlist.empty:
            st.success(f"🔍 {len(df_shortlist)} spelers gevonden in **Seizoen {selected_season}** (Alle competities).")
            
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
                    "comp_id": None # Verbergen voor de gebruiker
                },
                use_container_width=True,
                hide_index=True
            )
        else:
            st.warning("Geen spelers gevonden met deze criteria.")

# Vergeet niet de functie aan te roepen!
show_shortlists_page()
