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
    """ Haalt opties op. Garandeert ALTIJD een dataframe met columns ['value', 'label']. """
    fallback_data = pd.DataFrame(columns=['value', 'label'])
    
    if "posities" in table_name:
        fallback_data = pd.DataFrame({'value': ["Doelman", "Verdediger", "Middenvelder", "Aanvaller"], 'label': ["Doelman", "Verdediger", "Middenvelder", "Aanvaller"]})
    elif "advies" in table_name:
        fallback_data = pd.DataFrame({'value': ["A", "B", "C"], 'label': ["A", "B", "C"]})
    elif "profielen" in table_name:
        fallback_data = pd.DataFrame({'value': ["P1"], 'label': ["Standaard"]})
    elif "shortlists" in table_name:
        fallback_data = pd.DataFrame({'value': [1], 'label': ["Algemeen"]})

    try:
        df = run_query(f"SELECT * FROM scouting.{table_name}")
        if df.empty: return fallback_data
        cols = df.columns.tolist()
        if len(cols) == 1:
            col_name = cols[0]
            df['value'] = df[col_name]
            df['label'] = df[col_name]
            return df[['value', 'label']]
        candidates = ['naam', 'label', 'status', 'omschrijving', 'code']
        label_col = next((c for c in cols if c in candidates), cols[1])
        value_col = 'id' if 'id' in cols else cols[0]
        return df[[value_col, label_col]].rename(columns={value_col: 'value', label_col: 'label'})
    except Exception:
        return fallback_data

