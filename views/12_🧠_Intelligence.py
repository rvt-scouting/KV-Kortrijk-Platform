import streamlit as st
from utils import run_query, init_connection
import pandas as pd

st.title("🧠 Strategisch Speler Dossier")

# --- HELPER FUNCTIES ---
def get_players_data():
    # We voegen een unieke key toe of we zorgen dat deze query ververst wordt
    query = """
        SELECT p.id, p.commonname, s.name as club_name 
        FROM analysis.players p
        LEFT JOIN analysis.squads s ON p."currentSquadId" = s.id
        ORDER BY p.commonname ASC;
    """
    return run_query(query)

# --- TABS ---
tab1, tab2 = st.tabs(["📝 Dossier Beheer", "📖 Overzicht & Zoeken"])

# -----------------------------------------------------------------------------
# TAB 1: DOSSIER BEHEER
# -----------------------------------------------------------------------------
with tab1:
    st.subheader("Selecteer een speler")
    methode = st.radio("Bron:", ["Database", "Handmatige Invoer"], horizontal=True)
    
    selected_id, selected_name = None, ""
    
    if methode == "Database":
        df_db = get_players_data()
        if not df_db.empty:
            df_db['display'] = df_db.apply(lambda x: f"{x['commonname']} ({x['club_name'] if x['club_name'] else 'Geen club'})", axis=1)
            keuze = st.selectbox("Zoek speler:", ["Selecteer..."] + df_db['display'].tolist())
            if keuze != "Selecteer...":
                row = df_db[df_db['display'] == keuze].iloc[0]
                selected_id, selected_name = row['id'], row['commonname']
    else:
        selected_name = st.text_input("Naam van de nieuwe speler:")
        # Gebruik None of een specifieke code die je database aankan
        selected_id = None 

    if selected_name:
        # LET OP: We gebruiken hier GEEN run_query voor de check, omdat run_query gecached is!
        # Voor dossier-checks willen we ALTIJD de laatste status.
        conn_check = init_connection()
        if selected_id:
            check_sql = "SELECT * FROM scouting.speler_intelligence WHERE speler_id = %s"
            params = (str(selected_id),)
        else:
            check_sql = "SELECT * FROM scouting.speler_intelligence WHERE custom_naam = %s"
            params = (selected_name,)
        
        existing = pd.read_sql(check_sql, conn_check, params=params)
        conn_check.close()
        
        heeft_data = not existing.empty
        
        with st.form("dossier_form", clear_on_submit=False):
            st.markdown(f"### Bewerken: {selected_name}")
            
            # Formulier velden (ingevuld met bestaande data indien aanwezig)
            c1, c2 = st.columns(2)
            with c1:
                club_info = st.text_area("Club / Netwerk Info", value=existing.iloc[0]['club_informatie'] if heeft_data else "")
                familie = st.text_area("Familie & Omgeving", value=existing.iloc[0]['familie_achtergrond'] if heeft_data else "")
            with c2:
                mentaliteit = st.text_area("Persoonlijkheid & Mentaliteit", value=existing.iloc[0]['persoonlijkheid'] if heeft_data else "")
                makelaar = st.text_area("Makelaar & Contract", value=existing.iloc[0]['makelaar_details'] if heeft_data else "")
            
            st.markdown("---")
            st.markdown("🔗 **Social Media & Externe Links**")
            l1, l2 = st.columns(2)
            with l1:
                insta = st.text_input("Instagram URL", value=existing.iloc[0]['instagram_url'] if heeft_data else "")
                twitter = st.text_input("Twitter / X URL", value=existing.iloc[0]['twitter_url'] if heeft_data else "")
            with l2:
                tm = st.text_input("Transfermarkt URL", value=existing.iloc[0]['transfermarkt_url'] if heeft_data else "")
                overig = st.text_input("Overige Link", value=existing.iloc[0]['overige_url'] if heeft_data else "")

            if st.form_submit_button("💾 Dossier Opslaan"):
                scout = st.session_state.user_info.get('naam', 'Onbekend')
                conn = init_connection()
                cur = conn.cursor()
                try:
                    if heeft_data:
                        sql = """UPDATE scouting.speler_intelligence 
                                 SET club_informatie=%s, familie_achtergrond=%s, persoonlijkheid=%s, 
                                     makelaar_details=%s, instagram_url=%s, twitter_url=%s, 
                                     transfermarkt_url=%s, overige_url=%s, toegevoegd_door=%s, laatst_bijgewerkt=NOW() 
                                 WHERE id=%s"""
                        cur.execute(sql, (club_info, familie, mentaliteit, makelaar, insta, twitter, tm, overig, scout, int(existing.iloc[0]['id'])))
                    else:
                        sql = """INSERT INTO scouting.speler_intelligence 
                                 (speler_id, club_informatie, familie_achtergrond, persoonlijkheid, 
                                  makelaar_details, instagram_url, twitter_url, transfermarkt_url, 
                                  overige_url, toegevoegd_door, custom_naam) 
                                 VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
                        cur.execute(sql, (str(selected_id) if selected_id else None, club_info, familie, mentaliteit, makelaar, insta, twitter, tm, overig, scout, selected_name))
                    
                    conn.commit()
                    
                    # --- CRUCIAAL: CACHE LEGEN ---
                    st.cache_data.clear() 
                    
                    st.success(f"Dossier van {selected_name} succesvol opgeslagen!")
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
    st.subheader("Dossier Bibliotheek")
    
    # Handige refresh knop voor de zekerheid
    if st.button("🔄 Forceer Refresh"):
        st.cache_data.clear()
        st.rerun()

    all_data_sql = """
        SELECT i.*, COALESCE(p.commonname, i.custom_naam) as speler_naam, s.name as club
        FROM scouting.speler_intelligence i
        LEFT JOIN analysis.players p ON i.speler_id::text = p.id::text
        LEFT JOIN analysis.squads s ON p."currentSquadId" = s.id
        ORDER BY i.laatst_bijgewerkt DESC
    """
    df_all = run_query(all_data_sql)
    
    if not df_all.empty:
        search = st.text_input("🔍 Filter op naam:").lower()
        df_display = df_all[df_all['speler_naam'].str.lower().str.contains(search, na=False)].copy()
        
        # Gebruik st.dataframe met selectie
        selection = st.dataframe(
            df_display[['speler_naam', 'club', 'toegevoegd_door', 'laatst_bijgewerkt']],
            use_container_width=True, 
            hide_index=True, 
            on_select="rerun", 
            selection_mode="single-row"
        )
        
        if selection and selection.selection.rows:
            idx = selection.selection.rows[0]
            dossier = df_display.iloc[idx]
            
            # --- WEERGAVE ---
            st.divider()
            st.markdown(f"## 📖 {dossier['speler_naam']}")
            # ... rest van je mooie weergave code ...
