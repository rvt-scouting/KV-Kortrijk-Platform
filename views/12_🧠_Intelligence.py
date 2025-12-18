import streamlit as st
from utils import run_query, init_connection
import pandas as pd

# -----------------------------------------------------------------------------
# 1. SETUP & CONFIGURATIE
# -----------------------------------------------------------------------------
st.title("🧠 Strategisch Speler Dossier")

# Helper voor het ophalen van spelers inclusief clubnaam 
def get_players_data():
    query = """
        SELECT p.id, p.commonname, s.name as club_name 
        FROM analysis.players p
        LEFT JOIN analysis.squads s ON p."currentSquadId" = s.id
        ORDER BY p.commonname ASC;
    """
    return run_query(query)

# TABS voor structuur en piramide-weergave
tab1, tab2 = st.tabs(["📝 Dossier Beheer", "📖 Overzicht & Zoeken"])

# -----------------------------------------------------------------------------
# TAB 1: DOSSIER BEHEER (INVOEREN & AANPASSEN)
# -----------------------------------------------------------------------------
with tab1:
    st.subheader("Speler Selecteren")
    
    methode = st.radio("Bron:", ["Database", "Handmatige Invoer (Nieuwe speler)"], horizontal=True)
    
    selected_id = None
    selected_name = ""
    
    if methode == "Database":
        df_db = get_players_data()
        if not df_db.empty:
            df_db['display'] = df_db.apply(lambda x: f"{x['commonname']} ({x['club_name'] if x['club_name'] else 'Geen club'})", axis=1)
            keuze = st.selectbox("Zoek speler uit de database:", ["Selecteer..."] + df_db['display'].tolist())
            if keuze != "Selecteer...":
                row = df_db[df_db['display'] == keuze].iloc[0]
                selected_id = row['id']
                selected_name = row['commonname']
    else:
        selected_name = st.text_input("Naam van de nieuwe speler:")
        selected_id = "MANUEEL"

    if selected_name:
        # Zoek bestaand dossier 
        if selected_id == "MANUEEL":
            check_sql = "SELECT * FROM scouting.speler_intelligence WHERE speler_id = 'MANUEEL' AND custom_naam = %s"
            existing = run_query(check_sql, params=(selected_name,))
        else:
            check_sql = "SELECT * FROM scouting.speler_intelligence WHERE speler_id = %s"
            existing = run_query(check_sql, params=(selected_id,))
            
        heeft_data = not existing.empty
        
        with st.form("dossier_form"):
            st.write(f"Bewerken: **{selected_name}**")
            
            c1, c2 = st.columns(2)
            with c1:
                club_info = st.text_area("Club / Netwerk Informatie", value=existing.iloc[0]['club_informatie'] if heeft_data else "")
                familie = st.text_area("Familie & Omgeving", value=existing.iloc[0]['familie_achtergrond'] if heeft_data else "")
            with c2:
                mentaliteit = st.text_area("Persoonlijkheid & Mentaliteit", value=existing.iloc[0]['persoonlijkheid'] if heeft_data else "")
                makelaar = st.text_area("Makelaar & Contract", value=existing.iloc[0]['makelaar_details'] if heeft_data else "")
            
            if st.form_submit_button("Dossier Opslaan / Bijwerken"):
                scout = st.session_state.user_info.get('naam', 'Onbekend')
                conn = init_connection()
                cur = conn.cursor()
                try:
                    if heeft_data:
                        sql = """UPDATE scouting.speler_intelligence 
                                 SET club_informatie=%s, familie_achtergrond=%s, persoonlijkheid=%s, 
                                     makelaar_details=%s, toegevoegd_door=%s, laatst_bijgewerkt=NOW() 
                                 WHERE id=%s"""
                        cur.execute(sql, (club_info, familie, mentaliteit, makelaar, scout, int(existing.iloc[0]['id'])))
                    else:
                        sql = """INSERT INTO scouting.speler_intelligence 
                                 (speler_id, club_informatie, familie_achtergrond, persoonlijkheid, 
                                  makelaar_details, toegevoegd_door, custom_naam) 
                                 VALUES (%s, %s, %s, %s, %s, %s, %s)"""
                        cur.execute(sql, (selected_id, club_info, familie, mentaliteit, makelaar, scout, 
                                          selected_name if selected_id == "MANUEEL" else None))
                    conn.commit()
                    st.success("Dossier succesvol bijgewerkt!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Fout bij opslaan: {e}")
                finally:
                    cur.close()
                    conn.close()

# -----------------------------------------------------------------------------
# TAB 2: OVERZICHT & ZOEKEN
# -----------------------------------------------------------------------------
with tab2:
    st.subheader("Alle Opgeslagen Dossiers")
    
    all_data_sql = """
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
    df_all = run_query(all_data_sql)
    
    if not df_all.empty:
        search = st.text_input("🔍 Filter op naam of club:").lower()
        df_display = df_all[
            df_all['speler_naam'].str.lower().str.contains(search, na=False) | 
            df_all['club'].str.lower().str.contains(search, na=False)
        ]
        
        selection = st.dataframe(
            df_display[['speler_naam', 'club', 'scout', 'laatst_bijgewerkt']],
            use_container_width=True,
            hide_index=True,
            on_select="rerun",
            selection_mode="single"
        )
        
        if selection and selection.selection.rows:
            dossier = df_display.iloc[selection.selection.rows[0]]
            
            st.divider()
            st.markdown(f"### 📖 Volledig Dossier: {dossier['speler_naam']}")
            
            c_a, c_b = st.columns(2)
            with c_a:
                st.info("**Club / Netwerk Info**")
                st.write(dossier['club_informatie'] if dossier['club_informatie'] else "Niks ingevuld.")
                st.info("**Familie & Omgeving**")
                st.write(dossier['familie_achtergrond'] if dossier['familie_achtergrond'] else "Niks ingevuld.")
            with c_b:
                st.warning("**Persoonlijkheid & Mentaliteit**")
                st.write(dossier['persoonlijkheid'] if dossier['persoonlijkheid'] else "Niks ingevuld.")
                st.error("**Makelaar & Contract**")
                st.write(dossier['makelaar_details'] if dossier['makelaar_details'] else "Niks ingevuld.")
    else:
        st.write("Er zijn nog geen dossiers aangemaakt.")
