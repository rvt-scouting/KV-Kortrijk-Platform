import streamlit as st
import pandas as pd
from utils import run_query, init_connection

st.set_page_config(page_title="Legacy Data Import", page_icon="🏗️", layout="wide")

st.title("🏗️ Legacy Data Import Tool")
st.markdown("Upload oude Excel/CSV exports en koppel ze manueel aan de juiste database spelers.")

# -----------------------------------------------------------------------------
# 0. INITIALISATIE SESSION STATE
# -----------------------------------------------------------------------------
if 'import_df' not in st.session_state: st.session_state.import_df = None
if 'current_index' not in st.session_state: st.session_state.current_index = 0
if 'scout_map' not in st.session_state: st.session_state.scout_map = {}

# -----------------------------------------------------------------------------
# 1. HULPFUNCTIES
# -----------------------------------------------------------------------------
def load_scout_map():
    """Haalt alle scouts op en maakt een map: {email: id}"""
    try:
        df = run_query("SELECT id, email FROM scouting.gebruikers")
        return dict(zip(df['email'].str.lower().str.strip(), df['id']))
    except:
        return {}

def parse_legacy_player_string(player_str):
    """
    Probeert 'I. Halifa - RWD Molenbeek - 2425' te splitsen.
    Returnt (Naam, Team)
    """
    if not isinstance(player_str, str): return "", ""
    parts = player_str.split(' - ')
    if len(parts) >= 2:
        return parts[0].strip(), parts[1].strip()
    return player_str.strip(), ""

def search_players_fuzzy(name_part):
    """Zoekt in DB op basis van naam (flexibel)"""
    if not name_part or len(name_part) < 2: return pd.DataFrame()
    
    # Probeer achternaam te isoleren voor betere search
    # bv. "I. Halifa" -> zoek op "Halifa"
    search_term = name_part
    if "." in name_part:
        search_term = name_part.split('.')[-1].strip()
    
    query = """
        SELECT id, commonname, firstname, lastname, birthday
        FROM public.players 
        WHERE commonname ILIKE %s OR lastname ILIKE %s 
        LIMIT 10
    """
    term = f"%{search_term}%"
    return run_query(query, params=(term, term))

def save_legacy_report(row_data, db_player_id, scout_id):
    """Slaat het rapport op in de database"""
    conn = None
    try:
        conn = init_connection()
        cur = conn.cursor()
        
        # Rating omzetten (1-5 naar 1-10)
        rating_raw = pd.to_numeric(row_data.get('Match Rating'), errors='coerce')
        rating = int(rating_raw * 2) if not pd.isna(rating_raw) else None
        
        # Datum parsen
        date_val = pd.to_datetime(row_data.get('DATE')).date()
        
        # Advies
        advies = str(row_data.get('Advies', '')).strip()
        
        # Tekst
        tekst = str(row_data.get('Resume', '')).strip()
        if not tekst or tekst == 'nan':
            tekst = str(row_data.get('Scouting Notes', '')).strip()

        # Positie
        positie = str(row_data.get('Starting Position', '')).strip()
        
        # Insert Query
        q = """
            INSERT INTO scouting.rapporten 
            (scout_id, speler_id, positie_gespeeld, beoordeling, advies, 
             rapport_tekst, aangemaakt_op, custom_wedstrijd_naam)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'Legacy Import')
        """
        cur.execute(q, (
            scout_id, db_player_id, positie, rating, advies, tekst, date_val
        ))
        
        conn.commit()
        cur.close()
        return True
    except Exception as e:
        st.error(f"Fout bij opslaan: {e}")
        return False
    finally:
        if conn: conn.close()

