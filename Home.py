import streamlit as st
from utils import run_query, init_connection
import pandas as pd

st.title("🧠 Strategisch Speler Dossier")

# --- 0. CACHE RESET ---
# Dit dwingt de app om de nieuwe tabelstructuur te zien
if st.sidebar.button("Update Database Schema"):
    st.cache_data.clear()
    st.success("Cache geleegd! De nieuwe kolommen worden nu gezocht.")
    st.rerun()

# Helper voor spelersdata
def get_players_data():
    query = """
        SELECT p.id, p.commonname, s.name as club_name 
        FROM analysis.players p
        LEFT JOIN analysis.squads s ON p."currentSquadId" = s.id
        ORDER BY p.commonname ASC;
    """
    return run_query(query)

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
        selected_id = "MANUEEL"

    if selected_name:
        check_sql = "SELECT * FROM scouting.speler_intelligence WHERE speler_id = %s"
        params = (selected_id,)
        if selected_id == "MANUEEL":
            check_sql = "SELECT * FROM scouting.speler_intelligence WHERE speler_id = 'MANUEEL' AND custom_naam = %s"
            params = (selected_name,)
            
        existing = run_query(check_sql, params=params)
        heeft_data = not existing.empty
        
        # VEILIGE KOLOM-CHECK (Voorkomt KeyError)
        def get_val(col):
            if heeft_data and col in existing.columns:
                val = existing.iloc[0][col]
                return val if val is not None else ""
            return ""

        with st.form("dossier_form"):
            st.markdown(f"### Bewerken: {selected_name}")
            
            c1, c2 = st.columns(2)
            with c1:
                club_info = st.text_area("Club / Netwerk Info", value=get_val('club_informatie'))
                familie = st.text_area("Familie & Omgeving", value=get_val('familie_achtergrond'))
            with c2:
                mentaliteit = st.text_area("Persoonlijkheid & Mentaliteit", value=get_val('persoonlijkheid'))
                makelaar = st.text_area("Makelaar & Contract", value=get_val('makelaar_details'))
            
            st.markdown("---")
            st.markdown("🔗 **Social Media & Externe Links**")
            l1, l2 = st.columns(2)
            with l1:
                insta = st.text_input("Instagram URL", value=get_val('instagram_url'), placeholder="https://instagram.com/...")
                twitter = st.text_input("Twitter / X URL", value=get_val('twitter_url'), placeholder="https://x.com/...")
            with l2:
                tm = st.text_input("Transfermarkt URL", value=get_val('transfermarkt_url'), placeholder="https://transfermarkt.com/...")
                overig = st.text_input("Overige Link", value=get_val('overige_url'))

            # De knop MOET in de st.form staan
            if st.form_submit_button("Dossier Opslaan"):
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
                        cur.execute(sql, (selected_id, club_info, familie, mentaliteit, makelaar, insta, twitter, tm, overig, scout, 
                                          selected_name if selected_id == "MANUEEL" else None))
                    conn.commit()
                    st.success("Opgeslagen!")
                    st.cache_data.clear()
                    st.rerun()
                except Exception as e: st.error(f"Fout: {e}")
                finally: cur.close(); conn.close()

# -----------------------------------------------------------------------------
# TAB 2: OVERZICHT & ZOEKEN
# -----------------------------------------------------------------------------
with tab2:
    st.subheader("Dossier Bibliotheek")
    
    all_data_sql = """
        SELECT i.*, COALESCE(p.commonname, i.custom_naam) as speler_naam, s.name as club
        FROM scouting.speler_intelligence i
        LEFT JOIN analysis.players p ON i.speler_id = p.id
        LEFT JOIN analysis.squads s ON p."currentSquadId" = s.id
        ORDER BY i.laatst_bijgewerkt DESC
    """
    df_all = run_query(all_data_sql)
    
    if not df_all.empty:
        search = st.text_input("🔍 Filter op naam:").lower()
        df_display = df_all[df_all['speler_naam'].str.lower().str.contains(search, na=False)]
        
        # Weergeven van basis info in tabel
        selection = st.dataframe(
            df_display[['speler_naam', 'club', 'toegevoegd_door', 'laatst_bijgewerkt']],
            use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row"
        )
        
        if selection and selection.selection.rows:
            dossier = df_display.iloc[selection.selection.rows[0]]
            
            st.divider()
            st.markdown(f"### 📖 {dossier['speler_naam']}")
            st.caption(f"🗓️ Laatste wijziging: {dossier['laatst_bijgewerkt']} | Scout: {dossier['toegevoegd_door']}")
            
            # Toon links alleen als de kolommen bestaan in de resultaten
            st.markdown("#### 🔗 Links")
            sl1, sl2, sl3, sl4 = st.columns(4)
            with sl1: 
                if 'instagram_url' in dossier and dossier['instagram_url']: st.link_button("📸 Instagram", dossier['instagram_url'])
            with sl2: 
                if 'twitter_url' in dossier and dossier['twitter_url']: st.link_button("🐦 Twitter / X", dossier['twitter_url'])
            with sl3: 
                if 'transfermarkt_url' in dossier and dossier['transfermarkt_url']: st.link_button("⚽ Transfermarkt", dossier['transfermarkt_url'])
            with sl4: 
                if 'overige_url' in dossier and dossier['overige_url']: st.link_button("🔗 Overig", dossier['overige_url'])

            st.markdown("---")
            c_a, c_b = st.columns(2)
            with c_a:
                st.info("**Club Info**")
                st.write(dossier['club_informatie'] or "-")
                st.info("**Familie**")
                st.write(dossier['familie_achtergrond'] or "-")
            with c_b:
                st.warning("**Persoonlijkheid**")
                st.write(dossier['persoonlijkheid'] or "-")
                st.error("**Makelaar**")
                st.write(dossier['makelaar_details'] or "-")
    else:
        st.write("Geen dossiers gevonden.")
