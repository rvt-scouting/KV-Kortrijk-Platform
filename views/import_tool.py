import streamlit as st
import pandas as pd
from utils import run_query, init_connection
import datetime

st.set_page_config(page_title="Legacy Data Import", page_icon="🧠", layout="wide")

st.title("🧠 Slimme Import Tool")
# Progressie balk staat nu bovenaan voor duidelijkheid tijdens auto-modus
if 'import_df' in st.session_state and st.session_state.import_df is not None:
    df = st.session_state.import_df
    idx = st.session_state.current_index
    if len(df) > 0:
        st.progress((idx / len(df)), text=f"Verwerken: Rij {idx + 1} / {len(df)}")

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
    try:
        df = run_uncached_query("SELECT legacy_name, speler_id FROM scouting.legacy_names_map")
        if not df.empty:
            return dict(zip(df['legacy_name'], df['speler_id']))
    except:
        return {} 

def save_new_mapping(legacy_name, speler_id):
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

def search_players_fuzzy(name_part, limit=20):
    if not name_part or len(name_part) < 2: return pd.DataFrame()
    term = f"%{name_part}%"
    q = f"""
        SELECT p.id, p.commonname, p.firstname, p.lastname, s.name as team_name
        FROM public.players p
        LEFT JOIN public.squads s ON p."currentSquadId" = s.id
        WHERE p.commonname ILIKE %s 
           OR p.lastname ILIKE %s 
           OR p.firstname ILIKE %s
        LIMIT {limit}
    """
    return run_query(q, params=(term, term, term))

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
            
            # Deduplicatie
            if 'Resume' in df.columns:
                with st.spinner("Controleren op duplicaten..."):
                    existing = get_existing_report_hashes()
                    df['norm'] = df['Resume'].apply(normalize_text)
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
    
    # KLAAR CHECK
    if idx >= len(df):
        st.balloons()
        st.success("✅ Import Voltooid!")
        if st.button("Nieuw bestand"):
            st.session_state.import_df = None
            st.rerun()
        st.stop()
        
    row = df.iloc[idx]
    legacy_full_string = str(row.get('Player')).strip()
    
    # Check Geheugen
    memory_match_id = st.session_state.name_memory.get(legacy_full_string)
    
    # Parse Naam voor zoeken
    parsed_name_only, _ = parse_legacy_player_string(legacy_full_string)
    
    col_source, col_edit, col_match = st.columns([1, 1, 1.5])
    
    # --- KOLOM 1: BRON ---
    with col_source:
        st.subheader("📄 Origineel")
        st.info(f"**{legacy_full_string}**")
        st.write(f"Team: {row.get('Team')}")
        st.write(f"Datum: {row.get('DATE')}")
        
        st.text_input("CSV Positie", value=str(row.get('Starting Position')), disabled=True, key=f"orig_pos_{idx}")
        st.text_input("CSV Advies", value=str(row.get('Advies')), disabled=True, key=f"orig_adv_{idx}")
        
        scout_email = str(row.get('SCOUT')).lower().strip()
        found_scout_id = st.session_state.scout_map.get(scout_email, 1)
        st.caption(f"Scout: {scout_email} -> ID: {found_scout_id}")

    # --- KOLOM 2: CORRIGEER (AUTOMATISCH) ---
    with col_edit:
        st.subheader("✍️ Corrigeer")
        
        # 1. POSITIE MAPPING
        raw_pos = str(row.get('Starting Position', '')).strip()
        mapping_pos = {
            "WBL": "Verdediger", "WBR": "Verdediger", "CDM": "Middenvelder", 
            "CAM": "Middenvelder", "CF": "Aanvaller"
        } 
        
        default_pos_index = 0
        if raw_pos in valid_opts["posities"]:
             default_pos_index = valid_opts["posities"].index(raw_pos)
        elif raw_pos in mapping_pos and mapping_pos[raw_pos] in valid_opts["posities"]:
             default_pos_index = valid_opts["posities"].index(mapping_pos[raw_pos])
        
        final_pos = st.selectbox("Positie", valid_opts["posities"], index=default_pos_index, key=f"pos_{idx}")

        # 2. ADVIES MAPPING
        raw_adv_original = str(row.get('Advies', '')).strip()
        raw_adv_lower = raw_adv_original.lower()

        mapping_adv = {
            "get - promising youngster": "Future Sign",
            "get - first team": "Sign",
            "get - priority": "Sign",
            "get - backup": "Follow",
            "nan": "Follow",
            "future sign": "Future Sign",
            "sign": "Sign",
            "follow": "Follow",
            "not": "Not"
        } 
        
        target_val = None
        if raw_adv_lower in mapping_adv:
            target_val = mapping_adv[raw_adv_lower]
        
        found_index = -1
        fallback_index = len(valid_opts["advies"]) - 1 if valid_opts["advies"] else 0
        
        if target_val:
            for i, opt in enumerate(valid_opts["advies"]):
                if str(opt).strip().upper().startswith(target_val.upper()):
                    found_index = i
                    break
        
        if found_index == -1:
             if raw_adv_original in valid_opts["advies"]:
                 found_index = valid_opts["advies"].index(raw_adv_original)

        final_adv_index = found_index if found_index != -1 else fallback_index
        final_adv = st.selectbox("Advies", valid_opts["advies"], index=final_adv_index, key=f"adv_{idx}")

        # 3. RATING & TEKST
        raw_rating = pd.to_numeric(row.get('Match Rating'), errors='coerce')
        final_rating = st.slider("Rating", 1, 10, int(raw_rating * 2) if not pd.isna(raw_rating) else 6, key=f"rat_{idx}")
        
        raw_txt = str(row.get('Resume'))
        if raw_txt == 'nan': raw_txt = str(row.get('Scouting Notes', ''))
        final_tekst = st.text_area("Tekst", raw_txt, height=150, key=f"txt_{idx}")
        
        try: final_date = pd.to_datetime(row.get('DATE')).date()
        except: final_date = datetime.date.today()

    # --- KOLOM 3: KOPPELEN (NU MET AUTO-SAVE) ---
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

        # --- AUTOMATISCHE ROUTE ---
        if memory_match_id:
            # We tonen even kort wat er gebeurt (optioneel, gaat vaak te snel om te lezen)
            db_player_text = get_player_details(memory_match_id)
            st.success(f"⚡ **Auto-Match!** {legacy_full_string} -> {db_player_text}")
            
            # DIRECT OPSLAAN EN DOORGAAN
            save_packet['speler_id'] = str(memory_match_id)
            if save_legacy_report(save_packet):
                st.toast(f"✅ Opgeslagen: {legacy_full_string}") # Subtiele notificatie
                st.session_state.current_index += 1
                st.rerun()

        # --- HANDMATIGE ROUTE (ALLEEN ALS NIET HERKEND) ---
        else:
            c_search, c_limit = st.columns([3, 1])
            with c_search:
                search_input = st.text_input("Zoek speler:", value=parsed_name_only, key=f"search_{idx}")
            with c_limit:
                limit_val = st.number_input("#", min_value=5, max_value=100, value=20, step=10, key=f"lim_{idx}")

            results = search_players_fuzzy(search_input, limit=limit_val)
            
            if not results.empty:
                st.write(f"Resultaten ({len(results)}):")
                with st.container(height=300, border=True):
                    for _, db_row in results.iterrows():
                        btn_label = f"🔗 {db_row['commonname']} ({db_row['team_name']})"
                        if st.button(btn_label, key=f"btn_{db_row['id']}"):
                            save_packet['speler_id'] = str(db_row['id'])
                            
                            if save_legacy_report(save_packet):
                                # LEERMOMENT: Sla op in geheugen
                                save_new_mapping(legacy_full_string, db_row['id'])
                                st.session_state.current_index += 1
                                st.rerun()
            else:
                st.warning("Geen speler gevonden. Probeer een andere zoekterm.")

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
