import streamlit as st
from utils import run_query, init_connection
import pandas as pd

# -----------------------------------------------------------------------------
# 1. PAGINA CONFIGURATIE & TITEL
# -----------------------------------------------------------------------------
st.title("🧠 Strategisch Speler Dossier")
st.info("Leg hier kwalitatieve informatie vast over de achtergrond, familie en mentaliteit van spelers.")

# -----------------------------------------------------------------------------
# 2. SPELER SELECTIE
# -----------------------------------------------------------------------------
# We halen de spelerslijst op uit de analysis.players tabel 
speler_query = "SELECT id, commonname FROM analysis.players ORDER BY commonname ASC;"
df_spelers = run_query(speler_query)

if not df_spelers.empty:
    # Maak een dictionary voor de selectbox: "Naam": "ID"
    speler_dict = dict(zip(df_spelers['commonname'], df_spelers['id']))
    gekozen_naam = st.selectbox("Zoek een speler om het dossier in te zien of bij te werken:", 
                                options=["Selecteer een speler..."] + list(speler_dict.keys()))
    
    if gekozen_naam != "Selecteer een speler...":
        speler_id = speler_dict[gekozen_naam]
        
        # -----------------------------------------------------------------------------
        # 3. BESTAANDE DATA OPHALEN
        # -----------------------------------------------------------------------------
        # We halen de meest recente intelligence op voor deze speler
        bestaande_data_query = """
            SELECT * FROM scouting.speler_intelligence 
            WHERE speler_id = %s 
            ORDER BY laatst_bijgewerkt DESC LIMIT 1
        """
        df_intelligence = run_query(bestaande_data_query, params=(speler_id,))
        
        # Controleer of er al een dossier bestaat
        heeft_data = not df_intelligence.empty
        
        # We stellen de beginwaarden in voor het formulier
        init_club = df_intelligence.iloc[0]['club_informatie'] if heeft_data else ""
        init_familie = df_intelligence.iloc[0]['familie_achtergrond'] if heeft_data else ""
        init_mentaliteit = df_intelligence.iloc[0]['persoonlijkheid'] if heeft_data else ""
        init_makelaar = df_intelligence.iloc[0]['makelaar_details'] if heeft_data else ""

        # -----------------------------------------------------------------------------
        # 4. INVOER- & AANPASFORMULIER
        # -----------------------------------------------------------------------------
        with st.form("dossier_form", clear_on_submit=False):
            st.subheader(f"Dossier: {gekozen_naam}")
            
            # Toon metadata als het dossier al bestaat
            if heeft_data:
                st.caption(f"Laatste update: {df_intelligence.iloc[0]['laatst_bijgewerkt'].strftime('%d-%m-%Y %H:%M')} door {df_intelligence.iloc[0]['toegevoegd_door']}")

            col1, col2 = st.columns(2)
            
            with col1:
                club_info = st.text_area("Netwerk & Club Info", 
                                         value=init_club, 
                                         height=200, 
                                         help="Wat zeggen bronnen binnen andere clubs?")
                familie = st.text_area("Familie & Omgeving", 
                                       value=init_familie, 
                                       height=200, 
                                       help="Informatie over gezinssituatie, opvoeding en stabiliteit.")
            
            with col2:
                mentaliteit = st.text_area("Persoonlijkheid & Mentaliteit", 
                                           value=init_mentaliteit, 
                                           height=200, 
                                           help="Is het een leider? Hoe gaat hij om met tegenslagen?")
                makelaar = st.text_area("Makelaar & Contract", 
                                        value=init_makelaar, 
                                        height=200, 
                                        help="Details over de agent en eventuele contractuele bijzonderheden.")

            # Knop voor opslaan
            submit_label = "Dossier Bijwerken" if heeft_data else "Nieuw Dossier Opslaan"
            submitted = st.form_submit_button(submit_label)

            if submitted:
                # Naam van de ingelogde gebruiker ophalen uit de sessie
                scout_naam = st.session_state.user_info.get('naam', 'Onbekend')
                
                conn = init_connection()
                cur = conn.cursor()
                try:
                    if heeft_data:
                        # UPDATE bestaand record
                        update_sql = """
                            UPDATE scouting.speler_intelligence 
                            SET club_informatie = %s, familie_achtergrond = %s, 
                                persoonlijkheid = %s, makelaar_details = %s, 
                                toegevoegd_door = %s, laatst_bijgewerkt = NOW()
                            WHERE speler_id = %s
                        """
                        cur.execute(update_sql, (club_info, familie, mentaliteit, makelaar, scout_naam, speler_id))
                    else:
                        # INSERT nieuw record
                        insert_sql = """
                            INSERT INTO scouting.speler_intelligence 
                            (speler_id, club_informatie, familie_achtergrond, persoonlijkheid, makelaar_details, toegevoegd_door)
                            VALUES (%s, %s, %s, %s, %s, %s)
                        """
                        cur.execute(insert_sql, (speler_id, club_info, familie, mentaliteit, makelaar, scout_naam))
                    
                    conn.commit()
                    st.success(f"Dossier voor {gekozen_naam} succesvol opgeslagen!")
                    st.rerun() # Pagina herladen om de nieuwe data/datum te tonen
                except Exception as e:
                    st.error(f"Fout bij opslaan in database: {e}")
                finally:
                    cur.close()
                    conn.close()

# -----------------------------------------------------------------------------
# 5. HISTORIE OVERZICHT (Piramidestatistieken laag 3)
# -----------------------------------------------------------------------------
st.divider()
st.subheader("Recent bijgewerkte dossiers")

recent_query = """
    SELECT p.commonname AS Speler, i.toegevoegd_door AS Scout, i.laatst_bijgewerkt AS "Laatste Wijziging"
    FROM scouting.speler_intelligence i
    JOIN analysis.players p ON i.speler_id = p.id
    ORDER BY i.laatst_bijgewerkt DESC LIMIT 10
"""
df_recent = run_query(recent_query)

if not df_recent.empty:
    st.dataframe(df_recent, use_container_width=True, hide_index=True)
else:
    st.write("Er zijn nog geen dossiers aangemaakt.")
