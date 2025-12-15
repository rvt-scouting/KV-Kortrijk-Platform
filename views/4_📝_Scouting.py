import streamlit as st
import pandas as pd
import json
from utils import run_query, init_connection

st.set_page_config(page_title="Live Scouting", page_icon="📝", layout="wide")

# -----------------------------------------------------------------------------
# 1. HULPFUNCTIES
# -----------------------------------------------------------------------------

@st.cache_data
def get_scouting_options_safe(table_name):
    """ 
    Haalt opties op. 
    Garandeert ALTIJD een dataframe met columns ['value', 'label'].
    FIX: Werkt nu ook voor tabellen met maar 1 kolom.
    """
    # 1. Definieer Noodlijsten (Fallback)
    fallback_data = pd.DataFrame(columns=['value', 'label'])
    
    if "posities" in table_name:
        fallback_data = pd.DataFrame({
            'value': ["Doelman", "Verdediger", "Middenvelder", "Aanvaller"],
            'label': ["Doelman", "Verdediger", "Middenvelder", "Aanvaller"]
        })
    elif "advies" in table_name:
        fallback_data = pd.DataFrame({
            'value': ["A", "B", "C"],
            'label': ["A", "B", "C"]
        })
    elif "profielen" in table_name:
        fallback_data = pd.DataFrame({
            'value': ["P1", "P2"],
            'label': ["P1", "P2"]
        })
    elif "shortlists" in table_name:
        fallback_data = pd.DataFrame({
            'value': [1],
            'label': ["Algemeen"]
        })

    try:
        # 2. Probeer Database
        df = run_query(f"SELECT * FROM scouting.{table_name}")
        
        if df.empty: 
            return fallback_data
        
        cols = df.columns.tolist()
        
        # --- SCENARIO 1: TABEL HEEFT MAAR 1 KOLOM (bv. alleen 'code') ---
        if len(cols) == 1:
            col_name = cols[0]
            # We gebruiken die ene kolom als zowel de waarde als het label
            df['value'] = df[col_name]
            df['label'] = df[col_name]
            return df[['value', 'label']]

        # --- SCENARIO 2: TABEL HEEFT MEERDERE KOLOMMEN (ID + Naam) ---
        # Zoek label kolom
        candidates = ['naam', 'label', 'status', 'omschrijving', 'code', 'type']
        label_col = next((c for c in cols if c in candidates), cols[1])
        value_col = 'id' if 'id' in cols else cols[0]
        
        # Rename en return
        result = df[[value_col, label_col]].rename(columns={value_col: 'value', label_col: 'label'})
        return result

    except Exception as e:
        # 3. Als DB faalt, geef noodlijst terug
        return fallback_data

def save_report_to_db(data):
    """ Slaat rapport op (Upsert) """
    conn = None
    try:
        conn = init_connection()
        cur = conn.cursor()
        
        # IDs altijd strings maken voor veiligheid
        p_scout = str(data['scout_id'])
        p_speler = str(data['speler_id'])
        p_match = str(data['wedstrijd_id'])
        
        check_q = "SELECT id FROM scouting.rapporten WHERE scout_id = %s AND speler_id = %s AND wedstrijd_id = %s"
        cur.execute(check_q, (p_scout, p_speler, p_match))
        existing = cur.fetchone()
        
        if existing:
            update_q = """
                UPDATE scouting.rapporten SET
                    positie_gespeeld = %s, profiel_code = %s, advies = %s,
                    beoordeling = %s, rapport_tekst = %s, gouden_busser = %s,
                    shortlist_id = %s, aangemaakt_op = NOW()
                WHERE id = %s
            """
            cur.execute(update_q, (
                data['positie_gespeeld'], data['profiel_code'], data['advies'], 
                data['beoordeling'], data['rapport_tekst'], data['gouden_busser'], 
                data['shortlist_id'], existing[0]
            ))
        else:
            insert_q = """
                INSERT INTO scouting.rapporten 
                (scout_id, speler_id, wedstrijd_id, competitie_id, positie_gespeeld, 
                 profiel_code, advies, beoordeling, rapport_tekst, gouden_busser, shortlist_id, aangemaakt_op)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            """
            cur.execute(insert_q, (
                p_scout, p_speler, p_match, str(data['competitie_id']),
                data['positie_gespeeld'], data['profiel_code'], data['advies'], 
                data['beoordeling'], data['rapport_tekst'], data['gouden_busser'], 
                data['shortlist_id']
            ))
            
        conn.commit()
        cur.close()
        return True
    except Exception as e:
        st.error(f"Save Error: {e}")
        return False
    finally:
        if conn: conn.close()

