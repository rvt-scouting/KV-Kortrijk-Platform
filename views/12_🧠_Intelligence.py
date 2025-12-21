import streamlit as st
import pandas as pd
from utils import run_query, init_connection

# -----------------------------------------------------------------------------
# 1. SETUP & SESSION STATE
# -----------------------------------------------------------------------------
# We gebruiken session_state om te onthouden of we in de 'bewerk-modus' zitten in Tab 2
if 'edit_mode_tab2' not in st.session_state:
    st.session_state.edit_mode_tab2 = False

st.title("🧠 Strategisch Speler Dossier")

# Helper voor het ophalen van de basis spelerslijst (voor de selectbox in Tab 1)
def get_base_players():
    query = """
        SELECT p.id, p.commonname, s.name as club_name 
        FROM analysis.players p
        LEFT JOIN analysis.squads s ON p."currentSquadId"::text = s.id::text
        ORDER BY p.commonname ASC;
    """
    return run_query(query)

# Tabs definiëren
tab1, tab2 = st.tabs(["📝 Dossier Beheer (Nieuw/Update)", "📖 Dossier Bibliotheek"])

# -----------------------------------------------------------------------------
# TAB 1: DOSSIER BEHEER (Invoeren & Snelle Update)
# -----------------------------------------------------------------------------
with tab1:
    st.subheader("Selecteer een speler om een dossier te starten of bij te werken")
    methode = st.radio("Bron:", ["Database", "Handmatige Invoer"], horizontal=True, key="radio_tab1")
    
    selected_id, selected_name = None, ""
    
    if methode == "Database":
        df_db = get_base_players()
        if not df_db.empty:
            df_db['display'] = df_db.apply(lambda x: f"{x['commonname']} ({x['club_name'] if x['club_name'] else 'Geen club'})", axis=1)
            keuze = st.selectbox("Zoek speler uit database:", ["Selecteer..."] + df_db['display'].tolist())
            if keuze != "Selecteer...":
                row = df_db[df_db['display'] == keuze].iloc[0]
                selected_id, selected_name = str(row['id']), row['commonname']
    else:
        selected_name = st.text_input("Naam van de nieuwe speler (Manueel):")
        selected_id = "MANUEEL"

    if selected_name:
        # Check direct in de DB of er al data is (zonder cache!)
        conn_check = init_connection()
        if selected_id == "MANUEEL":
            check_sql = "SELECT * FROM scouting.speler_intelligence WHERE speler_id = 'MANUEEL' AND custom_naam = %s"
            params = (selected_name,)
        else:
            check_sql = "SELECT * FROM scouting.speler_intelligence WHERE speler_id = %s"
            params = (selected_id,)
        
        existing_data = pd.read_sql(check_sql, conn_check, params=params)
        conn_check.close()
        
        heeft_data = not existing_data.empty
        current = existing_data.iloc[0] if heeft_data else None

        with st.form("dossier_form_tab1"):
            st.markdown(f"### {'Bewerken' if heeft_data else 'Nieuw dossier'}: {selected_name}")
            
            c1, c2 = st.columns(2)
            with c1:
                club_info = st.text_area("Club / Netwerk Info", value=current['club_informatie'] if heeft_data else "")
                familie = st.text_area("Familie & Omgeving", value=current['familie_achtergrond'] if heeft_data else "")
            with c2:
                mentaliteit = st.text_area("Persoonlijkheid & Mentaliteit", value=current['persoonlijkheid'] if heeft_data else "")
                makelaar = st.text_area("Makelaar & Contract", value=current['makelaar_details'] if heeft_data else "")
            
            st.markdown("🔗 **Links**")
            l1, l2, l3, l4 = st.columns(4)
            insta = l1.text_input("Instagram", value=current['instagram_url'] if heeft_data else "")
            twitter = l2.text_input("Twitter", value=current['twitter_url'] if heeft_data else "")
            tm = l3.text_input("Transfermarkt", value=current['transfermarkt_url'] if heeft_data else "")
            overig = l4.text_input("Overige Link", value=current['overige_url'] if heeft_data else "")

            if st.form_submit_button("💾 Dossier Opslaan"):
                scout_naam = st.session_state.user_info.get('naam', 'Onbekend')
                conn = init_connection()
                cur = conn.cursor()
                try:
                    if heeft_data:
                        sql = """UPDATE scouting.speler_intelligence 
                                 SET club_informatie=%s, familie_achtergrond=%s, persoonlijkheid=%s, 
                                     makelaar_details=%s, instagram_url=%s, twitter_url=%s, 
                                     transfermarkt_url=%s, overige_url=%s, toegevoegd_door=%s, laatst_bijgewerkt=NOW() 
                                 WHERE id=%s"""
                        cur.execute(sql, (club_info, familie, mentaliteit, makelaar, insta, twitter, tm, overig, scout_naam, int(current['id'])))
                    else:
                        sql = """INSERT INTO scouting.speler_intelligence 
                                 (speler_id, club_informatie, familie_achtergrond, persoonlijkheid, 
                                  makelaar_details, instagram_url, twitter_url, transfermarkt_url, 
                                  overige_url, toegevoegd_door, custom_naam) 
                                 VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
                        cur.execute(sql, (selected_id, club_info, familie, mentaliteit, makelaar, insta, twitter, tm, overig, scout_naam, 
                                          selected_name if selected_id == "MANUEEL" else None))
                    conn.commit()
                    st.cache_data.clear() # BELANGRIJK: Leeg de cache zodat Tab 2 de nieuwe data ziet
                    st.success("Opgeslagen!")
                    st.rerun()
                except Exception as e: st.error(f"Fout: {e}")
                finally: cur.close(); conn.close()

# -----------------------------------------------------------------------------
# TAB 2: OVERZICHT & ZOEKEN (De 'Reader' & Editor)
# -----------------------------------------------------------------------------
with tab2:
    st.subheader("Dossier Bibliotheek")
    
    all_data_sql = """
        SELECT i.*, 
               COALESCE(p.commonname, i.custom_naam) as speler_naam, 
               s.name as club
        FROM scouting.speler_intelligence i
        LEFT JOIN analysis.players p ON i.speler_id::text = p.id::text
        LEFT JOIN analysis.squads s ON p."currentSquadId"::text = s.id::text
        ORDER BY i.laatst_bijgewerkt DESC
    """
    df_all = run_query(all_data_sql)
    
    if not df_all.empty:
        search = st.text_input("🔍 Filter op naam:", key="search_tab2").lower()
        df_display = df_all[df_all['speler_naam'].str.lower().str.contains(search, na=False)].copy()
        
        selection = st.dataframe(
            df_display[['speler_naam', 'club', 'toegevoegd_door', 'laatst_bijgewerkt']],
            use_container_width=True, hide_index=True, on_select="rerun", selection_mode="single-row", key="table_tab2"
        )
        
        if selection and selection.selection.rows:
            dossier = df_display.iloc[selection.selection.rows[0]]
            
            st.divider()
            col_header, col_btn = st.columns([3, 1])
            with col_header:
                st.markdown(f"## 📖 {dossier['speler_naam']}")
            with col_btn:
                if st.button("✏️ Dossier Bewerken", use_container_width=True):
                    st.session_state.edit_mode_tab2 = True

            if st.session_state.edit_mode_tab2:
                # --- BEWERK MODUS ---
                with st.form("edit_form_tab2"):
                    c1, c2 = st.columns(2)
                    edit_club = c1.text_area("Club Info", value=dossier['club_informatie'] or "")
                    edit_fam = c1.text_area("Familie", value=dossier['familie_achtergrond'] or "")
                    edit_pers = c2.text_area("Persoonlijkheid", value=dossier['persoonlijkheid'] or "")
                    edit_mak = c2.text_area("Makelaar", value=dossier['makelaar_details'] or "")
                    
                    if st.form_submit_button("💾 Wijzigingen Opslaan"):
                        conn = init_connection(); cur = conn.cursor()
                        try:
                            cur.execute("""UPDATE scouting.speler_intelligence SET club_informatie=%s, familie_achtergrond=%s, 
                                           persoonlijkheid=%s, makelaar_details=%s, laatst_bijgewerkt=NOW() WHERE id=%s""",
                                        (edit_club, edit_fam, edit_pers, edit_mak, int(dossier['id'])))
                            conn.commit()
                            st.cache_data.clear()
                            st.session_state.edit_mode_tab2 = False
                            st.success("Bijgewerkt!")
                            st.rerun()
                        except Exception as e: st.error(e)
                        finally: cur.close(); conn.close()
                if st.button("❌ Annuleren"):
                    st.session_state.edit_mode_tab2 = False
                    st.rerun()
            else:
                # --- READER MODUS ---
                st.markdown(f"""<div style="background-color: #f8f9fa; padding: 15px; border-left: 8px solid #d71920; border-radius: 5px;">
                    <p style="margin:0;">🗓️ <strong>Laatst gewijzigd:</strong> {pd.to_datetime(dossier['laatst_bijgewerkt']).strftime('%d-%m-%Y %H:%M')} | 👤 <strong>Scout:</strong> {dossier['toegevoegd_door']}</p>
                </div>""", unsafe_allow_html=True)
                
                st.markdown("<br>", unsafe_allow_html=True)
                sl1, sl2, sl3, sl4 = st.columns(4)
                if dossier['instagram_url']: sl1.link_button("📸 Instagram", dossier['instagram_url'], use_container_width=True)
                if dossier['twitter_url']: sl2.link_button("🐦 Twitter / X", dossier['twitter_url'], use_container_width=True)
                if dossier['transfermarkt_url']: sl3.link_button("⚽ Transfermarkt", dossier['transfermarkt_url'], use_container_width=True)
                if dossier['overige_url']: sl4.link_button("🔗 Overig", dossier['overige_url'], use_container_width=True)

                st.markdown("---")
                ca, cb = st.columns(2)
                ca.info("**Club Info**"); ca.write(dossier['club_informatie'] or "Geen data")
                ca.info("**Familie**"); ca.write(dossier['familie_achtergrond'] or "Geen data")
                cb.warning("**Persoonlijkheid**"); cb.write(dossier['persoonlijkheid'] or "Geen data")
                cb.error("**Makelaar**"); cb.write(dossier['makelaar_details'] or "Geen data")
    else:
        st.info("Geen dossiers gevonden.")
