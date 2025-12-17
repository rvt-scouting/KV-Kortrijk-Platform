import streamlit as st
import pandas as pd
from utils import run_query, init_connection
import datetime

st.set_page_config(page_title="Legacy Data Import", page_icon="🧠", layout="wide")

st.title("🧠 Slimme Import Tool")
st.markdown("Linker kolom toont de bron, midden correctie, rechts de database koppeling (met geheugen).")

# -----------------------------------------------------------------------------
# 0. INITIALISATIE SESSION STATE
# -----------------------------------------------------------------------------
if 'import_df' not in st.session_state: st.session_state.import_df = None
if 'current_index' not in st.session_state: st.session_state.current_index = 0
if 'scout_map' not in st.session_state: st.session_state.scout_map = {}
if 'name_memory' not in st.session_state: st.session_state.name_memory = {}

# -----------------------------------------------------------------------------
# 1. HULPFUNCTIES
# -----------------------------------------------------------------------------

def normalize_text(text):
    """Maakt tekst 'schoon' voor strikte vergelijking."""
    if not isinstance(text, str): return ""
    return "".join(text.lower().split())

def run_uncached_query(query, params=None):
    """Voert query uit ZONDER cache (voor live checks)."""
    conn = init_connection()
    try:
        return pd.read_sql(query, conn, params=params)
    except Exception as e:
        st.error(f"SQL Error: {e}")
        return pd.DataFrame()
    finally:
        conn.close()

# --- GEHEUGEN FUNCTIES ---
def load_name_memory():
    """Laadt alle opgeslagen koppelingen."""
    try:
        df = run_uncached_query("SELECT legacy_name, speler_id FROM scouting.legacy_names_map")
        if not df.empty:
            return dict(zip(df['legacy_name'], df['speler_id']))
    except:
        return {} 

def save_new_mapping(legacy_name, speler_id):
    """Slaat een nieuwe koppeling op in de database."""
    conn = init_connection()
    try:
        with conn.cursor() as cur:
            query = """
                INSERT INTO scouting.legacy_names_map (legacy_name, speler_id)
                VALUES (%s, %s)
                ON CONFLICT (legacy_name) DO UPDATE SET speler_id = EXCLUDED.speler_id;
            """
            cur.execute(query, (legacy_name, speler_id))
            conn.commit()
            st.session_state.name_memory[legacy_name] = speler_id
    except Exception as e:
        print(f"Kon niet opslaan in geheugen: {e}")
    finally:
        conn.close()

def get_player_details(player_id):
    """Haalt naam + team op van een ID."""
    q = """
        SELECT p.commonname, p.firstname, p.lastname, s.name as team_name
        FROM public.players p
        LEFT JOIN public.squads s ON p."currentSquadId" = s.id
        WHERE p.id = %s
    """
    df = run_query(q, params=(str(player_id),))
    if not df.empty:
        r = df.iloc[0]
        return f"{r['commonname']} ({r['team_name']})"
    return "Onbekende speler"

def parse_legacy_player_string(player_str):
    """Haalt 'Naam - Team' uit elkaar voor betere zoekresultaten."""
    if not isinstance(player_str, str): return "", ""
    parts = player_str.split(' - ')
    if len(parts) >= 2:
        return parts[0].strip(), parts[1].strip()
    return player_str.strip(), ""

# --- DATA OPHALEN ---
@st.cache_data
def load_scout_map():
    try:
        df = run_query("SELECT id, email FROM scouting.gebruikers")
        return dict(zip(df['email'].str.lower().str.strip(), df['id']))
    except: return {}

@st.cache_data
def get_valid_options():
    options = {"posities": [], "advies": []}
    try:
        df_pos = run_query("SELECT * FROM scouting.opties_posities")
        if not df_pos.empty:
            col = 'waarde' if 'waarde' in df_pos.columns else df_pos.columns[0]
            options["posities"] = df_pos[col].tolist()
        
        df_adv = run_query("SELECT * FROM scouting.opties_advies")
        if not df_adv.empty:
            col = 'waarde' if 'waarde' in df_adv.columns else df_adv.columns[0]
            options["advies"] = df_adv[col].tolist()
    except: pass
    return options

def get_existing_report_hashes():
    try:
        df = run_uncached_query("SELECT rapport_tekst FROM scouting.rapporten WHERE rapport_tekst IS NOT NULL")
        if not df.empty:
            return set(df['rapport_tekst'].apply(normalize_text).tolist())
    except: pass
    return set()

def search_players_fuzzy(name_part):
    if not name_part or len(name_part) < 2: return pd.DataFrame()
    # Zoek op commonname OF achternaam
    term = f"%{name_part}%"
    q = """
        SELECT p.id, p.commonname, p.firstname, p.lastname, s.name as team_name
        FROM public.players p
        LEFT JOIN public.squads s ON p."currentSquadId" = s.id
        WHERE p.commonname ILIKE %s OR p.lastname ILIKE %s LIMIT 10
    """
    return run_query(q, params=(term, term))

