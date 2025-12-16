import streamlit as st
import pandas as pd
from utils import run_query, init_connection

st.set_page_config(page_title="Legacy Data Import", page_icon="🏗️", layout="wide")

st.title("🏗️ Legacy Data Import Tool")
st.markdown("Slimme import tool: koppel aan DB of maak automatisch custom spelers aan.")

# -----------------------------------------------------------------------------
# 0. INITIALISATIE SESSION STATE
# -----------------------------------------------------------------------------
if 'import_df' not in st.session_state: st.session_state.import_df = None
if 'current_index' not in st.session_state: st.session_state.current_index = 0
if 'scout_map' not in st.session_state: st.session_state.scout_map = {}
if 'player_map' not in st.session_state: st.session_state.player_map = {}

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
    """Zoekt in DB op basis van naam (flexibel) + haalt TEAM op"""
    if not name_part or len(name_part) < 2: return pd.DataFrame()
    
    # Probeer achternaam te isoleren
    search_term = name_part
    if "." in name_part:
        search_term = name_part.split('.')[-1].strip()
    
    # --- AANGEPASTE QUERY MET JOIN NAAR SQUADS ---
    query = """
        SELECT p.id, p.commonname, p.firstname, p.lastname, p.birthdate, s.name as team_name
        FROM public.players p
        LEFT JOIN public.squads s ON p."currentSquadId" = s.id
        WHERE p.commonname ILIKE %s OR p.lastname ILIKE %s 
        LIMIT 10
    """
    term = f"%{search_term}%"
    return run_query(query, params=(term, term))

