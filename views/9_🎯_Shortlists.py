import streamlit as st
import pandas as pd
from utils import run_query, init_connection

st.set_page_config(page_title="Shortlist Manager", page_icon="🎯", layout="wide")

if 'user_info' not in st.session_state or not st.session_state.user_info:
    st.warning("⚠️ Log in AUB."); st.stop()

current_user_name = st.session_state.user_info.get('naam', 'Onbekend')
current_user_id = st.session_state.user_info.get('id')

# Haal niveau op
try:
    lvl = int(st.session_state.user_info.get('toegangsniveau', 0))
except:
    lvl = 0

st.title("🎯 Shortlists Manager")

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
    try:
        base_query = """
            SELECT s.id, s.naam, u.naam as eigenaar 
            FROM scouting.shortlists s
            LEFT JOIN scouting.gebruikers u ON s.eigenaar_id = u.id
        """
        
        # Als Level 1 (Scout), filter op eigen ID
        if lvl == 1:
            q_lists = base_query + " WHERE s.eigenaar_id = %s ORDER BY s.id"
            df_lists = run_query(q_lists, params=(current_user_id,))
        else:
            # Level 2/3 ziet alles
            q_lists = base_query + " ORDER BY s.id"
            df_lists = run_query(q_lists)
        
        if not df_lists.empty:
            list_opts = {f"{row['naam']} (Eigenaar: {row['eigenaar'] or 'Onbekend'})": row['id'] for _, row in df_lists.iterrows()}
            selected_label = st.selectbox("📂 Selecteer Shortlist:", list(list_opts.keys()))
            selected_list_id = list_opts[selected_label]
            selected_list_pure_name = selected_label.split(" (")[0]
        else:
            st.info("Geen shortlists gevonden.")
            selected_list_id = None
            selected_list_pure_name = ""
    except Exception as e:
        st.error(f"Kon shortlists niet laden: {e}")
        selected_list_id = None

with c2:
    # BEVEILIGING: Alleen Niveau 3 (Manager/Admin) mag nieuwe lijsten maken
    if lvl >= 3:
        with st.popover("➕ Nieuwe Lijst Maken"):
            st.write("**Nieuwe Lijst Configureren**")
            new_list_name = st.text_input("Naam lijst", placeholder="bv. Keepers Zomer '25")
            
            try:
                users_df = run_query("SELECT id, naam FROM scouting.gebruikers WHERE actief = true ORDER BY naam")
                if not users_df.empty:
                    user_dict = {row['naam']: row['id'] for _, row in users_df.iterrows()}
                    default_idx = 0
                    if current_user_name in user_dict:
                        default_idx = list(user_dict.keys()).index(current_user_name)
                    
                    assigned_owner_name = st.selectbox("Toewijzen aan:", list(user_dict.keys()), index=default_idx)
                    assigned_owner_id = user_dict[assigned_owner_name]
                else:
                    assigned_owner_id = current_user_id
            except:
                assigned_owner_id = current_user_id

            if st.button("Aanmaken"):
                if new_list_name:
                    q = "INSERT INTO scouting.shortlists (naam, eigenaar_id, aangemaakt_op) VALUES (%s, %s, NOW())"
                    if execute_command(q, (new_list_name, assigned_owner_id)):
                        st.success(f"Lijst '{new_list_name}' gemaakt!")
                        st.cache_data.clear()
                        st.rerun()

st.divider()

