import streamlit as st
import pandas as pd
from utils import run_query, init_connection
import datetime

st.set_page_config(page_title="Legacy Data Import", page_icon="🏗️", layout="wide")

st.title("🏗️ Legacy Data Import Tool")
st.markdown("Slimme import tool: Corrigeer data & koppel aan DB.")

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
@st.cache_data
def load_scout_map():
    """Haalt alle scouts op en maakt een map: {email: id}"""
    try:
        df = run_query("SELECT id, email FROM scouting.gebruikers")
        return dict(zip(df['email'].str.lower().str.strip(), df['id']))
    except:
        return {}

@st.cache_data
def get_valid_options():
    """Haalt toegestane waardes op voor dropdowns om FK errors te voorkomen"""
    options = {"posities": [], "advies": []}
    try:
        # Posities
        df_pos = run_query("SELECT * FROM scouting.opties_posities")
        if not df_pos.empty:
            # We gokken dat de eerste kolom de waarde is als er geen 'waarde' kolom is
            col = 'waarde' if 'waarde' in df_pos.columns else df_pos.columns[0]
            options["posities"] = df_pos[col].tolist()
        
        # Advies
        df_adv = run_query("SELECT * FROM scouting.opties_advies")
        if not df_adv.empty:
            col = 'waarde' if 'waarde' in df_adv.columns else df_adv.columns[0]
            options["advies"] = df_adv[col].tolist()
            
    except Exception as e:
        st.error(f"Kon opties niet laden: {e}")
    return options

def parse_legacy_player_string(player_str):
    if not isinstance(player_str, str): return "", ""
    parts = player_str.split(' - ')
    if len(parts) >= 2:
        return parts[0].strip(), parts[1].strip()
    return player_str.strip(), ""

def search_players_fuzzy(name_part):
    if not name_part or len(name_part) < 2: return pd.DataFrame()
    search_term = name_part
    if "." in name_part:
        search_term = name_part.split('.')[-1].strip()
    
    query = """
        SELECT p.id, p.commonname, p.firstname, p.lastname, p.birthdate, s.name as team_name
        FROM public.players p
        LEFT JOIN public.squads s ON p."currentSquadId" = s.id
        WHERE p.commonname ILIKE %s OR p.lastname ILIKE %s 
        LIMIT 10
    """
    term = f"%{search_term}%"
    return run_query(query, params=(term, term))

def save_legacy_report(data_dict):
    """
    Slaat het rapport op met reeds gevalideerde data uit de UI.
    data_dict verwacht: scout_id, speler_id (of custom_naam), positie, advies, rating, tekst, datum
    """
    conn = None
    try:
        conn = init_connection()
        cur = conn.cursor()
        
        # Insert Query
        q = """
            INSERT INTO scouting.rapporten 
            (scout_id, speler_id, custom_speler_naam, positie_gespeeld, beoordeling, advies, 
             rapport_tekst, aangemaakt_op, custom_wedstrijd_naam)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'Legacy Import')
        """
        cur.execute(q, (
            data_dict['scout_id'], 
            data_dict['speler_id'], 
            data_dict['custom_naam'], 
            data_dict['positie'], 
            data_dict['rating'], 
            data_dict['advies'], 
            data_dict['tekst'], 
            data_dict['datum']
        ))
        
        conn.commit()
        cur.close()
        return True
    except Exception as e:
        st.error(f"Fout bij opslaan DB: {e}")
        return False
    finally:
        if conn: conn.close()

# -----------------------------------------------------------------------------
# 2. SETUP & UPLOAD
# -----------------------------------------------------------------------------
valid_opts = get_valid_options() # Haal DB opties op

