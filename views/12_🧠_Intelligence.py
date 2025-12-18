import streamlit as st
from utils import run_query, init_connection
import pandas as pd

st.title("🧠 Strategisch Speler Dossier")

# --- HELPER FUNCTIES ---
def get_players_with_club():
    """Haalt spelers op met hun clubnaam voor onderscheid in de dropdown."""
    query = """
        SELECT p.id, p.commonname, s.name as club_name 
        FROM analysis.players p
        LEFT JOIN analysis.squads s ON p."currentSquadId" = s.id
        ORDER BY p.commonname ASC;
    """
    return run_query(query)

# --- TABS ---
tab1, tab2 = st.tabs(["📝 Dossier Beheer", "📖 Dossiers Inzien"])

# -----------------------------------------------------------------------------
# TAB 1: DOSSIER BEHEER (INVOEREN & AANPASSEN)
# -----------------------------------------------------------------------------
with tab1:
    st.subheader("Speler Selectie")
    
    invoer_methode = st.radio("Selecteer speler via:", ["Database", "Handmatige Invoer"], horizontal=True)
    
    gekozen_id = None
    gekozen_naam = ""

    if invoer_methode == "Database":
        df_db_spelers = get_players_with_club()
        if not df_db_spelers.empty:
            # Weergave: "Naam (Club)" 
            df_db_spelers['display_name'] = df_db_spelers.apply(
                lambda x: f"{x['commonname']} ({x['club_name'] if x['club_name'] else 'Geen Club'})", axis=1
            )
            
            speler_opties = ["Selecteer een speler..."] + df_db_spelers['display_name'].tolist()
            geselecteerde_weergave = st.selectbox("Zoek Speler:", options=speler_opties)
            
            if geselecteerde_weergave != "Selecteer een speler...":
                row = df_db_spelers[df_db_spelers['display_name'] == geselecteerde_weergave].iloc[0]
                gekozen_id = row['id']
                gekozen_naam = row['commonname']
    else:
        # Optie voor spelers die niet in de database staan 
        gekozen_naam = st.text_input("Voer de naam van de speler handmatig in:")
        gekozen_id = "MANUEEL"

    if gekozen_naam:
        # Check of er al een dossier bestaat voor deze selectie om aanpassingen mogelijk te maken
        if gekozen_id == "MANUEEL":
            check_query = "SELECT * FROM scouting.speler_intelligence WHERE speler_id = 'MANUEEL' AND custom_naam = %s LIMIT 1"
            params = (gekozen_naam,)
        else:
            check_query = "SELECT * FROM scouting.speler_intelligence WHERE speler_id = %s LIMIT 1"
            params = (gekozen_id,)
            
        df_exist = run_query(check_query, params=params)
        heeft_data = not df_exist.empty
        
        # Formulier voor invoer of aanpassing
        with st.form("intel_form"):
            st.write(f"Dossier voor: **{gekozen_naam}**")
            if heeft_data:
                st.info(f"Bestaand dossier gevonden (laatst bijgewerkt door {df_exist.iloc[0]['toegevoegd_door']}).")

            c1, c2 = st.columns(2)
            with c1:
                club_info = st.text_area("Netwerk & Club Info", value=df_exist.iloc[0]['club_informatie'] if heeft_data else "")
                familie = st.text_area("Familie & Omgeving", value=df_exist.iloc[0]['familie_achtergrond'] if heeft_data else "")
            with c2:
                mentaliteit = st.text_area("Persoonlijkheid & Mentaliteit", value=df_exist.iloc[0]['persoonlijkheid'] if heeft_data else "")
                makelaar = st.text_area("Makelaar & Contract", value=df_exist.iloc[0]['makelaar_details'] if heeft_data else "")
            
            if st.form_submit_button("Gegevens Opslaan"):
                scout = st.session_state.user_info.get('naam')
                conn = init_connection()
                cur = conn.cursor()
                try:
                    if heeft_data:
                        # Bestaand dossier aanpassen
                        sql = """UPDATE scouting.speler_intelligence SET club_informatie=%s, familie_achtergrond=%s, 
                                 persoonlijkheid=%s, makelaar_details=%s, toegevoegd_door=%s, laatst_bijgewerkt=NOW() 
                                 WHERE id=%s"""
                        cur.execute(sql, (club_info, familie, mentaliteit, makelaar, scout, int(df_exist.iloc[0]['id'])))
                    else:
                        # Nieuw dossier aanmaken
                        sql = """INSERT INTO scouting.speler_intelligence (speler_id, club_informatie, familie_achtergrond, 
                                 persoonlijkheid, makelaar_details, toegevoegd_door, custom_naam) 
                                 VALUES (%s, %s, %s, %s, %s, %s, %s)"""
                        cur.execute(sql, (gekozen_id, club_info, familie, mentaliteit, makelaar, scout, gekozen_naam if gekozen_id == "MANUEEL" else None))
                    conn.commit()
                    st.success(f"Dossier voor {gekozen_naam} succesvol opgeslagen!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Fout bij opslaan: {e}")
                finally:
                    cur.close()
                    conn.close()

# -----------------------------------------------------------------------------
# TAB 2: DOSSIERS INZIEN (TABEL, FILTER & SELECTIE)
# -----------------------------------------------------------------------------
with tab2:
    st.subheader("Alle Opgeslagen Dossiers")
    
    # Query voor alle dossiers met clubnamen
    list_query = """
        SELECT i.id, 
               COALESCE(p.commonname, i.custom_naam) as speler_naam,
               s.name as club,
               i.toegevoegd_door as scout,
               i.laatst_bijgewerkt,
               i.club_informatie, i.familie_achtergrond, i.persoonlijkheid, i.makelaar_details
        FROM scouting.speler_intelligence i
        LEFT JOIN analysis.players p ON i.speler_id = p.id
        LEFT JOIN analysis.squads s ON p."currentSquadId" = s.id
        ORDER BY i.laatst_bijgewerkt DESC
    """
    df_all = run_query(list_query)
    
    if not df_all.empty:
        # Zoek- en filterfunctie
        search = st.text_input("🔍 Filter op speler of club:").lower()
        df_filtered = df_all[
            df_all['speler_naam'].str.lower().str.contains(search, na=False) | 
            df_all['club'].str.lower().str.contains(search, na=False)
        ]
        
        st.write("Klik op een speler om het dossier te openen:")
        # Tabel weergave met selectie-mogelijkheid
        selection = st.dataframe(
            df_filtered[['speler_naam', 'club', 'scout', 'laatst_bijgewerkt']],
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single"
        )
        
        # Weergave van details bij selectie
        if selection and selection.selection.rows:
            row_idx = selection.selection.rows[0]
            row = df_filtered.iloc[row_idx]
            
            st.divider()
            st.header(f"📖 Dossier: {row['speler_naam']}")
            
            col_a, col_b = st.columns(2)
            with col_a:
                st.info("**Club Info & Bronnen**")
                st.write(row['club_informatie'] if row['club_informatie'] else "-")
                st.info("**Familie & Achtergrond**")
                st.write(row['familie_achtergrond'] if row['familie_achtergrond'] else "-")
            with col_b:
                st.warning("**Persoonlijkheid & Mentaliteit**")
                st.write(row['persoonlijkheid'] if row['persoonlijkheid'] else "-")
                st.error("**Makelaar & Contract**")
                st.write(row['makelaar_details'] if row['makelaar_details'] else "-")
            
            st.caption(f"Dit dossier is voor het laatst bijgewerkt door {row['scout']} op {row['laatst_bijgewerkt']}.")
    else:
        st.info("Er zijn nog geen dossiers beschikbaar.")
        