if selected_list_id:
    tab1, tab2 = st.tabs(["➕ Speler Toevoegen", "📋 Lijst Bekijken & Bewerken"])

    # LIJST MET POSITIES (Gebruikt in beide tabs)
    pos_options = ["GK","CB", "RB", "LB", "DM", "CM", "ACM", "RW", "LW", "FW"]

    # =========================================================================
    # TAB 1: SPELER TOEVOEGEN
    # =========================================================================
    with tab1:
        st.subheader(f"Toevoegen aan: {selected_list_pure_name}")
        
        col_search, col_form = st.columns([1, 2])
        
        # A. ZOEKEN
        with col_search:
            search_txt = st.text_input("🔍 Zoek speler (Database)", placeholder="Naam...")
            found_pid = None
            found_pname = None
            found_pos = None 
            
            if len(search_txt) > 2:
                q_search = """
                    SELECT p.id, p.commonname, sq.name as team,
                           (SELECT position FROM analysis.final_impect_scores 
                            WHERE "playerId" = p.id 
                            ORDER BY "iterationId" DESC LIMIT 1) as found_pos
                    FROM public.players p 
                    LEFT JOIN public.squads sq ON p."currentSquadId" = sq.id
                    WHERE p.commonname ILIKE %s LIMIT 10
                """
                res = run_query(q_search, (f"%{search_txt}%",))
                
                if not res.empty:
                    opts = {f"{r['commonname']} ({r['team'] or '?'}) - {r['found_pos'] or '?'}": r['id'] for _, r in res.iterrows()}
                    sel = st.radio("Resultaten:", list(opts.keys()))
                    found_pid = opts[sel]
                    found_pname = sel.split(" (")[0]
                    found_pos = res[res['id'] == found_pid].iloc[0]['found_pos']
                else:
                    st.warning("Geen speler gevonden.")
            
            st.markdown("---")
            use_manual = st.checkbox("Of voeg handmatig een naam toe")
        
        # B. OPSLAAN
        with col_form:
            with st.form("add_entry_form"):
                final_pid = None
                final_custom = None
                default_pos_index = 0
                
                if use_manual:
                    final_custom = st.text_input("Naam Speler (Handmatig)")
                    st.caption("Gebruik dit voor spelers die nog niet in onze datafeed zitten.")
                elif found_pid:
                    st.success(f"Geselecteerd: **{found_pname}**")
                    final_pid = found_pid
                    if found_pos and found_pos in pos_options:
                        default_pos_index = pos_options.index(found_pos)
                else:
                    st.info("👈 Zoek en selecteer eerst een speler links.")

                c_pos, c_prio = st.columns(2)
                with c_pos:
                    final_position = st.selectbox("Positie", pos_options, index=default_pos_index)
                with c_prio:
                    prio = st.selectbox("Prioriteit", ["High", "Medium", "Low"], index=1)
                
                notes = st.text_input("Korte notitie", placeholder="bv. Contract loopt af")
                
                if st.form_submit_button("Toevoegen aan Lijst"):
                    if final_pid or final_custom:
                        # Check dubbel
                        dup_check = run_query(
                            "SELECT id FROM scouting.shortlist_entries WHERE shortlist_id = %s AND player_id = %s", 
                            (selected_list_id, final_pid)
                        ) if final_pid else pd.DataFrame() 
                        
                        if not dup_check.empty:
                            st.error("Deze speler staat al op de lijst!")
                        else:
                            q_ins = """
                                INSERT INTO scouting.shortlist_entries 
                                (shortlist_id, player_id, custom_naam, position, priority, notities, added_by)
                                VALUES (%s, %s, %s, %s, %s, %s, %s)
                            """
                            if execute_command(q_ins, (selected_list_id, final_pid, final_custom, final_position, prio, notes, current_user_name)):
                                st.success("Toegevoegd!")
                                st.cache_data.clear()
                                st.rerun()
                    else:
                        st.warning("Selecteer een speler of vul een naam in.")

    # =========================================================================
    # TAB 2: LIJST BEKIJKEN & BEWERKEN
    # =========================================================================
    with tab2:
        q_entries = """
            SELECT 
                e.id,
                COALESCE(p.commonname, e.custom_naam) as "Naam",
                sq.name as "Huidig Team",
                e.position as "Positie",
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
            
            # Level 3 (Management) kan alles bewerken
            # Level 1 (Scouts) kunnen alleen bewerken als ze eigenaar zijn (in theorie, hier staat nu lvl >= 3 voor edit)
            # Aangezien Scouts alleen hun EIGEN lijsten zien (zie filter bovenaan), 
            # kunnen we overwegen om Scouts ook te laten editen in hun eigen lijst.
            # Voor nu houd ik de code consistent met je vorige logica (lvl >= 3), 
            # maar je kan dit veranderen naar `if lvl >= 1:` als scouts ook mogen editen.
            
            can_edit = lvl >= 3 # Pas aan naar lvl >= 1 als scouts ook mogen editen
            
            if can_edit:
                st.info("💡 Bewerk Positie, Prioriteit of Notities direct in de tabel.")
                edited_df = st.data_editor(
                    df_entries,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "id": None,
                        "Geboortedatum": st.column_config.DateColumn(format="DD-MM-YYYY"),
                        "Datum": st.column_config.DatetimeColumn(format="DD-MM-YYYY"),
                        "Prio": st.column_config.SelectboxColumn("Prio", options=["High", "Medium", "Low"], required=True),
                        # --- AANPASSING: POSITIE IS NU EEN DROPDOWN ---
                        "Positie": st.column_config.SelectboxColumn("Positie", options=pos_options), 
                    },
                    # --- AANPASSING: Positie uit disabled gehaald ---
                    disabled=["Naam", "Huidig Team", "Geboortedatum", "Door", "Datum"],
                    key="shortlist_editor"
                )

                if st.button("💾 Wijzigingen Opslaan"):
                    changes = st.session_state["shortlist_editor"]["edited_rows"]
                    if changes:
                        for idx, row_changes in changes.items():
                            rec_id = df_entries.iloc[idx]['id']
                            
                            if "Prio" in row_changes:
                                execute_command("UPDATE scouting.shortlist_entries SET priority = %s WHERE id = %s", (row_changes["Prio"], int(rec_id)))
                            
                            if "Notitie" in row_changes:
                                execute_command("UPDATE scouting.shortlist_entries SET notities = %s WHERE id = %s", (row_changes["Notitie"], int(rec_id)))
                            
                            # --- AANPASSING: OPSLAAN POSITIE ---
                            if "Positie" in row_changes:
                                execute_command("UPDATE scouting.shortlist_entries SET position = %s WHERE id = %s", (row_changes["Positie"], int(rec_id)))
                                
                        st.success("Opgeslagen!")
                        st.cache_data.clear()
                        st.rerun()

                st.markdown("---")
                to_delete = st.selectbox("Selecteer speler om te verwijderen:", ["-"] + df_entries['Naam'].tolist())
                if to_delete != "-":
                    if st.button(f"🗑️ Verwijder {to_delete}"):
                        del_id = df_entries[df_entries['Naam'] == to_delete].iloc[0]['id']
                        if execute_command("DELETE FROM scouting.shortlist_entries WHERE id = %s", (int(del_id),)):
                            st.success("Verwijderd.")
                            st.cache_data.clear()
                            st.rerun()
            else:
                # Read Only View
                def color_prio(val):
                    c = "#c0392b" if val == "High" else "#f39c12" if val == "Medium" else "#27ae60"
                    return f'color: {c}; font-weight: bold'

                st.dataframe(
                    df_entries.style.applymap(color_prio, subset=['Prio']),
                    use_container_width=True,
                    hide_index=True,
                    column_config={"id": None}
                )
        else:
            st.info("Deze lijst is nog leeg.")
