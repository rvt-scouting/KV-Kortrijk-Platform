import streamlit as st
import pandas as pd
from datetime import datetime
from utils import run_query, init_connection

st.set_page_config(page_title="Aangeboden Spelers", page_icon="📥", layout="wide")
st.title("📥 Aangeboden Spelers")

# -----------------------------------------------------------------------------
# 1. HULPFUNCTIE VOOR SCHRIJVEN (INSERT/UPDATE)
# -----------------------------------------------------------------------------
def execute_command(query, params=None):
    """ Voert een SQL commando uit dat geen data teruggeeft (INSERT, UPDATE, DELETE) """
    conn = None
    try:
        conn = init_connection()
        cur = conn.cursor()
        cur.execute(query, params)
        conn.commit() # Belangrijk: bevestig de wijziging
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
tab1, tab2 = st.tabs(["➕ Nieuwe speler toevoegen", "📋 Overzichtlijst"])

# =============================================================================
# TAB 1: TOEVOEGEN
# =============================================================================
with tab1:
    st.header("Nieuwe speler registreren")
    st.info("Zoek eerst de speler in onze database om de koppeling te maken.")
    
    # A. Speler Zoeken in public.players
    c_search, c_select = st.columns([1, 2])
    
    with c_search:
        search_term = st.text_input("🔍 Typ naam speler:", placeholder="bv. Messi")
    
    selected_player_id = None
    player_display_name = ""
    
    with c_select:
        if len(search_term) > 2:
            # We zoeken in de bestaande spelers tabel
            # We halen ook het huidige team op voor context
            search_q = """
                SELECT p.id, p.commonname, sq.name as "team"
                FROM public.players p
                LEFT JOIN public.squads sq ON p."currentSquadId" = sq.id
                WHERE p.commonname ILIKE %s
                LIMIT 20
            """
            df_results = run_query(search_q, params=(f"%{search_term}%",))
            
            if not df_results.empty:
                # Maak een dictionary voor de dropdown: "Naam (Team)" -> ID
                options = {f"{row['commonname']} ({row['team'] or 'Geen Club'})": row['id'] for _, row in df_results.iterrows()}
                selected_label = st.selectbox("Selecteer de juiste speler:", list(options.keys()))
                
                if selected_label:
                    selected_player_id = options[selected_label]
                    player_display_name = selected_label.split(" (")[0]
            else:
                st.warning("Geen spelers gevonden.")
        else:
            st.caption("Typ minimaal 3 letters om te zoeken.")

    st.divider()

    # B. Het Formulier (Alleen tonen als er een ID is of als fallback)
    # We blokkeren het formulier niet volledig, maar waarschuwen wel als er geen ID is.
    
    if selected_player_id:
        st.success(f"Geselecteerd: **{player_display_name}** (ID: {selected_player_id})")
        
        with st.form("offered_player_form"):
            c1, c2 = st.columns(2)
            with c1:
                makelaar = st.text_input("Makelaar / Bureau")
                vraagprijs = st.number_input("Vraagprijs (€)", min_value=0, step=10000, format="%d")
            
            with c2:
                video_link = st.text_input("Link naar Video (Wyscout/YouTube)")
                status = st.selectbox("Status", ["Te bekijken", "Interessant", "Afgekeurd", "Onderhandeling", "In de gaten houden"])
            
            opmerkingen = st.text_area("Korte Opmerking / Scoutingsverslag")
            
            # Automatisch de gebruiker ophalen die is ingelogd
            user_name = st.session_state.user_info.get('naam', 'Onbekend') if 'user_info' in st.session_state and st.session_state.user_info else "Systeem"

            submitted = st.form_submit_button("💾 Opslaan in Database")
            
            if submitted:
                if makelaar:
                    insert_q = """
                        INSERT INTO scouting.offered_players 
                        (player_id, makelaar, vraagprijs, video_link, status, opmerkingen, ingevoerd_door)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """
                    success = execute_command(insert_q, params=(
                        str(selected_player_id), 
                        makelaar, 
                        vraagprijs, 
                        video_link, 
                        status, 
                        opmerkingen, 
                        user_name
                    ))
                    
                    if success:
                        st.success(f"Speler **{player_display_name}** succesvol opgeslagen!")
                        st.balloons()
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
    
    # We halen de data op, inclusief de verborgen 'id' die we nodig hebben voor de update
    overview_query = """
        SELECT 
            o.id,
            p.commonname as "Naam",
            sq.name as "Huidig Team",
            p.birthdate as "Geboortedatum",
            o.status as "Status",
            o.makelaar as "Makelaar",
            o.vraagprijs as "Vraagprijs",
            o."TMlink" as "TM",
            o.video_link as "Video",
            o.opmerkingen as "Notities",
            o.ingevoerd_door as "Scout",
            o.aangeboden_datum as "Datum"
        FROM scouting.offered_players o
        JOIN public.players p ON o.player_id = p.id
        LEFT JOIN public.squads sq ON p."currentSquadId" = sq.id
        ORDER BY o.aangeboden_datum DESC
    """
    
    # We laden de dataframe in sessie state zodat we het origineel kunnen vergelijken
    # Dit voorkomt dat de tabel constant herlaadt terwijl je typt
    if "df_overview" not in st.session_state:
        st.session_state.df_overview = pd.DataFrame()

    # Vernieuw knop (handig als iemand anders iets heeft toegevoegd)
    if st.button("🔄 Tabel Verversen"):
        st.cache_data.clear() # Cache wissen indien nodig
        del st.session_state.df_overview # Forceer herladen
        st.rerun()

    try:
        # Alleen ophalen als het nog niet in session state zit of leeg is
        if st.session_state.df_overview.empty:
            st.session_state.df_overview = run_query(overview_query)
        
        df_display = st.session_state.df_overview.copy()
        
        if not df_display.empty:
            # ---------------------------------------------------------
            # DE DATA EDITOR CONFIGURATIE
            # ---------------------------------------------------------
            edited_df = st.data_editor(
                df_display,
                use_container_width=True,
                hide_index=True,
                key="scouting_editor", # Belangrijk: unieke sleutel
                disabled=["id", "Naam", "Huidig Team", "Geboortedatum", "Scout", "Datum"], # Deze kolommen mag je NIET aanpassen
                column_config={
                    "id": None, # Verberg de ID kolom, maar hij is er wel!
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
            # LOGICA OM WIJZIGINGEN OP TE SLAAN
            # ---------------------------------------------------------
            st.caption("✍️ Pas de waarden direct aan in de tabel en klik hieronder op Opslaan.")
            
            if st.button("💾 Wijzigingen Opslaan", type="primary"):
                # We moeten weten WAT er veranderd is. 
                # Streamlit geeft ons de hele 'edited_df'. We kunnen vergelijken of via session_state kijken.
                # De 'edited_rows' in session state is het makkelijkst, die bevat alleen de changes.
                
                changes = st.session_state["scouting_editor"]["edited_rows"]
                
                if not changes:
                    st.info("Geen wijzigingen gevonden.")
                else:
                    # Mapping van Scherm-kolomnaam naar Database-kolomnaam
                    col_mapping = {
                        "Status": "status",
                        "Makelaar": "makelaar",
                        "Vraagprijs": "vraagprijs",
                        "TM": "\"TMlink\"", # Let op de quotes voor TMlink
                        "Video": "video_link",
                        "Notities": "opmerkingen"
                    }
                    
                    success_count = 0
                    
                    for index, row_changes in changes.items():
                        # Haal de ECHTE database ID op uit de originele dataframe op basis van de index
                        # Let op: dit werkt alleen als de sortering niet tussentijds is veranderd door de user in de UI
                        # (st.data_editor sorteren verandert de index niet, dus dat is veilig)
                        record_id = df_display.iloc[index]['id']
                        
                        # Bouw de UPDATE query
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
                    
                    if success_count > 0:
                        st.success(f"✅ {success_count} speler(s) succesvol bijgewerkt!")
                        # Cache wissen en herladen om de nieuwe data te tonen
                        del st.session_state.df_overview
                        st.rerun()
                    else:
                        st.error("Er ging iets mis bij het opslaan.")

        else:
            st.info("Nog geen spelers in de lijst.")
            
    except Exception as e:
        st.error(f"Fout in overzicht: {e}")