def save_legacy_report(data_dict):
    conn = None
    try:
        conn = init_connection()
        cur = conn.cursor()
        q = """
            INSERT INTO scouting.rapporten 
            (scout_id, speler_id, custom_speler_naam, positie_gespeeld, beoordeling, advies, 
             rapport_tekst, aangemaakt_op, custom_wedstrijd_naam)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'Legacy Import')
        """
        cur.execute(q, (
            data_dict['scout_id'], data_dict['speler_id'], data_dict['custom_naam'], 
            data_dict['positie'], data_dict['rating'], data_dict['advies'], 
            data_dict['tekst'], data_dict['datum']
        ))
        conn.commit()
        return True
    except Exception as e:
        st.error(f"Fout bij opslaan: {e}")
        return False
    finally:
        if conn: conn.close()

# -----------------------------------------------------------------------------
# 2. SETUP & UPLOAD
# -----------------------------------------------------------------------------
valid_opts = get_valid_options()

if st.session_state.import_df is None:
    st.session_state.scout_map = load_scout_map()
    st.session_state.name_memory = load_name_memory()
    
    st.info(f"💡 Systeem klaar. {len(st.session_state.name_memory)} koppelingen in geheugen.")
    uploaded_file = st.file_uploader("Upload CSV (Screening/Scouting)", type=['csv'])
    
    if uploaded_file:
        try:
            df = pd.read_csv(uploaded_file)
            
            # --- DEDUPLICATIE ---
            if 'Resume' in df.columns:
                with st.spinner("Controleren op duplicaten..."):
                    existing = get_existing_report_hashes()
                    df['norm'] = df['Resume'].apply(normalize_text)
                    # Filter: tekst niet in DB én tekst niet leeg
                    df_clean = df[(~df['norm'].isin(existing)) & (df['norm'] != "")].drop(columns=['norm'])
                    
                    skipped = len(df) - len(df_clean)
                    if skipped > 0:
                        st.warning(f"📉 {skipped} rapporten overgeslagen (al in database).")
            else:
                df_clean = df

            if len(df_clean) > 0:
                if st.button(f"Start Import ({len(df_clean)} rapporten)"):
                    st.session_state.import_df = df_clean.reset_index(drop=True)
                    st.session_state.current_index = 0
                    st.rerun()
            else:
                st.balloons()
                st.success("✅ Alles is al verwerkt!")
        except Exception as e:
            st.error(f"Fout bij lezen CSV: {e}")

