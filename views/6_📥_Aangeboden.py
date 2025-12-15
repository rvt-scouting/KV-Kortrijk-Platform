import streamlit as st
import pandas as pd
from utils import run_query, init_connection

st.set_page_config(page_title="Aangeboden Spelers", page_icon="📥", layout="wide")
st.title("📥 Aangeboden Spelers")

# -----------------------------------------------------------------------------
# 1. HULPFUNCTIE VOOR SCHRIJVEN
# -----------------------------------------------------------------------------
def execute_command(query, params=None):
    """ Voert een SQL commando uit dat geen data teruggeeft (INSERT, UPDATE) """
    conn = None
    try:
        conn = init_connection()
        cur = conn.cursor()
        cur.execute(query, params)
        conn.commit() 
        cur.close()
        return True
    except Exception as e:
        st.error(f"Database Fout: {e}")
        return False
    finally:
        if conn: conn.close()

# -----------------------------------------------------------------------------
# 2. TAB BLADEN
# -----------------------------------------------------------------------------
tab1, tab2 = st.tabs(["➕ Nieuwe speler toevoegen", "📋 Recente aanbiedingen beheren"])

# =============================================================================
# TAB 1: TOEVOEGEN & BEWERKEN
# =============================================================================
with tab1:
    st.header("Speler registreren of bewerken")
    
    # A. Speler Zoeken
    c_search, c_select = st.columns([1, 2])
    with c_search:
        search_term = st.text_input("🔍 Typ naam speler:", placeholder="bv. Messi")
    
    selected_player_id = None
    player_display_name = ""
    
    with c_select:
        if len(search_term) > 2:
            search_q = """
                SELECT p.id, p.commonname, sq.name as "team"
                FROM public.players p
                LEFT JOIN public.squads sq ON p."currentSquadId" = sq.id
                WHERE p.commonname ILIKE %s
                LIMIT 20
            """
            df_results = run_query(search_q, params=(f"%{search_term}%",))
            
            if not df_results.empty:
                options = {f"{row['commonname']} ({row['team'] or 'Geen Club'})": row['id'] for _, row in df_results.iterrows()}
                selected_label = st.selectbox("Selecteer de speler:", list(options.keys()))
                
                if selected_label:
                    selected_player_id = options[selected_label]
                    player_display_name = selected_label.split(" (")[0]
            else:
                st.warning("Geen spelers gevonden.")
        else:
            st.caption("Typ minimaal 3 letters om te zoeken.")

    st.divider()

    # B. Het Formulier (Slimme Logica)
    if selected_player_id:
        # 1. CHECK: Bestaat deze speler al in scouting.offered_players?
        existing_data = run_query("SELECT * FROM scouting.offered_players WHERE player_id = %s", params=(str(selected_player_id),))
        
        is_update = False
        default_vals = {
            "makelaar": "", "vraagprijs": 0, "tm_link": "", 
            "video_link": "", "status": "Te bekijken", "opmerkingen": ""
        }

        if not existing_data.empty:
            # BESTAANDE SPELER: Laad de data
            is_update = True
            row = existing_data.iloc[0]
            st.warning(f"⚠️ **Let op:** {player_display_name} staat al in de lijst. Je bewerkt nu de bestaande inschrijving.")
            
            default_vals["makelaar"] = row['makelaar'] or ""
            default_vals["vraagprijs"] = int(row['vraagprijs']) if row['vraagprijs'] else 0
            default_vals["tm_link"] = row['tmlink'] or "" # Let op de kolomnaam in DB is tmlink
            default_vals["video_link"] = row['video_link'] or ""
            default_vals["status"] = row['status'] if row['status'] else "Te bekijken"
            default_vals["opmerkingen"] = row['opmerkingen'] or ""
        else:
            # NIEUWE SPELER
            st.success(f"Nieuwe registratie voor: **{player_display_name}**")

        # 2. HET FORMULIER
        with st.form("offered_player_form"):
            c1, c2 = st.columns(2)
            with c1:
                makelaar = st.text_input("Makelaar / Bureau", value=default_vals["makelaar"])
                vraagprijs = st.number_input("Vraagprijs (€)", min_value=0, step=10000, value=default_vals["vraagprijs"], format="%d")
                tm_link = st.text_input("Transfermarkt Link (URL)", value=default_vals["tm_link"])
            
            with c2:
                video_link = st.text_input("Link naar Video", value=default_vals["video_link"])
                status_opts = ["Te bekijken", "Interessant", "Afgekeurd", "Onderhandeling", "In de gaten houden"]
                # Zorg dat de huidige status geselecteerd is, of default naar index 0
                idx = status_opts.index(default_vals["status"]) if default_vals["status"] in status_opts else 0
                status = st.selectbox("Status", status_opts, index=idx)
            
            opmerkingen = st.text_area("Korte Opmerking / Scoutingsverslag", value=default_vals["opmerkingen"])
            
            user_name = st.session_state.user_info.get('naam', 'Onbekend') if 'user_info' in st.session_state and st.session_state.user_info else "Systeem"

            # Knop tekst past zich aan
            btn_text = "💾 Wijzigingen Opslaan (Update)" if is_update else "💾 Toevoegen aan Lijst (Insert)"
            submitted = st.form_submit_button(btn_text)
            
            if submitted:
                if makelaar:
                    if is_update:
                        # UPDATE QUERY
                        update_q = """
                            UPDATE scouting.offered_players SET
                                makelaar = %s, vraagprijs = %s, video_link = %s, 
                                tmlink = %s, status = %s, opmerkingen = %s, 
                                ingevoerd_door = %s, aangeboden_datum = NOW()
                            WHERE player_id = %s
                        """
                        success = execute_command(update_q, params=(
                            makelaar, vraagprijs, video_link, tm_link, status, 
                            opmerkingen, user_name, str(selected_player_id)
                        ))
                        msg = "bijgewerkt"
                    else:
                        # INSERT QUERY
                        insert_q = """
                            INSERT INTO scouting.offered_players 
                            (player_id, makelaar, vraagprijs, video_link, tmlink, status, opmerkingen, ingevoerd_door)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """
                        success = execute_command(insert_q, params=(
                            str(selected_player_id), makelaar, vraagprijs, video_link, 
                            tm_link, status, opmerkingen, user_name
                        ))
                        msg = "toegevoegd"
                    
                    if success:
                        st.success(f"Speler **{player_display_name}** succesvol {msg}!")
                        st.balloons()
                        # Cache wissen
                        if "df_overview" in st.session_state:
                            del st.session_state.df_overview
                    else:
                        st.error("Er ging iets mis bij het opslaan.")
                else:
                    st.error("Vul in ieder geval de makelaar in.")
    else:
        if len(search_term) > 2:
            st.info("👆 Selecteer hierboven een speler om het formulier te openen.")
