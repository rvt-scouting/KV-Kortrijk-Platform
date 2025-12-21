import streamlit as st
import pandas as pd
from utils import run_query, init_connection

# --- INITIALISATIE ---
# Zorg dat de edit_mode altijd gedefinieerd is in de sessie
if 'edit_mode' not in st.session_state:
    st.session_state.edit_mode = False

st.subheader("Dossier Bibliotheek")

# 1. DATA OPHALEN
# We casten de ID's naar text om joins tussen verschillende types te voorkomen
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
    # 2. ZOEKEN & FILTEREN
    search = st.text_input("🔍 Filter op naam:").lower()
    df_display = df_all[df_all['speler_naam'].str.lower().str.contains(search, na=False)].copy()
    
    # 3. INTERACTIEVE TABEL
    selection = st.dataframe(
        df_display[['speler_naam', 'club', 'toegevoegd_door', 'laatst_bijgewerkt']],
        use_container_width=True, 
        hide_index=True, 
        on_select="rerun", 
        selection_mode="single-row"
    )
    
    # 4. ACTIE OP SELECTIE
    if selection and selection.selection.rows:
        # Haal de specifieke rij op uit de gefilterde dataframe
        selected_index = selection.selection.rows[0]
        dossier = df_display.iloc[selected_index]
        
        st.divider()

        # Knoppenbalk voor acties
        col_title, col_edit = st.columns([3, 1])
        with col_title:
            st.markdown(f"## 📖 {dossier['speler_naam']}")
        with col_edit:
            if st.button("✏️ Dossier Bewerken", use_container_width=True):
                st.session_state.edit_mode = True

        # --- MODUS: BEWERKEN ---
        if st.session_state.edit_mode:
            st.warning(f"Je bewerkt nu het dossier van **{dossier['speler_naam']}**.")
            
            with st.form("edit_dossier_form_tab2"):
                c1, c2 = st.columns(2)
                with c1:
                    edit_club = st.text_area("Club / Netwerk Info", value=dossier['club_informatie'] or "")
                    edit_familie = st.text_area("Familie & Omgeving", value=dossier['familie_achtergrond'] or "")
                with c2:
                    edit_mentaliteit = st.text_area("Persoonlijkheid & Mentaliteit", value=dossier['persoonlijkheid'] or "")
                    edit_makelaar = st.text_area("Makelaar & Contract", value=dossier['makelaar_details'] or "")
                
                st.markdown("🔗 **Links**")
                l1, l2, l3, l4 = st.columns(4)
                edit_insta = l1.text_input("Instagram", value=dossier['instagram_url'] or "")
                edit_twitter = l2.text_input("Twitter / X", value=dossier['twitter_url'] or "")
                edit_tm = l3.text_input("Transfermarkt", value=dossier['transfermarkt_url'] or "")
                edit_overig = l4.text_input("Overig", value=dossier['overige_url'] or "")

                col_save, col_cancel = st.columns(2)
                submit = st.form_submit_button("💾 Wijzigingen Opslaan", use_container_width=True)

                if submit:
                    conn = init_connection()
                    cur = conn.cursor()
                    try:
                        sql_update = """
                            UPDATE scouting.speler_intelligence 
                            SET club_informatie=%s, familie_achtergrond=%s, persoonlijkheid=%s, 
                                makelaar_details=%s, instagram_url=%s, twitter_url=%s, 
                                transfermarkt_url=%s, overige_url=%s, 
                                laatst_bijgewerkt=NOW() 
                            WHERE id=%s
                        """
                        cur.execute(sql_update, (
                            edit_club, edit_familie, edit_mentaliteit, 
                            edit_makelaar, edit_insta, edit_twitter, 
                            edit_tm, edit_overig, int(dossier['id'])
                        ))
                        conn.commit()
                        st.cache_data.clear()  # Cruciaal voor refresh!
                        st.session_state.edit_mode = False
                        st.success("Wijzigingen opgeslagen!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Fout bij opslaan: {e}")
                    finally:
                        cur.close(); conn.close()
            
            if st.button("❌ Annuleren"):
                st.session_state.edit_mode = False
                st.rerun()

        # --- MODUS: LEZEN (Reader View) ---
        else:
            # Header met styling
            st.markdown(f"""
                <div style="background-color: #f8f9fa; padding: 15px; border-left: 8px solid #d71920; border-radius: 5px;">
                    <p style="color: #666; font-size: 14px; margin: 0;">
                        🗓️ <strong>Laatste wijziging:</strong> {pd.to_datetime(dossier['laatst_bijgewerkt']).strftime('%d-%m-%Y om %H:%M')} 
                        &nbsp;&nbsp; | &nbsp;&nbsp; 👤 <strong>Scout:</strong> {dossier['toegevoegd_door']}
                    </p>
                </div>
            """, unsafe_allow_html=True)
            
            # Social Media Knoppen
            st.markdown("<br>", unsafe_allow_html=True)
            sl1, sl2, sl3, sl4 = st.columns(4)
            with sl1: 
                if dossier['instagram_url']: st.link_button("📸 Instagram", dossier['instagram_url'], use_container_width=True)
            with sl2: 
                if dossier['twitter_url']: st.link_button("🐦 Twitter / X", dossier['twitter_url'], use_container_width=True)
            with sl3: 
                if dossier['transfermarkt_url']: st.link_button("⚽ Transfermarkt", dossier['transfermarkt_url'], use_container_width=True)
            with sl4: 
                if dossier['overige_url']: st.link_button("🔗 Overig", dossier['overige_url'], use_container_width=True)

            # Details Sectie
            st.markdown("---")
            c_a, c_b = st.columns(2)
            with c_a:
                st.info("**Club Info**")
                st.write(dossier['club_informatie'] or "*Geen data beschikbaar*")
                st.info("**Familie & Achtergrond**")
                st.write(dossier['familie_achtergrond'] or "*Geen data beschikbaar*")
            with c_b:
                st.warning("**Persoonlijkheid & Mentaliteit**")
                st.write(dossier['persoonlijkheid'] or "*Geen data beschikbaar*")
                st.error("**Makelaar & Contract**")
                st.write(dossier['makelaar_details'] or "*Geen data beschikbaar*")

else:
    st.info("Er zijn nog geen dossiers aangemaakt. Ga naar 'Dossier Beheer' om de eerste speler toe te voegen.")
