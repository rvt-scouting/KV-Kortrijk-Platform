import streamlit as st
import pandas as pd
from utils import run_query, init_connection
import datetime

st.set_page_config(page_title="Legacy Data Import", page_icon="🏗️", layout="wide")

st.title("🏗️ Legacy Data Import Tool")
st.markdown("Slimme import tool: Corrigeer data & koppel aan DB (slaat automatisch duplicaten over).")

# -----------------------------------------------------------------------------
# 0. INITIALISATIE SESSION STATE
# -----------------------------------------------------------------------------
if 'import_df' not in st.session_state: st.session_state.import_df = None
if 'current_index' not in st.session_state: st.session_state.current_index = 0
if 'scout_map' not in st.session_state: st.session_state.scout_map = {}

# -----------------------------------------------------------------------------
# 1. HULPFUNCTIES
# -----------------------------------------------------------------------------

def normalize_text(text):
    """Maakt tekst 'schoon' voor strikte vergelijking: alles kleine letters, geen spaties/enters."""
    if not isinstance(text, str):
        return ""
    # Split op whitespace en join weer aan elkaar -> verwijdert alle \n, \t en spaties
    return "".join(text.lower().split())

def run_uncached_query(query, params=None):
    """
    Voert een query uit ZONDER cache. 
    Cruciaal voor deduplicatie checks die altijd live data moeten zien.
    """
    conn = init_connection()
    try:
        return pd.read_sql(query, conn, params=params)
    except Exception as e:
        st.error(f"SQL Error (Uncached): {e}")
        return pd.DataFrame()
    finally:
        conn.close()

@st.cache_data
def load_scout_map():
    """Haalt alle scouts op en maakt een map: {email: id}"""
    try:
        # Hier mag wel cache op, scouts veranderen niet elke minuut
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

def get_existing_report_hashes():
    """Haalt alle rapport teksten op en geeft een set van genormaliseerde strings terug."""
    try:
        # LET OP: Gebruik run_uncached_query om zeker te zijn van de actuele DB status
        query = "SELECT rapport_tekst FROM scouting.rapporten WHERE rapport_tekst IS NOT NULL"
        df = run_uncached_query(query)
        
        if not df.empty:
            # We maken een set van 'kale' strings (zonder spaties/enters)
            return set(df['rapport_tekst'].apply(normalize_text).tolist())
    except Exception as e:
        st.error(f"Kon bestaande rapporten niet ophalen voor check: {e}")
    return set()

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
# 2. SETUP & UPLOAD MET DEDUPLICATIE
# -----------------------------------------------------------------------------
valid_opts = get_valid_options()

if st.session_state.import_df is None:
    st.session_state.scout_map = load_scout_map()
    
    st.info("💡 Tip: Het systeem checkt live in de database op duplicaten (cache disabled).")
    uploaded_file = st.file_uploader("Upload CSV (Screening/Scouting)", type=['csv'])
    
    if uploaded_file:
        try:
            df = pd.read_csv(uploaded_file)
            total_rows_csv = len(df)
            
            # --- DEDUPLICATIE LOGICA ---
            if 'Resume' in df.columns:
                with st.spinner("Bezig met controleren op duplicaten (Live DB Check)..."):
                    # 1. Haal alle unieke teksten uit de DB (zonder cache)
                    existing_hashes = get_existing_report_hashes()
                    
                    # 2. Maak genormaliseerde versie van CSV tekst
                    df['norm_text'] = df['Resume'].apply(normalize_text)
                    
                    # 3. Interne deduplicatie: Als de CSV zelf dubbele rijen bevat, gooi die er eerst uit
                    df_internal_dedup = df.drop_duplicates(subset=['norm_text'])
                    internal_dupes = len(df) - len(df_internal_dedup)
                    
                    # 4. DB Filter: behoud rijen waarvan de genormaliseerde tekst NIET in DB zit
                    df_clean = df_internal_dedup[
                        (~df_internal_dedup['norm_text'].isin(existing_hashes)) & 
                        (df_internal_dedup['norm_text'] != "")
                    ].drop(columns=['norm_text']) # Ruim hulpkolom op
                    
                    # Statistieken
                    db_dupes = len(df_internal_dedup) - len(df_clean)
                    total_skipped = internal_dupes + db_dupes
            else:
                df_clean = df
                total_skipped = 0
                st.warning("⚠️ Kolom 'Resume' niet gevonden in CSV, deduplicatie overgeslagen.")

            # --- RESULTAAT TONEN & STARTKNOP ---
            if total_skipped > 0:
                st.warning(f"📉 **{total_skipped}** rapporten overgeslagen ({internal_dupes} dubbel in CSV, {db_dupes} al in DB).")
            
            if len(df_clean) > 0:
                st.success(f"🚀 Klaar om **{len(df_clean)}** nieuwe rapporten te verwerken.")
                
                if st.button("Start Import Proces"):
                    st.session_state.import_df = df_clean.reset_index(drop=True)
                    st.session_state.current_index = 0
                    st.rerun()
            else:
                st.balloons()
                st.info("✅ Alle rapporten in deze CSV staan al in de database (of zijn duplicaten)! Je hoeft niets te doen.")

        except Exception as e:
            st.error(f"Kan bestand niet verwerken: {e}")