def save_report_to_db(data):
    """ 
    Slaat rapport op (Upsert). 
    Handelt nu zowel Database IDs als Manuele Namen (Custom) af.
    """
    conn = None
    try:
        conn = init_connection()
        cur = conn.cursor()
        
        # 1. Data voorbereiden (None als het leeg is)
        scout_id = str(data['scout_id'])
        
        # IDs (kunnen None zijn in manuele modus)
        speler_id = str(data['speler_id']) if data['speler_id'] else None
        match_id = str(data['wedstrijd_id']) if data['wedstrijd_id'] else None
        comp_id = str(data['competitie_id']) if data['competitie_id'] else None
        
        # Custom namen (kunnen None zijn in database modus)
        custom_p = data.get('custom_speler_naam')
        custom_m = data.get('custom_wedstrijd_naam')

        # 2. Bepaal de CHECK query (bestaat dit rapport al?)
        # De WHERE clause verandert afhankelijk van of we IDs of Namen hebben
        where_clauses = ["scout_id = %s"]
        params = [scout_id]

        if speler_id:
            where_clauses.append("speler_id = %s")
            params.append(speler_id)
        else:
            where_clauses.append("custom_speler_naam = %s")
            params.append(custom_p)
            # Zorg dat we niet per ongeluk DB spelers overschrijven, dus check dat speler_id NULL is
            where_clauses.append("speler_id IS NULL")

        if match_id:
            where_clauses.append("wedstrijd_id = %s")
            params.append(match_id)
        else:
            where_clauses.append("custom_wedstrijd_naam = %s")
            params.append(custom_m)
            where_clauses.append("wedstrijd_id IS NULL")

        check_q = f"SELECT id FROM scouting.rapporten WHERE {' AND '.join(where_clauses)}"
        cur.execute(check_q, tuple(params))
        existing = cur.fetchone()
        
        # 3. UPSERT Logica
        if existing:
            # UPDATE
            update_q = """
                UPDATE scouting.rapporten SET
                    positie_gespeeld = %s, profiel_code = %s, advies = %s,
                    beoordeling = %s, rapport_tekst = %s, gouden_buzzer = %s,
                    shortlist_id = %s, aangemaakt_op = NOW()
                WHERE id = %s
            """
            cur.execute(update_q, (
                data['positie_gespeeld'], data['profiel_code'], data['advies'], 
                data['beoordeling'], data['rapport_tekst'], data['gouden_buzzer'], 
                data['shortlist_id'], existing[0]
            ))
        else:
            # INSERT (Nu met custom kolommen!)
            insert_q = """
                INSERT INTO scouting.rapporten 
                (scout_id, speler_id, wedstrijd_id, competitie_id, 
                 custom_speler_naam, custom_wedstrijd_naam,
                 positie_gespeeld, profiel_code, advies, beoordeling, 
                 rapport_tekst, gouden_buzzer, shortlist_id, aangemaakt_op)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            """
            cur.execute(insert_q, (
                scout_id, speler_id, match_id, comp_id,
                custom_p, custom_m,
                data['positie_gespeeld'], data['profiel_code'], data['advies'], 
                data['beoordeling'], data['rapport_tekst'], data['gouden_buzzer'], 
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

# Initialisaties
if "scout_drafts" not in st.session_state: st.session_state.scout_drafts = {}
if 'user_info' not in st.session_state or not st.session_state.user_info:
    st.warning("⚠️ Log in AUB."); st.stop()

current_scout_id = str(st.session_state.user_info.get('id', '0'))
current_scout_name = st.session_state.user_info.get('naam', 'Onbekend')

# -----------------------------------------------------------------------------
# 2. WEDSTRIJD SELECTIE (HYBRIDE)
# -----------------------------------------------------------------------------
st.title("📝 Live Match Scouting")

# Variabelen resetten
selected_match_id = None
selected_comp_id = None
custom_match_name = None
home_team_name = "Thuis"
away_team_name = "Uit"

# Opties laden
opties_posities = get_scouting_options_safe('opties_posities')
opties_profielen = get_scouting_options_safe('opties_profielen')
opties_advies = get_scouting_options_safe('opties_advies')
opties_shortlists = get_scouting_options_safe('shortlists')

# --- SIDEBAR LOGICA ---
st.sidebar.header("Match Setup")
is_manual_match = st.sidebar.checkbox("🔓 Manuele Wedstrijd", help="Vink dit aan voor oefenmatchen of wedstrijden die niet in de database staan.")

if is_manual_match:
    # MANUELE MODUS
    custom_match_name = st.sidebar.text_input("Naam Wedstrijd / Tegenstander", placeholder="bv. KVK - Harelbeke")
    if not custom_match_name:
        st.info("👈 Voer een wedstrijd naam in.")
        st.stop()
    st.subheader(f"Wedstrijd: {custom_match_name}")

else:
    # DATABASE MODUS
    try:
        df_seasons = run_query("SELECT DISTINCT season FROM public.iterations ORDER BY season DESC")
        if not df_seasons.empty:
            seasons = df_seasons['season'].tolist()
            sel_season = st.sidebar.selectbox("1. Seizoen", seasons)
        else:
            st.error("Geen seizoenen gevonden."); st.stop()
    except Exception as e: st.error(f"DB Fout: {e}"); st.stop()

    if sel_season:
        df_comps = run_query('SELECT DISTINCT "competitionName" FROM public.iterations WHERE season = %s ORDER BY "competitionName"', params=(sel_season,))
        if not df_comps.empty:
            comps = df_comps['competitionName'].tolist()
            sel_comp = st.sidebar.selectbox("2. Competitie", comps)
        else: st.warning("Geen competities."); st.stop()
    else: st.stop()

    if sel_season and sel_comp:
        match_query = """
            SELECT m.id, m."scheduledDate", m."iterationId", h.name as home, a.name as away
            FROM public.matches m
            JOIN public.squads h ON m."homeSquadId" = h.id
            JOIN public.squads a ON m."awaySquadId" = a.id
            WHERE m."iterationId" IN (SELECT id FROM public.iterations WHERE season = %s AND "competitionName" = %s)
            AND m."scheduledDate" <= NOW()
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
# 3. SPELERS OPHALEN (HYBRIDE)
# -----------------------------------------------------------------------------
df_players = pd.DataFrame()

# A. DATABASE WEDSTRIJD -> Haal spelers op
if selected_match_id:
    json_query = 'SELECT "squadHome", "squadAway" FROM public.match_details_full WHERE "id" = %s'
    try:
        df_json = run_query(json_query, params=(selected_match_id,))
        if not df_json.empty:
            def parse_squad_json(json_data, side):
                players_list = []
                try:
                    data = json_data if isinstance(json_data, dict) else json.loads(json_data)
                    if 'players' in data:
                        for p in data['players']:
                            players_list.append({'player_id': str(p['id']), 'shirt_number': p.get('shirtNumber', '?'), 'side': side})
                except: pass
                return players_list

            home_players = parse_squad_json(df_json.iloc[0]['squadHome'], 'home')
            away_players = parse_squad_json(df_json.iloc[0]['squadAway'], 'away')
            all_players_data = home_players + away_players
            
            if all_players_data:
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

    except Exception as e: st.error(f"Fout laden spelers: {e}")

# -----------------------------------------------------------------------------
# 4. UI: SPLIT VIEW
# -----------------------------------------------------------------------------
col_list, col_editor = st.columns([1, 2])

# Initialize session state for manual player entry logic
if "manual_player_mode" not in st.session_state: st.session_state.manual_player_mode = False
if "manual_player_name" not in st.session_state: st.session_state.manual_player_name = ""

with col_list:
    st.subheader("Selecties")
    
    # 1. Toon Database Spelers (Alleen als we in DB Match modus zitten en er spelers zijn)
    if not is_manual_match and not df_players.empty:
        team_tab = st.radio("Team", [home_team_name, away_team_name], horizontal=True, label_visibility="collapsed")
        side_filter = 'home' if team_tab == home_team_name else 'away'
        filtered_df = df_players[df_players['side'] == side_filter]
        
        for _, row in filtered_df.iterrows():
            pid = str(row['player_id'])
            pname = f"{int(row['shirt_number'])}. {row['commonname']}"
            
            # Draft check
            dkey = f"{selected_match_id}_{pid}_{current_scout_id}"
            has_draft = dkey in st.session_state.scout_drafts
            
            btn_type = "primary" if str(st.session_state.active_player_id) == pid and not st.session_state.manual_player_mode else "secondary"
            icon = "📝" if has_draft else "👤"
            
            if st.button(f"{icon} {pname}", key=f"btn_{pid}", type=btn_type, use_container_width=True):
                st.session_state.active_player_id = pid
                st.session_state.manual_player_mode = False # We kiezen een bestaande speler
                st.rerun()

    # 2. Knop voor Manuele Speler (Altijd zichtbaar, of de enige optie bij manuele match)
    st.markdown("---")
    
    # Als we in manuele match modus zitten, of als de gebruiker op "Manueel" klikt
    if is_manual_match or st.button("➕ Speler handmatig toevoegen", use_container_width=True):
         st.session_state.manual_player_mode = True
         st.session_state.active_player_id = None # Geen ID

    if st.session_state.manual_player_mode:
        st.info("Voer naam van de speler in:")
        manual_name_input = st.text_input("Naam Speler", value=st.session_state.manual_player_name, key="inp_manual_name_sidebar")
        
        # Sla op in state als er getypt wordt
        if manual_name_input:
            st.session_state.manual_player_name = manual_name_input

# --- EDITOR ---
with col_editor:
    # Bepaal Identifiers voor opslaan/laden
    active_pid = None
    active_pname = "Onbekend"
    active_match_key = selected_match_id if selected_match_id else custom_match_name
    
    # Scenario A: Bestaande Speler
    if st.session_state.active_player_id and not st.session_state.manual_player_mode:
        active_pid = str(st.session_state.active_player_id)
        p_row = df_players[df_players['player_id'] == active_pid].iloc[0]
        active_pname = p_row['commonname']
        
        draft_key = f"{active_match_key}_{active_pid}_{current_scout_id}"
        
        # Load Logic DB (ID based)
        where_clause = "scout_id = %s AND speler_id = %s AND wedstrijd_id = %s"
        params = (current_scout_id, active_pid, selected_match_id)
        
    # Scenario B: Manuele Speler (of Manuele Match)
    elif st.session_state.manual_player_mode and st.session_state.manual_player_name:
        active_pname = st.session_state.manual_player_name
        # Gebruik naam in de key
        draft_key = f"{active_match_key}_{active_pname}_{current_scout_id}"
        
        # Load Logic DB (Custom Name based)
        # Let op: we moeten hier flexibel zijn. 
        # Als match_id er is -> gebruik match_id + custom_speler
        # Als match_id er NIET is -> gebruik custom_wedstrijd + custom_speler
        
        if selected_match_id:
            where_clause = "scout_id = %s AND custom_speler_naam = %s AND wedstrijd_id = %s"
            params = (current_scout_id, active_pname, selected_match_id)
        else:
            where_clause = "scout_id = %s AND custom_speler_naam = %s AND custom_wedstrijd_naam = %s"
            params = (current_scout_id, active_pname, custom_match_name)
            
    else:
        if is_manual_match:
             st.info("👈 Voer hiernaast een spelernaam in.")
        else:
             st.info("👈 Selecteer een speler.")
        st.stop()

    st.subheader(f"Rapport: {active_pname}")

    # --- DATALOADER ---
    if draft_key not in st.session_state.scout_drafts:
        db_q = f"SELECT * FROM scouting.rapporten WHERE {where_clause}"
        existing = run_query(db_q, params=params)
        
        if not existing.empty:
            rec = existing.iloc[0]
            gval = bool(rec['gouden_buzzer']) if 'gouden_buzzer' in rec else False
            st.session_state.scout_drafts[draft_key] = {
                "positie": rec['positie_gespeeld'], "profiel": rec['profiel_code'], "advies": rec['advies'],
                "rating": int(rec['beoordeling']) if rec['beoordeling'] else 6,
                "tekst": rec['rapport_tekst'] or "", "gouden_buzzer": gval, "shortlist": rec['shortlist_id']
            }
        else:
            st.session_state.scout_drafts[draft_key] = {
                "positie": None, "profiel": None, "advies": None,
                "rating": 6, "tekst": "", "gouden_buzzer": False, "shortlist": None
            }
    
    draft = st.session_state.scout_drafts[draft_key]
    
    # --- FORMULIER ---
    unique_suffix = f"{draft_key}" # Maak keys uniek op basis van de draft combo

    c1, c2 = st.columns(2)
    def get_idx(val, opts): return opts.index(val) if val in opts else 0

    with c1:
        pos_opts = opties_posities['value'].tolist(); pos_lbls = opties_posities['label'].tolist()
        curr_pos = draft['positie']
        idx_pos = pos_opts.index(curr_pos) if curr_pos in pos_opts else 0
        new_pos = st.selectbox("Positie", pos_opts, index=idx_pos, format_func=lambda x: pos_lbls[pos_opts.index(x)] if x in pos_opts else x, key=f"pos_{unique_suffix}")
        
        new_rating = st.slider("Beoordeling (1-10)", 1, 10, draft["rating"], key=f"rate_{unique_suffix}")

    with c2:
        adv_opts = opties_advies['value'].tolist(); adv_lbls = opties_advies['label'].tolist()
        curr_adv = draft['advies']
        idx_adv = adv_opts.index(curr_adv) if curr_adv in adv_opts else 0
        new_adv = st.selectbox("Advies", adv_opts, index=idx_adv, format_func=lambda x: adv_lbls[adv_opts.index(x)] if x in adv_opts else x, key=f"adv_{unique_suffix}")

        prof_opts = opties_profielen['value'].tolist(); prof_lbls = opties_profielen['label'].tolist()
        curr_prof = draft['profiel']
        idx_prof = prof_opts.index(curr_prof) if curr_prof in prof_opts else 0
        new_prof = st.selectbox("Profiel", prof_opts, index=idx_prof, format_func=lambda x: prof_lbls[prof_opts.index(x)] if x in prof_opts else x, key=f"prof_{unique_suffix}")

    new_tekst = st.text_area("Rapportage", draft["tekst"], height=200, key=f"txt_{unique_suffix}")
    
    ce1, ce2 = st.columns(2)
    with ce1: 
        new_gouden = st.checkbox("🏆 Gouden Buzzer", draft["gouden_buzzer"], key=f"gold_{unique_suffix}")
    with ce2:
        sl_opts = [None] + opties_shortlists['value'].tolist()
        sl_lbls = ["Geen"] + opties_shortlists['label'].tolist()
        curr_sl = draft['shortlist']
        idx_sl = sl_opts.index(curr_sl) if curr_sl in sl_opts else 0
        def fmt_sl(x):
            try: return sl_lbls[sl_opts.index(x)]
            except: return "Geen"
        new_sl = st.selectbox("Shortlist", sl_opts, index=idx_sl, format_func=fmt_sl, key=f"sl_{unique_suffix}")

    st.session_state.scout_drafts[draft_key] = {
        "positie": new_pos, "profiel": new_prof, "advies": new_adv,
        "rating": new_rating, "tekst": new_tekst, "gouden_buzzer": new_gouden, "shortlist": new_sl
    }

    st.markdown("---")
    if st.button("💾 Rapport Opslaan", type="primary", use_container_width=True, key=f"save_{unique_suffix}"):
        save_data = {
            "scout_id": current_scout_id,
            "speler_id": active_pid, # Kan None zijn
            "wedstrijd_id": selected_match_id, # Kan None zijn
            "competitie_id": selected_comp_id, # Kan None zijn
            "custom_speler_naam": active_pname if not active_pid else None,
            "custom_wedstrijd_naam": custom_match_name if not selected_match_id else None,
            "positie_gespeeld": new_pos, "profiel_code": new_prof, "advies": new_adv,
            "beoordeling": new_rating, "rapport_tekst": new_tekst, 
            "gouden_buzzer": new_gouden, "shortlist_id": new_sl
        }
        if save_report_to_db(save_data):
            st.success("Opgeslagen!")
            st.balloons()