if "scout_drafts" not in st.session_state: st.session_state.scout_drafts = {}
if 'user_info' not in st.session_state or not st.session_state.user_info:
    st.warning("⚠️ Log in AUB."); st.stop()

current_scout_id = str(st.session_state.user_info.get('id'))
current_scout_name = st.session_state.user_info.get('naam', 'Onbekend')

# -----------------------------------------------------------------------------
# 2. WEDSTRIJD SELECTIE
# -----------------------------------------------------------------------------
st.title("📝 Live Match Scouting")

# Haal opties op (Veilige functie)
# Zorg dat je 'Cache Clear' doet als het nog steeds fout gaat!
opties_posities = get_scouting_options_safe('opties_posities')
opties_profielen = get_scouting_options_safe('opties_profielen')
opties_advies = get_scouting_options_safe('opties_advies')
opties_shortlists = get_scouting_options_safe('shortlists')

st.sidebar.header("Selecteer Wedstrijd")

try:
    df_seasons = run_query("SELECT DISTINCT season FROM public.iterations ORDER BY season DESC")
    seasons = df_seasons['season'].tolist()
    sel_season = st.sidebar.selectbox("1. Seizoen", seasons)
except: st.error("DB Fout"); st.stop()

if sel_season:
    df_comps = run_query('SELECT DISTINCT "competitionName" FROM public.iterations WHERE season = %s ORDER BY "competitionName"', params=(sel_season,))
    comps = df_comps['competitionName'].tolist()
    sel_comp = st.sidebar.selectbox("2. Competitie", comps)
else: st.stop()

if sel_season and sel_comp:
    match_query = """
        SELECT m.id, m."scheduledDate", m."iterationId", h.name as home, a.name as away
        FROM public.matches m
        JOIN public.squads h ON m."homeSquadId" = h.id
        JOIN public.squads a ON m."awaySquadId" = a.id
        WHERE m."iterationId" IN (SELECT id FROM public.iterations WHERE season = %s AND "competitionName" = %s)
        ORDER BY m."scheduledDate" DESC
    """
    df_matches = run_query(match_query, params=(sel_season, sel_comp))
    
    if df_matches.empty: st.info("Geen wedstrijden."); st.stop()

    match_opts = {f"{r['home']} vs {r['away']} ({r['scheduledDate'].strftime('%d-%m')})": r for _, r in df_matches.iterrows()}
    sel_match_label = st.sidebar.selectbox("3. Wedstrijd", list(match_opts.keys()))
    sel_match_row = match_opts[sel_match_label]
    selected_match_id = str(sel_match_row['id'])
    selected_comp_id = str(sel_match_row['iterationId'])
    home_team_name = sel_match_row['home']
    away_team_name = sel_match_row['away']
else: st.stop()

st.sidebar.divider()
st.sidebar.write(f"👤 **Scout:** {current_scout_name}")

# -----------------------------------------------------------------------------
# 3. SPELERS OPHALEN
# -----------------------------------------------------------------------------
json_query = 'SELECT "squadHome", "squadAway" FROM public.match_details_full WHERE "id" = %s'
try:
    df_json = run_query(json_query, params=(selected_match_id,))
except Exception as e: st.error(f"Fout JSON: {e}"); st.stop()