# -----------------------------------------------------------------------------
# 3. MATCHING WIZARD
# -----------------------------------------------------------------------------
else:
    df = st.session_state.import_df
    idx = st.session_state.current_index
    
    # Check of we klaar zijn
    if idx >= len(df):
        st.balloons()
        st.success("✅ Import Voltooid! Alle nieuwe rapporten zijn verwerkt.")
        if st.button("Nieuw bestand uploaden"):
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
    
    # ... (Rest van de UI code blijft exact hetzelfde als je origineel, hieronder voor volledigheid)
    
    # ---------------------------------------------------------
    # KOLOM 1: BRON DATA (ReadOnly)
    # ---------------------------------------------------------
    with col_source:
        st.subheader("📄 Origineel")
        st.info(f"**{legacy_player_name}**")
        st.write(f"Team: {row.get('Team')}")
        st.write(f"Datum: {row.get('DATE')}")
        
        st.text_input("CSV Positie", value=str(row.get('Starting Position')), disabled=True)
        st.text_input("CSV Advies", value=str(row.get('Advies')), disabled=True)
        
        scout_email = str(row.get('SCOUT')).lower().strip()
        found_scout_id = st.session_state.scout_map.get(scout_email, 1)

    # ---------------------------------------------------------
    # KOLOM 2: CORRIGEER DATA
    # ---------------------------------------------------------
    with col_edit:
        st.subheader("✍️ Corrigeer")
        
        # Positie
        raw_pos = str(row.get('Starting Position', '')).strip()
        mapping_pos = {"WBL": "Verdediger", "WBR": "Verdediger", "CDM": "Middenvelder", "CAM": "Middenvelder", "CF": "Aanvaller"} 
        
        default_pos_index = 0
        if raw_pos in valid_opts["posities"]:
             default_pos_index = valid_opts["posities"].index(raw_pos)
        elif raw_pos in mapping_pos and mapping_pos[raw_pos] in valid_opts["posities"]:
             default_pos_index = valid_opts["posities"].index(mapping_pos[raw_pos])
        
        final_pos = st.selectbox("Positie", valid_opts["posities"], index=default_pos_index, key=f"pos_{idx}")

        # Advies
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
        final_tekst = st.text_area("Tekst", raw_txt, height=100, key=f"txt_{idx}")
        
        try:
            final_date = pd.to_datetime(row.get('DATE')).date()
        except:
            final_date = datetime.date.today()

    # ---------------------------------------------------------
    # KOLOM 3: KOPPELEN
    # ---------------------------------------------------------
    with col_match:
        st.subheader("🔗 Koppel & Opslaan")
        
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
