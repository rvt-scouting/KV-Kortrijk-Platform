import streamlit as st
from utils import run_query, init_connection
import pandas as pd

st.title("🧠 Strategisch Speler Dossier")

# --- 0. CACHE RESET (Voeg dit tijdelijk toe als de error blijft) ---
if st.button("🔄 Cache vernieuwen (bij database wijzigingen)"):
    st.cache_data.clear()
    st.rerun()

# --- 1. HELPER FUNCTIES ---
def get_players_dropdown():
    # Haal spelers en clubs op uit het analysis schema 
    query = """
        SELECT p.id, p.commonname, s.name as club_name 
        FROM analysis.players p
        LEFT JOIN analysis.squads s ON p."currentSquadId" = s.id
        ORDER BY p.commonname ASC;
    """
    return run_query(query)

# --- 2. TABS ---
tab1, tab2 = st.tabs(["📝 Dossier Beheer", "📖 Dossiers Inzien"])

# -----------------------------------------------------------------------------
# TAB 1: DOSSIER BEHEER (INVOEREN & AANPASSEN)
# -----------------------------------------------------------------------------
with tab1:
    st.subheader("Selectie voor invoer of aanpassing")
    methode = st.radio("Speler zoeken via:", ["Database", "Handmatige Invoer"], horizontal=True)
    
    gekozen_id, gekozen_naam = None, ""

    if methode == "Database":
        df_players = get_players_dropdown()
        if not df_players.empty:
            df_players['display'] = df_players.apply(lambda x: f"{x['commonname']} ({x['club_name'] if x['club_name'] else 'Geen Club'})", axis=1)
            sel = st.selectbox("Selecteer speler:", ["Zoek speler..."] + df_players['display'].tolist())
            if sel != "Zoek speler...":
                row = df_players[df_players['display'] == sel].iloc[0]
                gekozen_id, gekozen_naam = row['id'], row['commonname']
    else:
        gekozen_naam = st.text_input("Naam nieuwe speler (Manueel):")
        gekozen_id = "MANUEEL"

    if gekozen_naam:
        # Check op bestaand dossier
        query_check = "SELECT * FROM scouting.speler_intelligence WHERE speler_id = %s"
        params = (gekozen_id,) if gekozen_id != "MANUEEL" else None
        if gekozen_id == "MANUEEL":
            query_check = "SELECT * FROM scouting.speler_intelligence WHERE speler_id = 'MANUEEL' AND custom_naam = %s"
            params = (gekozen_naam,)
            
        df_exist = run_query(query_check, params=params)
        heeft_data = not df_exist.empty

        with st.form("dossier_form"):
            st.write(f"Dossier: **{gekozen_naam}**")
            c1, c2 = st.columns(2)
            with c1:
                club_info = st.text_area("Netwerk & Club Info", value=df_exist.iloc[0]['club_informatie'] if heeft_data else "")
                familie = st.text_area("Familie & Omgeving", value=df_exist.iloc[0]['familie_achtergrond'] if heeft_data else "")
            with c2:
                mentaliteit = st.text_area("Persoonlijkheid & Mentaliteit", value=df_exist.iloc[0]['persoonlijkheid'] if heeft_data else "")
                makelaar = st.text_area("Makelaar & Contract", value=df_exist.iloc[0]['makelaar_details'] if heeft_data else "")
            
            if st.form_submit_button("Opslaan / Bijwerken"):
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
                        sql = """INSERT INTO scouting.speler_intelligence (speler_id, club_informatie, familie_achtergrond, 
                                 persoonlijkheid, makelaar_details, toegevoegd_door, custom_naam) 
                                 VALUES (%s, %s, %s, %s, %s, %s, %s)"""
                        cur.execute(sql, (gekozen_id, club_info, familie, mentaliteit, makelaar, scout, 
                                          gekozen_naam if gekozen_id == "MANUEEL" else None))
                    conn.commit()
                    st.success("Dossier bijgewerkt!")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e: st.error(f"Fout: {e}")
                finally: cur.close(); conn.close()

# -----------------------------------------------------------------------------
# TAB 2: DOSSIERS INZIEN (READER)
# -----------------------------------------------------------------------------
with tab2:
    st.subheader("Dossier Bibliotheek")
    
    # Gebruik exact de kolomnamen zoals ze in de DB staan (custom_naam met een 'u')
    query_all = """
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
    df_all = run_query(query_all)
    
    if not df_all.empty:
        search = st.text_input("🔍 Filter op naam of club:").lower()
        df_filtered = df_all[df_all['speler_naam'].str.lower().str.contains(search, na=False) | 
                             df_all['club'].str.lower().str.contains(search, na=False)]
        
        # Interactieve tabel voor selectie
        st.write("Selecteer een rij om het dossier te lezen:")
        selection = st.dataframe(
            df_filtered[['speler_naam', 'club', 'scout', 'laatst_bijgewerkt']],
            use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row"
        )
        
        if selection and selection.selection.rows:
            row = df_filtered.iloc[selection.selection.rows[0]]
            st.divider()
            st.markdown(f"## 📖 Dossier: {row['speler_naam']}")
            
            c_a, c_b = st.columns(2)
            with c_a:
                st.info("**Club Info & Netwerk**")
                st.write(row['club_informatie'] or "Geen data")
                st.info("**Familie & Achtergrond**")
                st.write(row['familie_achtergrond'] or "Geen data")
            with c_b:
                st.warning("**Mentaliteit & Karakter**")
                st.write(row['persoonlijkheid'] or "Geen data")
                st.error("**Makelaar & Contract**")
                st.write(row['makelaar_details'] or "Geen data")
    else:
        st.info("Nog geen dossiers gevonden.")