# -----------------------------------------------------------------------------
# 2. BESTAND UPLOADEN
# -----------------------------------------------------------------------------
if st.session_state.import_df is None:
    st.session_state.scout_map = load_scout_map()
    
    uploaded_file = st.file_uploader("Upload CSV (Screening/Scouting)", type=['csv'])
    
    if uploaded_file:
        try:
            df = pd.read_csv(uploaded_file)
            st.success(f"{len(df)} rijen geladen.")
            
            # Kolom check
            required = ['Player', 'DATE', 'SCOUT']
            if not all(col in df.columns for col in required):
                st.error(f"CSV mist kolommen. Vereist: {required}")
            else:
                if st.button("Start Import Proces"):
                    st.session_state.import_df = df
                    st.session_state.current_index = 0
                    st.rerun()
        except Exception as e:
            st.error(f"Kan bestand niet lezen: {e}")

# -----------------------------------------------------------------------------
# 3. MATCHING WIZARD
# -----------------------------------------------------------------------------
else:
    df = st.session_state.import_df
    idx = st.session_state.current_index
    
    # Check of we klaar zijn
    if idx >= len(df):
        st.balloons()
        st.success("✅ Import Voltooid! Alle rijen zijn verwerkt.")
        if st.button("Opnieuw beginnen"):
            st.session_state.import_df = None
            st.session_state.current_index = 0
            st.rerun()
        st.stop()
        
    # Huidige rij ophalen
    row = df.iloc[idx]
    
    # Progress Bar
    progress = (idx / len(df))
    st.progress(progress, text=f"Bezig met rij {idx + 1} van {len(df)}")
    
    # --- UI LAYOUT ---
    col_source, col_match = st.columns([1, 2])
    
    # A. BRON DATA (LINKERKANT)
    with col_source:
        st.subheader("📄 Bron Data (Excel)")
        st.info(f"**Speler:** {row.get('Player')}")
        st.write(f"**Team (Excel):** {row.get('Team')}")
        st.write(f"**Positie:** {row.get('Starting Position')}")
        st.write(f"**Datum:** {row.get('DATE')}")
        
        # Scout Check
        scout_email = str(row.get('SCOUT')).lower().strip()
        found_scout_id = st.session_state.scout_map.get(scout_email)
        
        if found_scout_id:
            st.success(f"✅ Scout herkend (ID: {found_scout_id})")
        else:
            st.warning(f"⚠️ Scout '{scout_email}' onbekend!")
            found_scout_id = st.text_input("Voer manueel Scout ID in:", value="1")

        # Tekst preview
        txt = str(row.get('Resume'))
        if txt == 'nan': txt = str(row.get('Scouting Notes'))
        with st.expander("Lees rapport tekst"):
            st.write(txt)

    # B. MATCHING (RECHTERKANT)
    with col_match:
        st.subheader("🔍 Zoek in Database")
        
        # Naam parsen
        parsed_name, parsed_team = parse_legacy_player_string(row.get('Player'))
        
        # Zoekbalk (standaard ingevuld met geparsde naam)
        search_query = st.text_input("Zoekterm", value=parsed_name, key=f"search_{idx}")
        
        # Resultaten ophalen
        results = search_players_fuzzy(search_query)
        
        if not results.empty:
            st.write("Resultaten:")
            for _, db_row in results.iterrows():
                # Card voor elke speler
                c1, c2, c3 = st.columns([3, 2, 2])
                with c1: st.write(f"**{db_row['commonname']}**")
                with c2: st.caption(f"{db_row['firstname']} {db_row['lastname']}")
                with c3:
                    # DE KNOP: Koppelen en Opslaan
                    if st.button("Koppel & Opslaan", key=f"link_{db_row['id']}", type="primary"):
                        if save_legacy_report(row, db_row['id'], found_scout_id):
                            st.session_state.current_index += 1
                            st.rerun()
            st.markdown("---")
        else:
            st.warning("Geen directe matches gevonden.")

        # SKIP OPTIE
        c_skip, c_next = st.columns(2)
        with c_skip:
            if st.button("⏭️ Overslaan (Niet importeren)", key=f"skip_{idx}"):
                st.session_state.current_index += 1
                st.rerun()
