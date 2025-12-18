import streamlit as st
from utils import run_query, init_connection
import pandas as pd

st.title("🧠 Strategisch Speler Dossier")

# 1. Selecteer Speler
speler_query = "SELECT id, commonname FROM analysis.players ORDER BY commonname ASC;"
df_spelers = run_query(speler_query)

if not df_spelers.empty:
    speler_dict = dict(zip(df_spelers['commonname'], df_spelers['id']))
    gekozen_naam = st.selectbox("Zoek Speler:", options=["Selecteer een speler..."] + list(speler_dict.keys()))
    
    if gekozen_naam != "Selecteer een speler...":
        speler_id = speler_dict[gekozen_naam]
        
        # 2. Bestaande data ophalen
        bestaande_data_query = "SELECT * FROM scouting.speler_intelligence WHERE speler_id = %s ORDER BY laatst_bijgewerkt DESC LIMIT 1"
        df_intelligence = run_query(bestaande_data_query, params=(speler_id,))
        
        # We vullen de velden met bestaande data als die er is
        heeft_data = not df_intelligence.empty
        init_club = df_intelligence.iloc[0]['club_informatie'] if heeft_data else ""
        init_familie = df_intelligence.iloc[0]['familie_achtergrond'] if heeft_data else ""
        init_mentaliteit = df_intelligence.iloc[0]['persoonlijkheid'] if heeft_data else ""
        init_makelaar = df_intelligence.iloc[0]['makelaar_details'] if heeft_data else ""

        # 3. Formulier (Invoeren & Aanpassen)
        with st.form("dossier_form", clear_on_submit=False):
            st.subheader(f"Dossier van {gekozen_naam}")
            if heeft_data:
                st.caption(f"Laatste update: {df_intelligence.iloc[0]['laatst_bijgewerkt']} door {df_intelligence.iloc[0]['toegevoegd_door']}")

            col1, col2 = st.columns(2)
            with col1:
                club_info = st.text_area("Club Informatie (netwerk)", value=init_club, height=150)
                familie = st.text_area("Familie & Omgeving", value=init_familie, height=150)
            with col2:
                mentaliteit = st.text_area("Persoonlijkheid & Mentaliteit", value=init_mentaliteit, height=150)
                makelaar = st.text_area("Makelaar & Contract", value=init_makelaar, height=150)

            submitted = st.form_submit_button("Dossier Bijwerken")

            if submitted:
                conn = init_connection()
                cur = conn.cursor()
                try:
                    # We gebruiken een UPDATE als er al data is, anders een INSERT
                    if heeft_data:
                        update_sql = """
                            UPDATE scouting.speler_intelligence 
                            SET club_informatie = %s, familie_achtergrond = %s, 
                                persoonlijkheid = %s, makelaar_details = %s, 
                                toegevoegd_door = %s, laatst_bijgewerkt = NOW()
                            WHERE speler_id = %s
                        """
                        cur.execute(update_sql, (club_info, familie, mentaliteit, makelaar, st.session_state.user_info['naam'], speler_id))
                    else:
                        insert_sql = """
                            INSERT INTO scouting.speler_intelligence 
                            (speler_id, club_informatie, familie_achtergrond, persoonlijkheid, makelaar_details, toegevoegd_door)
                            VALUES (%s, %s, %s, %s, %s, %s)
                        """
                        cur.execute(insert_sql, (speler_id, club_info, familie, mentaliteit, makelaar, st.session_state.user_info['naam']))
                    
                    conn.commit()
                    st.success(f"Dossier voor {gekozen_naam} is succesvol bijgewerkt!")
                    st.rerun() # Pagina verversen om nieuwe info te tonen
                except Exception as e:
                    st.error(f"Fout bij opslaan: {e}")
                finally:
                    cur.close()
                    conn.close()

# 4. Historie overzicht (onderaan de pagina)
st.divider()
st.subheader("Recent toegevoegde intelligentie")
recent_query = """
    SELECT p.commonname as Speler, i.toegevoegd_door as Scout, i.laatst_bijgewerkt as Datum
    FROM scouting.speler_intelligence i
    JOIN analysis.players p ON i.speler_id = p.id
    ORDER BY i.laatst_bijgewerkt DESC LIMIT 5
"""
st.dataframe(run_query(recent_query), use_container_width=True)
