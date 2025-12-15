import streamlit as st
import pandas as pd
from utils import run_query, init_connection

st.set_page_config(page_title="Shortlist Manager", page_icon="🎯", layout="wide")

if 'user_info' not in st.session_state or not st.session_state.user_info:
    st.warning("⚠️ Log in AUB."); st.stop()

current_user = st.session_state.user_info.get('naam', 'Onbekend')
current_user_id = st.session_state.user_info.get('id')

st.title("🎯 Shortlist Manager")

# -----------------------------------------------------------------------------
# 1. HELPER: OPSLAAN
# -----------------------------------------------------------------------------
def execute_command(query, params=None):
    conn = None
    try:
        conn = init_connection()
        cur = conn.cursor()
        cur.execute(query, params)
        conn.commit()
        cur.close()
        return True
    except Exception as e:
        st.error(f"DB Fout: {e}")
        return False
    finally:
        if conn: conn.close()

# -----------------------------------------------------------------------------
# 2. SHORTLIST SELECTIE / AANMAKEN
# -----------------------------------------------------------------------------
c1, c2 = st.columns([3, 1])

with c1:
    # Haal lijsten op
    try:
        df_lists = run_query("SELECT id, naam FROM scouting.shortlists ORDER BY id")
        if not df_lists.empty:
            list_opts = {row['naam']: row['id'] for _, row in df_lists.iterrows()}
            selected_list_label = st.selectbox("📂 Selecteer een Shortlist om te beheren:", list(list_opts.keys()))
            selected_list_id = list_opts[selected_list_label]
        else:
            st.info("Nog geen shortlists.")
            selected_list_id = None
    except:
        st.error("Kon shortlists niet laden.")
        selected_list_id = None

with c2:
    # Quick Create
    with st.popover("➕ Nieuwe Lijst"):
        new_list_name = st.text_input("Naam nieuwe lijst")
        if st.button("Aanmaken"):
            if new_list_name:
                q = "INSERT INTO scouting.shortlists (naam, eigenaar_id, aangemaakt_op) VALUES (%s, %s, NOW())"
                if execute_command(q, (new_list_name, current_user_id)):
                    st.success("Gemaakt! Ververs de pagina.")
                    st.rerun()

st.divider()

if selected_list_id:
    tab1, tab2 = st.tabs(["➕ Speler Toevoegen", "📋 Lijst Bekijken"])

    # =========================================================================
    # TAB 1: SPELER TOEVOEGEN
    # =========================================================================
    with tab1:
        st.subheader(f"Speler toevoegen aan: {selected_list_label}")
        
        col_search, col_form = st.columns([1, 2])
        
        # A. ZOEKEN
        with col_search:
            search_txt = st.text_input("🔍 Zoek speler (Database)", placeholder="Naam...")
            found_pid = None
            found_pname = None
            
            if len(search_txt) > 2:
                # Zoek in public.players
                res = run_query("""
                    SELECT p.id, p.commonname, sq.name as team 
                    FROM public.players p 
                    LEFT JOIN public.squads sq ON p."currentSquadId" = sq.id
                    WHERE p.commonname ILIKE %s LIMIT 10
                """, (f"%{search_txt}%",))
                
                if not res.empty:
                    opts = {f"{r['commonname']} ({r['team'] or '?'})": r['id'] for _, r in res.iterrows()}
                    sel = st.radio("Resultaten:", list(opts.keys()))
                    found_pid = opts[sel]
                    found_pname = sel.split(" (")[0]
                else:
                    st.warning("Geen database speler gevonden.")
            
            st.markdown("---")
            use_manual = st.checkbox("Of voeg handmatig een naam toe")
        
        # B. OPSLAAN
        with col_form:
            with st.form("add_entry_form"):
                final_pid = None
                final_custom = None
                
                if use_manual:
                    final_custom = st.text_input("Naam Speler (Handmatig)")
                    st.caption("Gebruik dit voor spelers die nog niet in onze datafeed zitten.")
                elif found_pid:
                    st.success(f"Geselecteerd: **{found_pname}**")
                    final_pid = found_pid
                else:
                    st.info("👈 Zoek en selecteer eerst een speler links.")

                c_prio, c_note = st.columns(2)
                with c_prio:
                    prio = st.selectbox("Prioriteit", ["High", "Medium", "Low"], index=1)
                with c_note:
                    notes = st.text_input("Korte notitie", placeholder="bv. Contract loopt af")
                
                if st.form_submit_button("Toevoegen aan Lijst"):
                    if final_pid or final_custom:
                        # Check dubbel
                        dup_check = run_query(
                            "SELECT id FROM scouting.shortlist_entries WHERE shortlist_id = %s AND player_id = %s", 
                            (selected_list_id, final_pid)
                        ) if final_pid else pd.DataFrame() # Custom namen checken we minder streng
                        
                        if not dup_check.empty:
                            st.error("Deze speler staat al op de lijst!")
                        else:
                            q_ins = """
                                INSERT INTO scouting.shortlist_entries 
                                (shortlist_id, player_id, custom_naam, priority, notities, added_by)
                                VALUES (%s, %s, %s, %s, %s, %s)
                            """
                            if execute_command(q_ins, (selected_list_id, final_pid, final_custom, prio, notes, current_user)):
                                st.success("Toegevoegd!")
                                st.cache_data.clear()
                    else:
                        st.warning("Selecteer een speler of vul een naam in.")