def save_legacy_report(row_data, db_player_id=None, custom_player_name=None, scout_id=None):
    """
    Slaat het rapport op. 
    Accepteert OF db_player_id (integer) OF custom_player_name (string).
    """
    conn = None
    try:
        conn = init_connection()
        cur = conn.cursor()
        
        # Rating omzetten
        rating_raw = pd.to_numeric(row_data.get('Match Rating'), errors='coerce')
        rating = int(rating_raw * 2) if not pd.isna(rating_raw) else None
        
        # Datum parsen
        date_val = pd.to_datetime(row_data.get('DATE')).date()
        
        # Advies Mapping
        raw_advies = str(row_data.get('Advies', '')).strip()
        advies_map = {
            "Future Sign": "Future sign",
            "Sign": "Sign", "Follow": "Follow", "Not": "Not",
            "nan": None, "": None
        }
        advies = advies_map.get(raw_advies, raw_advies)
        
        # Profiel Code (Lower)
        raw_prof = str(row_data.get('Profile', '')).strip()
        profiel = raw_prof.lower() if raw_prof and raw_prof != 'nan' else None

        # Tekst
        tekst = str(row_data.get('Resume', '')).strip()
        if not tekst or tekst == 'nan':
            tekst = str(row_data.get('Scouting Notes', '')).strip()

        # Positie
        positie = str(row_data.get('Starting Position', '')).strip()
        
        # LOGICA: ID of Custom Naam?
        val_speler_id = db_player_id
        val_custom_naam = custom_player_name
        
        # Insert Query
        q = """
            INSERT INTO scouting.rapporten 
            (scout_id, speler_id, custom_speler_naam, positie_gespeeld, beoordeling, advies, 
             profiel_code, rapport_tekst, aangemaakt_op, custom_wedstrijd_naam)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'Legacy Import')
        """
        cur.execute(q, (
            scout_id, val_speler_id, val_custom_naam, positie, rating, advies, 
            profiel, tekst, date_val
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
    
    # Check Einde
    if idx >= len(df):
        st.balloons()
        st.success("✅ Import Voltooid! Alle rijen zijn verwerkt.")
        if st.button("Opnieuw beginnen"):
            st.session_state.import_df = None
            st.session_state.current_index = 0
            st.rerun()
        st.stop()
        
    # Huidige rij
    row = df.iloc[idx]
    legacy_player_name = str(row.get('Player')).strip()

    # --- AUTO-PROCESS LOGICA ---
    if legacy_player_name in st.session_state.player_map:
        mapped_val = st.session_state.player_map[legacy_player_name]
        
        scout_email = str(row.get('SCOUT')).lower().strip()
        scout_id = st.session_state.scout_map.get(scout_email, 1) 
        
        is_db_id = isinstance(mapped_val, int)
        db_id = mapped_val if is_db_id else None
        cust_name = mapped_val if not is_db_id else None
        
        if save_legacy_report(row, db_player_id=db_id, custom_player_name=cust_name, scout_id=scout_id):
            st.session_state.current_index += 1
            st.rerun()
    
    # --- UI LAYOUT ---
    progress = (idx / len(df))
    st.progress(progress, text=f"Bezig met rij {idx + 1} van {len(df)}")
    
    col_source, col_match = st.columns([1, 2])
    
    # A. BRON DATA
    with col_source:
        st.subheader("📄 Bron Data")
        st.info(f"**Speler:** {legacy_player_name}")
        st.write(f"**Team (Excel):** {row.get('Team')}")
        st.write(f"**Datum:** {row.get('DATE')}")
        
        scout_email = str(row.get('SCOUT')).lower().strip()
        found_scout_id = st.session_state.scout_map.get(scout_email)
        
        if found_scout_id:
            st.success(f"✅ Scout ID: {found_scout_id}")
        else:
            st.warning(f"⚠️ Scout onbekend (Default: 1)")
            found_scout_id = st.text_input("Scout ID:", value="1")

        txt = str(row.get('Resume'))
        if txt == 'nan': txt = str(row.get('Scouting Notes'))
        with st.expander("Lees tekst"): st.write(txt)

    # B. MATCHING
    with col_match:
        st.subheader("🔍 Zoek & Koppel")
        
        parsed_name, _ = parse_legacy_player_string(legacy_player_name)
        search_query = st.text_input("Zoekterm", value=parsed_name, key=f"search_{idx}")
        results = search_players_fuzzy(search_query)
        
        # OPTIE 1: DATABASE MATCHES
        if not results.empty:
            st.write("Database Resultaten:")
            for _, db_row in results.iterrows():
                # Card voor elke speler
                c1, c2, c3 = st.columns([3, 2, 2])
                
                # --- AANGEPASTE WEERGAVE MET CLUB ---
                club_display = db_row['team_name'] if db_row['team_name'] else "Geen club"
                
                with c1: st.write(f"**{db_row['commonname']}**")
                with c2: 
                    st.caption(f"{db_row['firstname']} {db_row['lastname']}")
                    st.caption(f"⚽ {club_display} | 📅 {db_row['birthdate']}")
                
                with c3:
                    if st.button("🔗 Koppel", key=f"link_{db_row['id']}", type="primary"):
                        st.session_state.player_map[legacy_player_name] = int(db_row['id'])
                        
                        if save_legacy_report(row, db_player_id=int(db_row['id']), scout_id=found_scout_id):
                            st.session_state.current_index += 1
                            st.rerun()
            st.markdown("---")
        else:
            st.warning("Geen directe matches gevonden.")

        # OPTIE 2: CUSTOM SPELER
        with st.expander("➕ Speler niet gevonden? Maak Custom aan", expanded=True):
            st.write("Sla op als 'Custom Speler' (zonder ID).")
            custom_name_input = st.text_input("Naam voor rapport:", value=legacy_player_name, key=f"cust_{idx}")
            
            if st.button("💾 Opslaan als Custom Speler", key=f"btn_cust_{idx}"):
                st.session_state.player_map[legacy_player_name] = custom_name_input
                
                if save_legacy_report(row, custom_player_name=custom_name_input, scout_id=found_scout_id):
                    st.session_state.current_index += 1
                    st.rerun()

        # SKIP OPTIE
        st.markdown("---")
        if st.button("⏭️ Overslaan", key=f"skip_{idx}"):
            st.session_state.current_index += 1
            st.rerun()