# -----------------------------------------------------------------------------
# 3. WIZARD INTERFACE
# -----------------------------------------------------------------------------
else:
    df = st.session_state.import_df
    idx = st.session_state.current_index
    
    if idx >= len(df):
        st.balloons()
        st.success("✅ Import Voltooid!")
        if st.button("Nieuw bestand"):
            st.session_state.import_df = None
            st.rerun()
        st.stop()
        
    row = df.iloc[idx]
    legacy_full_string = str(row.get('Player')).strip()
    
    # 1. Check Geheugen
    memory_match_id = st.session_state.name_memory.get(legacy_full_string)
    
    # 2. Naam Parsing voor zoekfunctie (Splits 'Naam - Team')
    parsed_name_only, _ = parse_legacy_player_string(legacy_full_string)

    # UI PROGRESS
    st.progress((idx / len(df)), text=f"Rij {idx + 1} / {len(df)}")
    
    # KOLOMMEN: TERUG NAAR DE ORIGINELE INDELING
    col_source, col_edit, col_match = st.columns([1, 1, 1.5])
    
    # ---------------------------------------------------------
    # KOLOM 1: BRON DATA (LEES-MODUS)
    # ---------------------------------------------------------
    with col_source:
        st.subheader("📄 Origineel")
        st.info(f"**{legacy_full_string}**")
        st.write(f"Team: {row.get('Team')}")
        st.write(f"Datum: {row.get('DATE')}")
        
        # OUDE FUNCTIONALITEIT TERUG: Originele waardes tonen
        st.text_input("CSV Positie", value=str(row.get('Starting Position')), disabled=True, key="orig_pos")
        st.text_input("CSV Advies", value=str(row.get('Advies')), disabled=True, key="orig_adv")
        
        scout_email = str(row.get('SCOUT')).lower().strip()
        found_scout_id = st.session_state.scout_map.get(scout_email, 1) # Default Admin (1)
        st.caption(f"Scout email: {scout_email} -> ID: {found_scout_id}")

    # ---------------------------------------------------------
    # KOLOM 2: CORRIGEER DATA
    # ---------------------------------------------------------
    with col_edit:
        st.subheader("✍️ Corrigeer")
        
        # Positie Mapping Logic
        raw_pos = str(row.get('Starting Position', '')).strip()
        mapping_pos = {"WBL": "Verdediger", "WBR": "Verdediger", "CDM": "Middenvelder", "CAM": "Middenvelder", "CF": "Aanvaller"} 
        
        default_pos_index = 0
        if raw_pos in valid_opts["posities"]:
             default_pos_index = valid_opts["posities"].index(raw_pos)
        elif raw_pos in mapping_pos and mapping_pos[raw_pos] in valid_opts["posities"]:
             default_pos_index = valid_opts["posities"].index(mapping_pos[raw_pos])
        
        final_pos = st.selectbox("Positie", valid_opts["posities"], index=default_pos_index, key=f"pos_{idx}")

        # Advies Mapping Logic
        raw_adv = str(row.get('Advies', '')).strip()
        mapping_adv = {"Future Sign": "A", "Sign": "A", "Follow": "B", "Not": "C"} 
        
        default_adv_index = 0
        if raw_adv in valid_opts["advies"]:
            default_adv_index = valid_opts["advies"].index(raw_adv)
        elif raw_adv in mapping_adv and mapping_adv[raw_adv] in valid_opts["advies"]:
            default_adv_index = valid_opts["advies"].index(mapping_adv[raw_adv])
            
        final_adv = st.selectbox("Advies", valid_opts["advies"], index=default_adv_index, key=f"adv_{idx}")

        # Rating & Tekst
        raw_rating = pd.to_numeric(row.get('Match Rating'), errors='coerce')
        final_rating = st.slider("Rating", 1, 10, int(raw_rating * 2) if not pd.isna(raw_rating) else 6, key=f"rat_{idx}")
        
        raw_txt = str(row.get('Resume'))
        if raw_txt == 'nan': raw_txt = str(row.get('Scouting Notes', ''))
        final_tekst = st.text_area("Tekst", raw_txt, height=150, key=f"txt_{idx}")
        
        try: final_date = pd.to_datetime(row.get('DATE')).date()
        except: final_date = datetime.date.today()

    # ---------------------------------------------------------
    # KOLOM 3: KOPPELEN (MET GEHEUGEN)
    # ---------------------------------------------------------
    with col_match:
        st.subheader("🔗 Koppel aan Database")
        
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

        # SITUATIE A: SPELER ZIT IN HET GEHEUGEN
        if memory_match_id:
            db_player_text = get_player_details(memory_match_id)
            st.success(f"🧠 **Herkend uit geheugen!**")
            st.markdown(f"Wordt gekoppeld aan: **{db_player_text}**")
            
            c_conf, c_edit = st.columns([2, 1])
            if c_conf.button("💾 Bevestig & Opslaan", type="primary", key=f"mem_save_{idx}"):
                save_packet['speler_id'] = str(memory_match_id)
                if save_legacy_report(save_packet):
                    st.session_state.current_index += 1
                    st.rerun()
            
            if c_edit.button("Wijzig"):
                del st.session_state.name_memory[legacy_full_string]
                st.rerun()

        # SITUATIE B: NIEUWE SPELER (ZOEKEN)
        else:
            # We vullen de zoekbalk vooraf in met de 'gesplitste' naam (parsed_name_only)
            # Hierdoor zoekt hij op 'Jantje' ipv 'Jantje - Ajax'
            search_input = st.text_input("Zoek speler:", value=parsed_name_only, key=f"search_{idx}")
            results = search_players_fuzzy(search_input)
            
            if not results.empty:
                st.write("Resultaten:")
                for _, db_row in results.iterrows():
                    # KNOP: Sla rapport op EN onthoud keuze voor de toekomst
                    btn_label = f"🔗 {db_row['commonname']} ({db_row['team_name']})"
                    if st.button(btn_label, key=f"btn_{db_row['id']}"):
                        save_packet['speler_id'] = str(db_row['id'])
                        
                        if save_legacy_report(save_packet):
                            # HIER SLAAN WE HET OP IN GEHEUGEN
                            save_new_mapping(legacy_full_string, db_row['id'])
                            st.session_state.current_index += 1
                            st.rerun()
            else:
                st.warning("Geen speler gevonden in DB.")

            st.markdown("---")
            c_cust, c_skip = st.columns(2)
            if c_cust.button("💾 Custom Opslaan"):
                save_packet['custom_naam'] = legacy_full_string
                if save_legacy_report(save_packet):
                    st.session_state.current_index += 1
                    st.rerun()
            
            if c_skip.button("⏭️ Overslaan"):
                st.session_state.current_index += 1
                st.rerun()