if df_json.empty: st.warning("Geen detail data."); st.stop()

def parse_squad_json(json_data, side):
    players_list = []
    try:
        data = json_data if isinstance(json_data, dict) else json.loads(json_data)
        if 'players' in data:
            for p in data['players']:
                players_list.append({
                    'player_id': str(p['id']),
                    'shirt_number': p.get('shirtNumber', '?'),
                    'side': side
                })
    except: pass
    return players_list

home_players = parse_squad_json(df_json.iloc[0]['squadHome'], 'home')
away_players = parse_squad_json(df_json.iloc[0]['squadAway'], 'away')
all_players_data = home_players + away_players

if not all_players_data: st.warning("Geen spelers."); st.stop()

df_p_raw = pd.DataFrame(all_players_data)
player_ids = tuple(df_p_raw['player_id'].unique())

if player_ids:
    name_query = f"SELECT id, commonname FROM public.players WHERE id IN {player_ids}"
    if len(player_ids) == 1: name_query = name_query.replace(f"IN {player_ids}", f"IN ('{player_ids[0]}')")
    
    df_names = run_query(name_query)
    df_names['id'] = df_names['id'].astype(str)
    
    df_players = pd.merge(df_p_raw, df_names, left_on='player_id', right_on='id', how='left')
    df_players['commonname'] = df_players['commonname'].fillna("Onbekend")
    df_players['shirt_number'] = pd.to_numeric(df_players['shirt_number'], errors='coerce').fillna(99)
    df_players = df_players.sort_values(by=['side', 'shirt_number'])
else:
    df_players = df_p_raw
    df_players['commonname'] = "Onbekend"

# -----------------------------------------------------------------------------
# 4. UI: SPLIT VIEW
# -----------------------------------------------------------------------------
col_list, col_editor = st.columns([1, 2])

with col_list:
    st.subheader("Selecties")
    team_tab = st.radio("Team", [home_team_name, away_team_name], horizontal=True, label_visibility="collapsed")
    side_filter = 'home' if team_tab == home_team_name else 'away'
    
    filtered_df = df_players[df_players['side'] == side_filter]
    
    if "active_player_id" not in st.session_state: st.session_state.active_player_id = None

    for _, row in filtered_df.iterrows():
        pid = str(row['player_id'])
        pname = f"{int(row['shirt_number'])}. {row['commonname']}"
        
        draft_key = f"{selected_match_id}_{pid}_{current_scout_id}"
        has_draft = draft_key in st.session_state.scout_drafts
        
        btn_type = "primary" if str(st.session_state.active_player_id) == pid else "secondary"
        icon = "📝" if has_draft else "👤"
        
        if st.button(f"{icon} {pname}", key=f"btn_{pid}", type=btn_type, use_container_width=True):
            st.session_state.active_player_id = pid
            st.rerun()

