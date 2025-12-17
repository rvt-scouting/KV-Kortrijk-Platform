import streamlit as st
import pandas as pd
from utils import run_query, init_connection
import datetime

st.set_page_config(page_title="Legacy Data Import", page_icon="🧠", layout="wide")

st.title("🧠 Slimme Import met Geheugen")
st.markdown("Deze tool leert van je keuzes. Eerdere koppelingen worden onthouden.")

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

# --- GEHEUGEN FUNCTIES (NIEUW) ---
def load_name_memory():
    """Laadt alle opgeslagen koppelingen in een dictionary."""
    try:
        df = run_uncached_query("SELECT legacy_name, speler_id FROM scouting.legacy_names_map")
        if not df.empty:
            return dict(zip(df['legacy_name'], df['speler_id']))
    except Exception:
        return {} # Tabel bestaat misschien nog niet
    return {}

def save_new_mapping(legacy_name, speler_id):
    """Slaat een nieuwe koppeling op in de database."""
    conn = init_connection()
    try:
        with conn.cursor() as cur:
            # Upsert: Als naam al bestaat, update ID (voor de zekerheid)
            query = """
                INSERT INTO scouting.legacy_names_map (legacy_name, speler_id)
                VALUES (%s, %s)
                ON CONFLICT (legacy_name) DO UPDATE SET speler_id = EXCLUDED.speler_id;
            """
            cur.execute(query, (legacy_name, speler_id))
            conn.commit()
            # Update ook direct de sessie zodat we niet hoeven te herladen
            st.session_state.name_memory[legacy_name] = speler_id
    except Exception as e:
        st.warning(f"Kon koppeling niet onthouden: {e}")
    finally:
        conn.close()

def get_player_details(player_id):
    """Haalt info op voor de automatische match weergave."""
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

# --- BESTAANDE FUNCTIES ---
@st.cache_data
def load_scout_map():
    try:
        df = run_query("SELECT id, email FROM scouting.gebruikers")
        return dict(zip(df['email'].str.lower().str.strip(), df['id']))
    except:
        return {}

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
    st.session_state.name_memory = load_name_memory() # Laad geheugen!
    
    st.info(f"💡 Geheugen geladen: **{len(st.session_state.name_memory)}** bekende spelernamen.")
    uploaded_file = st.file_uploader("Upload CSV", type=['csv'])
    
    if uploaded_file:
        try:
            df = pd.read_csv(uploaded_file)
            
            # --- DEDUPLICATIE ---
            if 'Resume' in df.columns:
                with st.spinner("Checken op duplicaten..."):
                    existing = get_existing_report_hashes()
                    df['norm'] = df['Resume'].apply(normalize_text)
                    df_clean = df[(~df['norm'].isin(existing)) & (df['norm'] != "")].drop(columns=['norm'])
                    
                    if len(df_clean) < len(df):
                        st.warning(f"📉 {len(df) - len(df_clean)} duplicaten overgeslagen.")
            else:
                df_clean = df

            if len(df_clean) > 0:
                if st.button(f"Start Import ({len(df_clean)} rapporten)"):
                    st.session_state.import_df = df_clean.reset_index(drop=True)
                    st.session_state.current_index = 0
                    st.rerun()
            else:
                st.success("Alle rapporten staan al in de database!")
        except Exception as e:
            st.error(str(e))

# -----------------------------------------------------------------------------
# 3. WIZARD MET GEHEUGEN
# -----------------------------------------------------------------------------
else:
    df = st.session_state.import_df
    idx = st.session_state.current_index
    
    if idx >= len(df):
        st.success("✅ Klaar! Alle rapporten verwerkt.")
        if st.button("Nieuwe upload"):
            st.session_state.import_df = None
            st.rerun()
        st.stop()
        
    row = df.iloc[idx]
    legacy_name = str(row.get('Player')).strip()
    
    # Check Geheugen
    memory_match_id = st.session_state.name_memory.get(legacy_name)

    # UI
    progress = (idx / len(df))
    st.progress(progress, text=f"Rij {idx + 1} / {len(df)}")
    
    c1, c2, c3 = st.columns([1, 1, 1.5])
    
    with c1:
        st.info(f"Origineel: **{legacy_name}**")
        st.write(f"Team: {row.get('Team')}")
        st.caption(str(row.get('DATE')))

    with c2:
        # Quick Edit Form
        pos_opts = valid_opts["posities"]
        def_pos = 0
        raw_pos = str(row.get('Starting Position', ''))
        # Simpele mapping poging
        if raw_pos in pos_opts: def_pos = pos_opts.index(raw_pos)
        
        final_pos = st.selectbox("Positie", pos_opts, index=def_pos, key=f"p{idx}")
        
        # Advies
        adv_opts = valid_opts["advies"]
        final_adv = st.selectbox("Advies", adv_opts, key=f"a{idx}")
        
        # Rating & Tekst
        r = pd.to_numeric(row.get('Match Rating'), errors='coerce')
        rate = st.slider("Rating", 1, 10, int(r*2) if not pd.isna(r) else 6, key=f"r{idx}")
        
        txt = str(row.get('Resume', ''))
        if txt == 'nan': txt = ""
        final_txt = st.text_area("Tekst", txt, height=100, key=f"t{idx}")
        
        # Datum
        try: d = pd.to_datetime(row.get('DATE')).date()
        except: d = datetime.date.today()

    with c3:
        st.subheader("🔗 Koppeling")
        
        # Bereid data voor
        packet = {
            "scout_id": st.session_state.scout_map.get(str(row.get('SCOUT')).lower().strip(), 1),
            "positie": final_pos, "advies": final_adv, "rating": rate,
            "tekst": final_txt, "datum": d, "speler_id": None, "custom_naam": None
        }

        # SCENARIO 1: We kennen deze speler al!
        if memory_match_id:
            player_info = get_player_details(memory_match_id)
            st.success(f"✅ Herkend! Wordt gekoppeld aan:\n**{player_info}**")
            
            col_save, col_change = st.columns([2,1])
            if col_save.button("💾 Bevestig & Opslaan", type="primary", key=f"auto_{idx}"):
                packet['speler_id'] = str(memory_match_id)
                if save_legacy_report(packet):
                    st.session_state.current_index += 1
                    st.rerun()
            
            if col_change.button("Wijzig"):
                # Verwijder tijdelijk uit geheugen sessie om zoeken mogelijk te maken
                del st.session_state.name_memory[legacy_name]
                st.rerun()

        # SCENARIO 2: Onbekend, zoek handmatig
        else:
            search = st.text_input("Zoek in DB", value=legacy_name, key=f"s{idx}")
            res = search_players_fuzzy(search)
            
            if not res.empty:
                for _, db_r in res.iterrows():
                    # De knop slaat NU OOK op in het geheugen
                    if st.button(f"🔗 Koppel: {db_r['commonname']} ({db_r['team_name']})", key=f"b{db_r['id']}"):
                        packet['speler_id'] = str(db_r['id'])
                        
                        # 1. Sla rapport op
                        if save_legacy_report(packet):
                            # 2. LEER hiervan (Sla op in geheugen tabel)
                            save_new_mapping(legacy_name, db_r['id'])
                            
                            st.session_state.current_index += 1
                            st.rerun()
            
            st.markdown("---")
            if st.button("Als Custom Opslaan (Geen DB link)"):
                packet['custom_naam'] = legacy_name
                save_legacy_report(packet)
                st.session_state.current_index += 1
                st.rerun()
            
            if st.button("Overslaan"):
                st.session_state.current_index += 1
                st.rerun()
