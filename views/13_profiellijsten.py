import streamlit as st
import pandas as pd
from utils import run_query, show_sidebar_filters

@st.cache_data(ttl=3600) # Cache dit voor een uur, kolommen veranderen niet vaak
def get_dynamic_profiles():
    """
    Haalt automatisch alle profiel-kolommen op uit de database metadata.
    Zet ze om in een dictionary: {'Mooie Naam': 'database_kolom'}
    """
    # We vragen de database om alle kolomnamen in het schema 'analysis' 
    # en tabel 'final_impect_scores' die eindigen op '_kvk_score'
    query = """
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_schema = 'analysis' 
          AND table_name = 'final_impect_scores' 
          AND column_name LIKE '%_kvk_score';
    """
    df_cols = run_query(query)
    
    profiles = {}
    if not df_cols.empty:
        for col in df_cols['column_name']:
            # Logica om de naam mooi te maken voor de gebruiker:
            # 1. 'offensive_wingback_kvk_score' -> verwijder '_kvk_score'
            # 2. vervang underscores door spaties
            # 3. Zet elk woord met een Hoofdletter
            readable_name = col.replace('_kvk_score', '').replace('_', ' ').title()
            
            # Voeg toe aan dictionary
            profiles[readable_name] = col
            
    return profiles

def show_shortlists_page():
    st.title("📋 Scouting Shortlists (Dynamisch)")

    # -------------------------------------------------------------------------
    # 0. SETUP & DATA OPHALEN
    # -------------------------------------------------------------------------
    # Haal de profielen dynamisch op uit de DB
    profiles_dict = get_dynamic_profiles()
    
    # Check of het gelukt is
    if not profiles_dict:
        st.error("Kon geen profielen vinden in de database (analysis.final_impect_scores).")
        return

    # -------------------------------------------------------------------------
    # 1. FILTERS
    # -------------------------------------------------------------------------
    # Globale filters (Seizoen)
    selected_season, selected_iteration_id = show_sidebar_filters()

    # Lokale filters
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Nu vullen we de selectbox met de keys van onze dynamische dictionary
        selected_profile_name = st.selectbox("Selecteer Profiel", list(profiles_dict.keys()))
        # We halen de echte kolomnaam op die bij de keuze hoort
        selected_db_column = profiles_dict[selected_profile_name]
        
    with col2:
        max_age = st.slider("Maximale Leeftijd", 15, 40, 24)
        
    with col3:
        min_score = st.number_input("Minimale Score", 0, 100, 60)

    # -------------------------------------------------------------------------
    # 2. QUERY UITVOEREN
    # -------------------------------------------------------------------------
    if selected_iteration_id:
        # We bouwen de query op dezelfde manier, maar nu zeker wetende dat de kolom bestaat
        query = f"""
            SELECT 
                info."Spelersnaam" as naam,
                info."Teamnaam" as team,
                DATE_PART('year', AGE(CURRENT_DATE, TO_DATE(info."Geboortedatum", 'YYYY-MM-DD'))) as leeftijd,
                scores."{selected_db_column}" as score,
                scores."position" as positie
            FROM analysis.final_impect_scores as scores
            JOIN tabellen.players_squads_info as info 
              ON scores."playerId"::text = info."Speler_ID"::text
            WHERE 
                scores."iterationId"::int = %s
                AND scores."{selected_db_column}" >= %s
                AND DATE_PART('year', AGE(CURRENT_DATE, TO_DATE(info."Geboortedatum", 'YYYY-MM-DD'))) <= %s
            ORDER BY 
                scores."{selected_db_column}" DESC
            LIMIT 50;
        """
        
        df_shortlist = run_query(query, params=(selected_iteration_id, min_score, max_age))
        
        # -------------------------------------------------------------------------
        # 3. WEERGAVE
        # -------------------------------------------------------------------------
        if not df_shortlist.empty:
            st.success(f"🔍 {len(df_shortlist)} resultaten voor **{selected_profile_name}**")
            
            st.dataframe(
                df_shortlist,
                column_config={
                    "naam": "Speler",
                    "team": "Club",
                    "leeftijd": st.column_config.NumberColumn("Leeftijd", format="%d"),
                    "score": st.column_config.ProgressColumn(
                        f"Score {selected_profile_name}", 
                        format="%.1f", 
                        min_value=0, 
                        max_value=100
                    ),
                },
                use_container_width=True,
                hide_index=True
            )
        else:
            st.warning(f"Geen spelers gevonden voor {selected_profile_name} met score > {min_score}.")
    else:
        st.info("Selecteer links een seizoen.")
