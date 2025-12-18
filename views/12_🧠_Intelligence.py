import streamlit as st
from utils import run_query, init_connection
import pandas as pd

st.title("🧠 Strategisch Speler Dossier")

# Maak twee tabs: Invoeren & Inzien
tab1, tab2 = st.tabs(["📝 Dossier Beheer", "📖 Dossiers Inzien"])

# -----------------------------------------------------------------------------
# HELP FUNCTIE: SPELERS OPHALEN MET CLUBNAME
# -----------------------------------------------------------------------------
def get_players_with_club():
    # We joinen analysis.players met analysis.squads voor de clubnaam 
    query = """
        SELECT p.id, p.commonname, s.name as club_name 
        FROM analysis.players p
        LEFT JOIN analysis.squads s ON p."currentSquadId" = s.id
        ORDER BY p.commonname ASC;
    """
    return run_query(query)

# -----------------------------------------------------------------------------
# TAB 1: DOSSIER BEHEER (INVOEREN & AANPASSEN)
# -----------------------------------------------------------------------------
with tab1:
    st.subheader("Nieuw Dossier of Aanpassen")
    
    # Keuze tussen Database of Manueel
    invoer_methode = st.radio("Selecteer speler via:", ["Database", "Handmatige Invoer"], horizontal=True)
    
    gekozen_id = None
    gekozen_naam = ""

    if invoer_methode == "Database":
        df_db_spelers = get_players_with_club()
        if not df_db_spelers.empty:
            # Maak een mooie weergave: "Naam (Club)" 
            df_db_spelers['display_name'] = df_db_spelers.apply(
                lambda x: f"{x['commonname']} ({x['club_name'] if x['club_name'] else 'Geen Club'})", axis=1
            )
            
            speler_opties = ["Selecteer een speler..."] + df_db_spelers['display_name'].tolist()
            geselecteerde_weergave = st.selectbox("Zoek Speler:", options=speler_opties)
            
            if geselecteerde_weergave != "Selecteer een speler...":
                # Haal ID en naam weer op uit de dataframe
                row = df_db_spelers[df_db_spelers['display_name'] == geselecteerde_weergave].iloc[0]
                gekozen_id = row['id']
                gekozen_naam = row['commonname']
    else:
        gekozen_naam = st.text_input("Voer de naam van de speler handmatig in:")
        gekozen_id = "MANUEEL"

    # Als er een speler is geselecteerd/ingevoerd, toon het formulier
    if gekozen_naam:
        # Bestaande data ophalen (indien aanwezig)
        if gekozen_id == "MANUEEL":
            check_query = "SELECT * FROM scouting.speler_intelligence WHERE speler_id = 'MANUEEL' AND custom_naam = %s LIMIT 1"
            params = (gekozen_naam,)
        else:
            check_query = "SELECT * FROM scouting.speler_intelligence WHERE speler_id = %s LIMIT 1"
            params = (gekozen_id,)
            
        df_exist = run_query(check_query, params=params)
        heeft_data = not df_exist.empty
        
        # Formulier vullen
        with st.form("intel_form"):
            st.write(f"Dossier voor: **{gekozen_naam}**")
            c1, c2 = st.columns(2)
            with c1:
                club_info = st.text_area("Netwerk & Club Info", value=df_exist.iloc[0]['club_informatie'] if heeft_data else "")
                familie = st.text_area("Familie & Omgeving", value=df_exist.iloc[0]['familie_achtergrond'] if heeft_data else "")
            with c2:
                mentaliteit = st.text_area("Persoonlijkheid & Mentaliteit", value=df_exist.iloc[0]['persoonlijkheid'] if heeft_data else "")
                makelaar = st.text_area("Makelaar & Contract", value=df_exist.iloc[0]['makelaar_details'] if heeft_data else "")
            
            if st.form_submit_button("Opslaan"):
                scout = st.session_state.user_info.get('naam')
                conn = init_connection()
                cur = conn.cursor()
                try:
                    if heeft_data:
                        sql = """UPDATE scouting.speler_intelligence SET club_informatie=%s, familie_achtergrond=%s, 
                                 persoonlijkheid=%s, makelaar_details=%s, toegevoegd_door=%s, laatst_bijgewerkt=NOW() 
                                 WHERE id=%s"""
                        cur.execute(sql, (club_info, familie, mentaliteit, makelaar, scout, int(df_exist.iloc[0]['id'])))
                    else:
                        # Zorg dat je de kolom 'custom_naam' in je database hebt! 
                        sql = """INSERT INTO scouting.speler_intelligence (speler_id, club_informatie, familie_achtergrond, 
                                 persoonlijkheid, makelaar_details, toegevoegd_door, custom_naam) 
                                 VALUES (%s, %s, %s, %s, %s, %s, %s)"""
                        cur.execute(sql, (gekozen_id, club_info, familie, mentaliteit, makelaar, scout, gekozen_naam if gekozen_id == "MANUEEL" else None))
                    conn.commit()
                    st.success("Opgeslagen!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Fout: {e}")
                finally:
                    cur.close()
                    conn.close()

# -----------------------------------------------------------------------------
# TAB 2: DOSSIERS INZIEN (LEZEN & FILTEREN)
# -----------------------------------------------------------------------------
with tab2:
    st.subheader("Alle Opgeslagen Dossiers")
    
    # Haal alle dossiers op met spelersnamen
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
        # Filter optie
        search = st.text_input("Filter op speler of club:", "").lower()
        df_filtered = df_all[
            df_all['speler_naam'].str.lower().contains(search, na=False) | 
            df_all['club'].str.lower().contains(search, na=False)
        ]
        
        # Tabel weergave
        st.write("Klik op een rij in de tabel hieronder om het volledige dossier te lezen.")
        # We gebruiken dataframe selectie
        event = st.dataframe(
            df_filtered[['speler_naam', 'club', 'scout', 'laatst_bijgewerkt']],
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single"
        )
        
        # Details tonen bij selectie
        if event and len(event.selection.rows) > 0:
            selected_idx = event.selection.rows[0]
            row = df_filtered.iloc[selected_idx]
            
            st.divider()
            st.header(f"📖 Dossier: {row['speler_naam']}")
            
            col_a, col_b = st.columns(2)
            with col_a:
                st.markdown(f"**Club Info:**\n{row['club_informatie']}")
                st.markdown(f"**Familie:**\n{row['familie_achtergrond']}")
            with col_b:
                st.markdown(f"**Mentaliteit:**\n{row['persoonlijkheid']}")
                st.markdown(f"**Makelaar:**\n{row['makelaar_details']}")
            
            st.caption(f"Bijgewerkt op {row['laatst_bijgewerkt']} door {row['scout']}")
    else:
        st.info("Er zijn nog geen dossiers om weer te geven.")