# =========================================================================
    # TAB 2: LIJST BEKIJKEN
    # =========================================================================
    with tab2:
        # Haal entries op
        # FIX: We gebruiken CAST(... AS TEXT) in de JOIN om de integer/text mismatch op te lossen
        q_entries = """
            SELECT 
                e.id,
                COALESCE(p.commonname, e.custom_naam) as "Naam",
                sq.name as "Huidig Team",
                p.birthdate as "Geboortedatum",
                e.priority as "Prio",
                e.notities as "Notitie",
                e.added_by as "Door",
                e.added_at as "Datum"
            FROM scouting.shortlist_entries e
            LEFT JOIN public.players p ON CAST(e.player_id AS TEXT) = CAST(p.id AS TEXT)
            LEFT JOIN public.squads sq ON p."currentSquadId" = sq.id
            WHERE e.shortlist_id = %s
            ORDER BY 
                CASE WHEN e.priority = 'High' THEN 1 WHEN e.priority = 'Medium' THEN 2 ELSE 3 END,
                e.added_at DESC
        """
        df_entries = run_query(q_entries, (selected_list_id,))
        
        if not df_entries.empty:
            # Prio kleuren
            def color_prio(val):
                color = "black"
                if val == "High": color = "#c0392b" # Rood
                elif val == "Medium": color = "#f39c12" # Oranje
                elif val == "Low": color = "#27ae60" # Groen
                return f'color: {color}; font-weight: bold'

            # Editor voor snelle wijzigingen (Prio & Notities)
            st.write("Pas prioriteit of notities direct aan:")
            
            edited_df = st.data_editor(
                df_entries,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "id": None,
                    "Geboortedatum": st.column_config.DateColumn(format="DD-MM-YYYY"),
                    "Datum": st.column_config.DatetimeColumn(format="DD-MM-YYYY"),
                    "Prio": st.column_config.SelectboxColumn("Prio", options=["High", "Medium", "Low"], required=True)
                },
                disabled=["Naam", "Huidig Team", "Geboortedatum", "Door", "Datum"],
                key="shortlist_editor"
            )

            # SAVE CHANGES BUTTON
            if st.button("💾 Wijzigingen Opslaan"):
                changes = st.session_state["shortlist_editor"]["edited_rows"]
                if changes:
                    for idx, row_changes in changes.items():
                        # Haal ID op (pas op met sortering, gebruik originele index)
                        rec_id = df_entries.iloc[idx]['id']
                        
                        # Update logic
                        if "Prio" in row_changes:
                            execute_command("UPDATE scouting.shortlist_entries SET priority = %s WHERE id = %s", (row_changes["Prio"], int(rec_id)))
                        if "Notitie" in row_changes:
                            execute_command("UPDATE scouting.shortlist_entries SET notities = %s WHERE id = %s", (row_changes["Notitie"], int(rec_id)))
                    
                    st.success("Opgeslagen!")
                    st.cache_data.clear()
                    st.rerun()

            st.markdown("---")
            # DELETE BUTTON
            st.write("🗑️ **Verwijderen**")
            to_delete = st.selectbox("Selecteer speler om te verwijderen:", ["-"] + df_entries['Naam'].tolist())
            if to_delete != "-":
                if st.button(f"Verwijder {to_delete} van lijst"):
                    # Zoek ID
                    del_id = df_entries[df_entries['Naam'] == to_delete].iloc[0]['id']
                    if execute_command("DELETE FROM scouting.shortlist_entries WHERE id = %s", (int(del_id),)):
                        st.success("Verwijderd.")
                        st.cache_data.clear()
                        st.rerun()

        else:
            st.info("Deze lijst is nog leeg.")