# =============================================================================
# TAB 2: OVERZICHT & BEWERKEN
# =============================================================================
with tab2:
    st.header("📋 Recente aanbiedingen beheren")
    
    # AANGEPAST: o.tmlink (kleine letters)
    overview_query = """
        SELECT 
            o.id,
            p.commonname as "Naam",
            sq.name as "Huidig Team",
            p.birthdate as "Geboortedatum",
            o.status as "Status",
            o.makelaar as "Makelaar",
            o.vraagprijs as "Vraagprijs",
            o.tmlink as "TM",
            o.video_link as "Video",
            o.opmerkingen as "Notities",
            o.ingevoerd_door as "Scout",
            o.aangeboden_datum as "Datum"
        FROM scouting.offered_players o
        JOIN public.players p ON o.player_id = p.id
        LEFT JOIN public.squads sq ON p."currentSquadId" = sq.id
        ORDER BY o.aangeboden_datum DESC
    """
    
    # Laad data in sessie (caching voor de editor)
    if "df_overview" not in st.session_state:
        st.session_state.df_overview = pd.DataFrame()

    # Vernieuw knop
    if st.button("🔄 Tabel Verversen"):
        st.cache_data.clear()
        if "df_overview" in st.session_state:
            del st.session_state.df_overview
        st.rerun()

    try:
        if st.session_state.df_overview.empty:
            st.session_state.df_overview = run_query(overview_query)
        
        df_display = st.session_state.df_overview.copy()
        
        if not df_display.empty:
            # ---------------------------------------------------------
            # DE DATA EDITOR
            # ---------------------------------------------------------
            edited_df = st.data_editor(
                df_display,
                use_container_width=True,
                hide_index=True,
                key="scouting_editor", 
                disabled=["id", "Naam", "Huidig Team", "Geboortedatum", "Scout", "Datum"], 
                column_config={
                    "id": None, 
                    "Vraagprijs": st.column_config.NumberColumn(format="€ %.2f", min_value=0, step=10000),
                    "Datum": st.column_config.DatetimeColumn(format="DD-MM-YYYY"),
                    "Video": st.column_config.LinkColumn("Video Link", display_text="Link"),
                    "TM": st.column_config.LinkColumn("Transfermarkt", display_text="TM"),
                    "Status": st.column_config.SelectboxColumn(
                        "Status",
                        help="Wijzig de status van de speler",
                        width="medium",
                        options=[
                            "Te bekijken", 
                            "Interessant", 
                            "Afgekeurd", 
                            "Onderhandeling", 
                            "In de gaten houden"
                        ],
                        required=True
                    ),
                    "Notities": st.column_config.TextColumn("Notities", width="large")
                }
            )

            # ---------------------------------------------------------
            # OPSLAAN LOGICA
            # ---------------------------------------------------------
            st.caption("✍️ Pas de waarden direct aan in de tabel en klik hieronder op Opslaan.")
            
            if st.button("💾 Wijzigingen Opslaan", type="primary"):
                changes = st.session_state["scouting_editor"]["edited_rows"]
                
                if not changes:
                    st.info("Geen wijzigingen gevonden.")
                else:
                    # AANGEPAST: Mapping naar kleine letters 'tmlink'
                    col_mapping = {
                        "Status": "status",
                        "Makelaar": "makelaar",
                        "Vraagprijs": "vraagprijs",
                        "TM": "tmlink", 
                        "Video": "video_link",
                        "Notities": "opmerkingen"
                    }
                    
                    success_count = 0
                    
                    for index, row_changes in changes.items():
                        # Veilig de ID ophalen (uit de originele dataframe in geheugen)
                        if index in df_display.index:
                            record_id = df_display.iloc[index]['id']
                            
                            set_clauses = []
                            values = []
                            
                            for col_name, new_value in row_changes.items():
                                if col_name in col_mapping:
                                    db_col = col_mapping[col_name]
                                    set_clauses.append(f"{db_col} = %s")
                                    values.append(new_value)
                            
                            if set_clauses:
                                query = f"UPDATE scouting.offered_players SET {', '.join(set_clauses)} WHERE id = %s"
                                values.append(str(record_id))
                                
                                if execute_command(query, tuple(values)):
                                    success_count += 1
                        else:
                            st.warning(f"Rij index {index} niet gevonden (mogelijk door sortering). Ververs de tabel en probeer opnieuw.")
                    
                    if success_count > 0:
                        st.success(f"✅ {success_count} speler(s) succesvol bijgewerkt!")
                        if "df_overview" in st.session_state:
                            del st.session_state.df_overview
                        st.rerun()
                    else:
                        st.error("Er ging iets mis bij het opslaan.")

        else:
            st.info("Nog geen spelers in de lijst.")
            
    except Exception as e:
        st.error(f"Fout in overzicht: {e}")