with col_editor:
    if st.session_state.active_player_id:
        active_pid = str(st.session_state.active_player_id)
        p_row = df_players[df_players['player_id'] == active_pid].iloc[0]
        st.subheader(f"{p_row['commonname']}")
        
        draft_key = f"{selected_match_id}_{active_pid}_{current_scout_id}"
        
        # OPHALEN RAPPORT UIT DB
        if draft_key not in st.session_state.scout_drafts:
            db_q = "SELECT * FROM scouting.rapporten WHERE scout_id = %s AND speler_id = %s AND wedstrijd_id = %s"
            existing = run_query(db_q, params=(current_scout_id, active_pid, selected_match_id))
            
            if not existing.empty:
                rec = existing.iloc[0]
                st.session_state.scout_drafts[draft_key] = {
                    "positie": rec['positie_gespeeld'], "profiel": rec['profiel_code'], "advies": rec['advies'],
                    "rating": int(rec['beoordeling']) if rec['beoordeling'] else 6,
                    "tekst": rec['rapport_tekst'] or "", "gouden": bool(rec['gouden_busser']), "shortlist": rec['shortlist_id']
                }
            else:
                st.session_state.scout_drafts[draft_key] = {
                    "positie": None, "profiel": None, "advies": None,
                    "rating": 6, "tekst": "", "gouden": False, "shortlist": None
                }
        
        draft = st.session_state.scout_drafts[draft_key]

        c1, c2 = st.columns(2)
        def get_idx(val, opts): return opts.index(val) if val in opts else 0

        with c1:
            # POSITIES
            pos_opts = opties_posities['value'].tolist()
            pos_lbls = opties_posities['label'].tolist()
            # Veilig de index bepalen (als lijst leeg is, default naar None)
            curr_pos = draft['positie']
            if not pos_opts: 
                new_pos = None
                st.warning("Geen posities gevonden in DB.")
            else:
                idx_pos = pos_opts.index(curr_pos) if curr_pos in pos_opts else 0
                new_pos = st.selectbox("Positie Gespeeld", pos_opts, index=idx_pos, format_func=lambda x: pos_lbls[pos_opts.index(x)], key="inp_pos")
            
            new_rating = st.slider("Beoordeling (1-10)", 1, 10, draft["rating"], key="inp_rate")

        with c2:
            # ADVIES
            adv_opts = opties_advies['value'].tolist()
            adv_lbls = opties_advies['label'].tolist()
            curr_adv = draft['advies']
            if not adv_opts:
                new_adv = None
            else:
                idx_adv = adv_opts.index(curr_adv) if curr_adv in adv_opts else 0
                new_adv = st.selectbox("Advies", adv_opts, index=idx_adv, format_func=lambda x: adv_lbls[adv_opts.index(x)], key="inp_adv")

            # PROFIEL
            prof_opts = opties_profielen['value'].tolist()
            prof_lbls = opties_profielen['label'].tolist()
            curr_prof = draft['profiel']
            if not prof_opts:
                new_prof = None
            else:
                idx_prof = prof_opts.index(curr_prof) if curr_prof in prof_opts else 0
                new_prof = st.selectbox("Profiel Type", prof_opts, index=idx_prof, format_func=lambda x: prof_lbls[prof_opts.index(x)], key="inp_prof")

        new_tekst = st.text_area("Rapportage", draft["tekst"], height=200, key="inp_txt")
        
        ce1, ce2 = st.columns(2)
        with ce1: new_gouden = st.checkbox("🏆 Gouden Busser", draft["gouden"], key="inp_gold")
        with ce2:
            # SHORTLIST
            sl_opts = [None] + opties_shortlists['value'].tolist()
            sl_lbls = ["Geen"] + opties_shortlists['label'].tolist()
            curr_sl = draft['shortlist']
            idx_sl = sl_opts.index(curr_sl) if curr_sl in sl_opts else 0
            
            def fmt_sl(x):
                try: return sl_lbls[sl_opts.index(x)]
                except: return "Geen"
            
            new_sl = st.selectbox("Zet op Shortlist", sl_opts, index=idx_sl, format_func=fmt_sl, key="inp_sl")

        st.session_state.scout_drafts[draft_key] = {
            "positie": new_pos, "profiel": new_prof, "advies": new_adv,
            "rating": new_rating, "tekst": new_tekst, "gouden": new_gouden, "shortlist": new_sl
        }

        st.markdown("---")
        if st.button("💾 Rapport Opslaan", type="primary", use_container_width=True):
            save_data = {
                "scout_id": current_scout_id, "speler_id": active_pid,
                "wedstrijd_id": selected_match_id, "competitie_id": selected_comp_id,
                "positie_gespeeld": new_pos, "profiel_code": new_prof, "advies": new_adv,
                "beoordeling": new_rating, "rapport_tekst": new_tekst, "gouden_busser": new_gouden, "shortlist_id": new_sl
            }
            if save_report_to_db(save_data):
                st.success("Opgeslagen!")
                st.balloons()
    else:
        st.info("👈 Selecteer een speler.")
