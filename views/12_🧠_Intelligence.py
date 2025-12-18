import streamlit as st
from utils import run_query, init_connection
import pandas as pd

st.title("🧠 Strategisch Speler Dossier")

# Helper voor het ophalen van spelersdata inclusief clubnamen
def get_players_data():
    query = """
        SELECT p.id, p.commonname, s.name as club_name 
        FROM analysis.players p
        LEFT JOIN analysis.squads s ON p."currentSquadId" = s.id
        ORDER BY p.commonname ASC;
    """
    return run_query(query)

# Tabs voor Dossier Beheer en Inzien
tab1, tab2 = st.tabs(["📝 Dossier Beheer", "📖 Overzicht & Zoeken"])

# -----------------------------------------------------------------------------
# TAB 1: DOSSIER BEHEER (Invoeren & Aanpassen)
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
        # Zoek bestaand dossier
        check_sql = "SELECT * FROM scouting.speler_intelligence WHERE speler_id = %s"
        params = (selected_id,)
        if selected_id == "MANUEEL":
            check_sql = "SELECT * FROM scouting.speler_intelligence WHERE speler_id = 'MANUEEL' AND custom_naam = %s"
            params = (selected_name,)
            
        existing = run_query(check_sql, params=params)
        heeft_data = not existing.empty
        
        with st.form("dossier_form"):
            st.markdown(f"### Bewerken: {selected_name}")
            
            # Sectie 1: Tekstuele Info
            c1, c2 = st.columns(2)
            with c1:
                club_info = st.text_area("Club / Netwerk Info", value=existing.iloc[0]['club_informatie'] if heeft_data else "")
                familie = st.text_area("Familie & Omgeving", value=existing.iloc[0]['familie_achtergrond'] if heeft_data else "")
            with c2:
                mentaliteit = st.text_area("Persoonlijkheid & Mentaliteit", value=existing.iloc[0]['persoonlijkheid'] if heeft_data else "")
                makelaar = st.text_area("Makelaar & Contract", value=existing.iloc[0]['makelaar_details'] if heeft_data else "")
            
            # Sectie 2: Sociale Media & Links
            st.markdown("---")
            st.markdown("🔗 **Social Media & Externe Links**")
            l1, l2 = st.columns(2)
            with l1:
                insta = st.text_input("Instagram URL", value=existing.iloc[0]['instagram_url'] if heeft_data else "", placeholder="https://instagram.com/...")
                twitter = st.text_input("Twitter / X URL", value=existing.iloc[0]['twitter_url'] if heeft_data else "", placeholder="https://x.com/...")
            with l2:
                tm = st.text_input("Transfermarkt URL", value=existing.iloc[0]['transfermarkt_url'] if heeft_data else "", placeholder="https://transfermarkt.com/...")
                overig = st.text_input("Overige Link (Video's, etc.)", value=existing.iloc[0]['overige_url'] if heeft_data else "")

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
                    st.rerun()
                except Exception as e: st.error(f"Fout: {e}")
                finally: cur.close(); conn.close()

# -----------------------------------------------------------------------------
# TAB 2: OVERZICHT & ZOEKEN (Reader)
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
        
        selection = st.dataframe(
            df_display[['speler_naam', 'club', 'toegevoegd_door', 'laatst_bijgewerkt']],
            use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row"
        )
        
        if selection and selection.selection.rows:
            dossier = df_display.iloc[selection.selection.rows[0]]
            
            # --- HOOFDWEERGAVE DOSSIER ---
            st.divider()
            
            # HEADER MET LAATSTE WIJZIGING (Duidelijk zichtbaar)
            st.markdown(f"""
                <div style="background-color: #f8f9fa; padding: 20px; border-left: 10px solid #d71920; border-radius: 5px;">
                    <h1 style="margin:0;">📖 {dossier['speler_naam']}</h1>
                    <p style="color: #666; font-size: 14px; margin-top: 5px;">
                        🗓️ <strong>Laatste wijziging:</strong> {pd.to_datetime(dossier['laatst_bijgewerkt']).strftime('%d-%m-%Y om %H:%M')} 
                        &nbsp;&nbsp; | &nbsp;&nbsp; 👤 <strong>Scout:</strong> {dossier['toegevoegd_door']}
                    </p>
                </div>
            """, unsafe_allow_html=True)
            
            # SOCIAL MEDIA LINKS
            st.markdown("#### 🔗 Links")
            sl1, sl2, sl3, sl4 = st.columns(4)
            with sl1: 
                if dossier['instagram_url']: st.link_button("📸 Instagram", dossier['instagram_url'], use_container_width=True)
            with sl2: 
                if dossier['twitter_url']: st.link_button("🐦 Twitter / X", dossier['twitter_url'], use_container_width=True)
            with sl3: 
                if dossier['transfermarkt_url']: st.link_button("⚽ Transfermarkt", dossier['transfermarkt_url'], use_container_width=True)
            with sl4: 
                if dossier['overige_url']: st.link_button("🔗 Overig", dossier['overige_url'], use_container_width=True)

            # DETAILS
            st.markdown("---")
            c_a, c_b = st.columns(2)
            with c_a:
                st.info("**Club Info**")
                st.write(dossier['club_informatie'] or "Geen data")
                st.info("**Familie**")
                st.write(dossier['familie_achtergrond'] or "Geen data")
            with c_b:
                st.warning("**Persoonlijkheid**")
                st.write(dossier['persoonlijkheid'] or "Geen data")
                st.error("**Makelaar**")
                st.write(dossier['makelaar_details'] or "Geen data")
    else:
        st.write("Geen dossiers gevonden.")