if st.session_state.import_df is None:
    st.session_state.scout_map = load_scout_map()
    uploaded_file = st.file_uploader("Upload CSV (Screening/Scouting)", type=['csv'])
    
    if uploaded_file:
        try:
            df = pd.read_csv(uploaded_file)
            st.success(f"{len(df)} rijen geladen.")
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
    
    if idx >= len(df):
        st.balloons()
        st.success("✅ Import Voltooid!")
        if st.button("Opnieuw"):
            st.session_state.import_df = None
            st.session_state.current_index = 0
            st.rerun()
        st.stop()
        
    row = df.iloc[idx]
    legacy_player_name = str(row.get('Player')).strip()

    # --- UI LAYOUT ---
    progress = (idx / len(df))
    st.progress(progress, text=f"Rij {idx + 1} / {len(df)}")
    
    col_source, col_edit, col_match = st.columns([1, 1, 1.5])
    
    # ---------------------------------------------------------
    # KOLOM 1: BRON DATA (ReadOnly)
    # ---------------------------------------------------------
    with col_source:
        st.subheader("📄 Origineel")
        st.info(f"**{legacy_player_name}**")
        st.write(f"Team: {row.get('Team')}")
        st.write(f"Datum: {row.get('DATE')}")
        
        # Raw data tonen
        st.text_input("CSV Positie", value=str(row.get('Starting Position')), disabled=True)
        st.text_input("CSV Advies", value=str(row.get('Advies')), disabled=True)
        
        scout_email = str(row.get('SCOUT')).lower().strip()
        found_scout_id = st.session_state.scout_map.get(scout_email, 1)

    # ---------------------------------------------------------
    # KOLOM 2: CORRIGEER DATA (Cruciaal voor Foreign Keys)
    # ---------------------------------------------------------
    with col_edit:
        st.subheader("✍️ Corrigeer")
        
        # 1. POSITIE MAPPING LOGICA
        raw_pos = str(row.get('Starting Position', '')).strip()
        # Mapping tabelletje voor legacy afkortingen naar DB waarden
        mapping_pos = {"WBL": "Verdediger", "WBR": "Verdediger", "CDM": "Middenvelder", "CAM": "Middenvelder", "CF": "Aanvaller"} 
        
        # Probeer slim te matchen in de lijst van DB opties
        default_pos_index = 0
        if raw_pos in valid_opts["posities"]:
             default_pos_index = valid_opts["posities"].index(raw_pos)
        elif raw_pos in mapping_pos and mapping_pos[raw_pos] in valid_opts["posities"]:
             default_pos_index = valid_opts["posities"].index(mapping_pos[raw_pos])
        
        final_pos = st.selectbox("Positie (Verplicht)", valid_opts["posities"], index=default_pos_index, key=f"pos_{idx}")

        # 2. ADVIES MAPPING LOGICA
        raw_adv = str(row.get('Advies', '')).strip()
        mapping_adv = {"Future Sign": "A", "Sign": "A", "Follow": "B", "Not": "C"} # Pas aan naar jouw codes (A, B, C)
        
        default_adv_index = 0
        if raw_adv in valid_opts["advies"]:
            default_adv_index = valid_opts["advies"].index(raw_adv)
        elif raw_adv in mapping_adv and mapping_adv[raw_adv] in valid_opts["advies"]:
            default_adv_index = valid_opts["advies"].index(mapping_adv[raw_adv])
            
        final_adv = st.selectbox("Advies (Verplicht)", valid_opts["advies"], index=default_adv_index, key=f"adv_{idx}")

        # 3. RATING & TEKST
        raw_rating = pd.to_numeric(row.get('Match Rating'), errors='coerce')
        final_rating = st.slider("Rating", 1, 10, int(raw_rating * 2) if not pd.isna(raw_rating) else 6, key=f"rat_{idx}")
        
        raw_txt = str(row.get('Resume'))
        if raw_txt == 'nan': raw_txt = str(row.get('Scouting Notes', ''))
        final_tekst = st.text_area("Tekst", raw_txt, height=100, key=f"txt_{idx}")
        
        # Datum Fix
        try:
            final_date = pd.to_datetime(row.get('DATE')).date()
        except:
            final_date = datetime.date.today()

    # ---------------------------------------------------------
    # KOLOM 3: KOPPELEN (Acties)
    # ---------------------------------------------------------
    with col_match:
        st.subheader("🔗 Koppel & Opslaan")
        
        # Data pakketje maken voor de save functie
        save_packet = {
            "scout_id": found_scout_id,
            "positie": final_pos,
            "advies": final_adv,
            "rating": final_rating,
            "tekst": final_tekst,
            "datum": final_date,
            "speler_id": None,
            "custom_naam": None
        }

        parsed_name, _ = parse_legacy_player_string(legacy_player_name)
        results = search_players_fuzzy(st.text_input("Zoek DB", value=parsed_name, key=f"s_{idx}"))
        
        # KNOPPEN
        if not results.empty:
            for _, db_row in results.iterrows():
                if st.button(f"Koppel: {db_row['commonname']} ({db_row['team_name']})", key=f"btn_{db_row['id']}", type="primary"):
                    save_packet['speler_id'] = str(db_row['id'])
                    if save_legacy_report(save_packet):
                        st.session_state.current_index += 1
                        st.rerun()

        st.markdown("---")
        
        col_cust, col_skip = st.columns(2)
        with col_cust:
            if st.button("💾 Als Custom Opslaan"):
                save_packet['custom_naam'] = legacy_player_name
                if save_legacy_report(save_packet):
                    st.session_state.current_index += 1
                    st.rerun()
        with col_skip:
            if st.button("⏭️ Overslaan"):
                st.session_state.current_index += 1
                st.rerun()
