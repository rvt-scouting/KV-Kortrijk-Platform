import streamlit as st
import pandas as pd
import json
import datetime
from utils import run_query, init_connection

st.set_page_config(page_title="Speler Scouting", page_icon="📝", layout="wide")

# -----------------------------------------------------------------------------
# 0. SESSION STATE INITIALISATIES
# -----------------------------------------------------------------------------
if "scout_drafts" not in st.session_state: st.session_state.scout_drafts = {}
if "active_player_id" not in st.session_state: st.session_state.active_player_id = None
if "manual_player_mode" not in st.session_state: st.session_state.manual_player_mode = False
if "manual_player_type" not in st.session_state: st.session_state.manual_player_type = "db_search"
if "manual_player_name_text" not in st.session_state: st.session_state.manual_player_name_text = ""
# NIEUW: Om 'gepinde' spelers te onthouden
if "watched_players" not in st.session_state: st.session_state.watched_players = set()

# Check login
if 'user_info' not in st.session_state or not st.session_state.user_info:
    st.warning("⚠️ Log in AUB."); st.stop()

current_scout_id = str(st.session_state.user_info.get('id', '0'))
current_scout_name = st.session_state.user_info.get('naam', 'Onbekend')

# -----------------------------------------------------------------------------
# 1. HULPFUNCTIES
# -----------------------------------------------------------------------------
@st.cache_data
def get_scouting_options_safe(table_name):
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
            df['value'] = df[col_name]; df['label'] = df[col_name]
            return df[['value', 'label']]
        candidates = ['naam', 'label', 'status', 'omschrijving', 'code']
        label_col = next((c for c in cols if c in candidates), cols[1])
        value_col = 'id' if 'id' in cols else cols[0]
        return df[[value_col, label_col]].rename(columns={value_col: 'value', label_col: 'label'})
    except Exception: return fallback_data

def search_player_in_db(search_term):
    if not search_term or len(search_term) < 2: return pd.DataFrame()
    try:
        q = "SELECT id, commonname, firstname, lastname FROM public.players WHERE commonname ILIKE %s OR lastname ILIKE %s LIMIT 20"
        term = f"%{search_term}%"
        return run_query(q, params=(term, term))
    except: return pd.DataFrame()

def save_report_to_db(data):
    conn = None
    try:
        conn = init_connection()
        cur = conn.cursor()
        
        scout_id = str(data['scout_id'])
        speler_id = str(data['speler_id']) if data['speler_id'] else None
        match_id = str(data['wedstrijd_id']) if data['wedstrijd_id'] else None
        comp_id = str(data['competitie_id']) if data['competitie_id'] else None
        
        custom_p = data.get('custom_speler_naam')
        custom_m = data.get('custom_wedstrijd_naam')

        where_clauses = ["scout_id = %s"]
        params = [scout_id]
        if speler_id:
            where_clauses.append("speler_id = %s"); params.append(speler_id)
        else:
            where_clauses.append("custom_speler_naam = %s"); params.append(custom_p)
            where_clauses.append("speler_id IS NULL")
        if match_id:
            where_clauses.append("wedstrijd_id = %s"); params.append(match_id)
        else:
            where_clauses.append("custom_wedstrijd_naam = %s"); params.append(custom_m)
            where_clauses.append("wedstrijd_id IS NULL")

        check_q = f"SELECT id FROM scouting.rapporten WHERE {' AND '.join(where_clauses)}"
        cur.execute(check_q, tuple(params))
        existing = cur.fetchone()
        
        if existing:
            update_q = """
                UPDATE scouting.rapporten SET
                    positie_gespeeld = %s, profiel_code = %s, advies = %s,
                    beoordeling = %s, rapport_tekst = %s, gouden_buzzer = %s,
                    shortlist_id = %s, speler_lengte = %s, contract_einde = %s, aangemaakt_op = NOW()
                WHERE id = %s
            """
            cur.execute(update_q, (
                data['positie_gespeeld'], data['profiel_code'], data['advies'], 
                data['beoordeling'], data['rapport_tekst'], data['gouden_buzzer'], 
                data['shortlist_id'], data['speler_lengte'], data['contract_einde'], existing[0]
            ))
        else:
            insert_q = """
                INSERT INTO scouting.rapporten 
                (scout_id, speler_id, wedstrijd_id, competitie_id, 
                 custom_speler_naam, custom_wedstrijd_naam,
                 positie_gespeeld, profiel_code, advies, beoordeling, 
                 rapport_tekst, gouden_buzzer, shortlist_id, 
                 speler_lengte, contract_einde, aangemaakt_op)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            """
            cur.execute(insert_q, (
                scout_id, speler_id, match_id, comp_id, custom_p, custom_m,
                data['positie_gespeeld'], data['profiel_code'], data['advies'], 
                data['beoordeling'], data['rapport_tekst'], data['gouden_buzzer'], 
                data['shortlist_id'], data['speler_lengte'], data['contract_einde']
            ))
            
        conn.commit()
        cur.close()
        return True
    except Exception as e:
        st.error(f"Save Error: {e}")
        return False
    finally:
        if conn: conn.close()

# -----------------------------------------------------------------------------
# 2. WEDSTRIJD SELECTIE
# -----------------------------------------------------------------------------
st.title("📝 Live Match Scouting")

selected_match_id = None; selected_comp_id = None; custom_match_name = None
home_team_name = "Thuis"; away_team_name = "Uit"
sel_season = None; sel_comp = None

opties_posities = get_scouting_options_safe('opties_posities')
opties_profielen = get_scouting_options_safe('opties_profielen')
opties_advies = get_scouting_options_safe('opties_advies')
opties_shortlists = get_scouting_options_safe('shortlists')

st.sidebar.header("Match Setup")
is_manual_match = st.sidebar.checkbox("🔓 Manuele Wedstrijd", help="Voor oefenmatchen of niet-DB wedstrijden.")

if is_manual_match:
    custom_match_name = st.sidebar.text_input("Naam Wedstrijd", placeholder="bv. KVK - Harelbeke")
    if not custom_match_name: st.info("👈 Voer een naam in."); st.stop()
    st.subheader(f"Wedstrijd: {custom_match_name}")
else:
    try:
        df_seasons = run_query("SELECT DISTINCT season FROM public.iterations ORDER BY season DESC")
        if not df_seasons.empty:
            seasons = df_seasons['season'].tolist()
            sel_season = st.sidebar.selectbox("1. Seizoen", seasons)
        else: st.error("Geen seizoenen."); st.stop()
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
        if df_matches.empty: st.info("Geen gespeelde wedstrijden."); st.stop()
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
df_players = pd.DataFrame()
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
            all_players_data = parse_squad_json(df_json.iloc[0]['squadHome'], 'home') + parse_squad_json(df_json.iloc[0]['squadAway'], 'away')
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
                    
                    # NIEUW: Voeg 'is_watched' kolom toe voor sortering
                    df_players['is_watched'] = df_players['player_id'].apply(lambda x: x in st.session_state.watched_players)
                    # Sorteren: Eerst watched (True), dan team side, dan rugnummer
                    df_players = df_players.sort_values(by=['is_watched', 'side', 'shirt_number'], ascending=[False, True, True])
    except: pass

# -----------------------------------------------------------------------------
# 4. UI: SPLIT VIEW
# -----------------------------------------------------------------------------
col_list, col_editor = st.columns([1, 2])

with col_list:
    st.subheader("Selecties")
    if not is_manual_match and not df_players.empty:
        team_tab = st.radio("Team", [home_team_name, away_team_name], horizontal=True, label_visibility="collapsed")
        side_filter = 'home' if team_tab == home_team_name else 'away'
        filtered_df = df_players[df_players['side'] == side_filter]
        
        # We herhalen de sortering hier voor de zekerheid binnen de gefilterde set
        filtered_df = filtered_df.sort_values(by=['is_watched', 'shirt_number'], ascending=[False, True])

        for _, row in filtered_df.iterrows():
            pid = str(row['player_id'])
            dkey = f"{selected_match_id}_{pid}_{current_scout_id}"
            btn_type = "primary" if str(st.session_state.active_player_id) == pid and not st.session_state.manual_player_mode else "secondary"
            icon = "📝" if dkey in st.session_state.scout_drafts else "👤"
            
            # --- NIEUWE LOGICA: CHECKBOX + BUTTON ---
            c_check, c_btn = st.columns([0.15, 0.85])
            
            with c_check:
                # De 'pin' checkbox
                is_w = st.checkbox("📌", value=row['is_watched'], key=f"watch_{pid}", label_visibility="collapsed")
                if is_w != row['is_watched']:
                    if is_w: st.session_state.watched_players.add(pid)
                    else: st.session_state.watched_players.discard(pid)
                    st.rerun() # Direct verversen om de speler bovenaan te zetten

            with c_btn:
                # De normale selectie knop
                if st.button(f"{icon} {int(row['shirt_number'])}. {row['commonname']}", key=f"btn_{pid}", type=btn_type, use_container_width=True):
                    st.session_state.active_player_id = pid
                    st.session_state.manual_player_mode = False
                    st.rerun()

    st.markdown("---")
    knop_label = "➕ Speler toevoegen / Zoeken" if not is_manual_match else "Selecteer Speler"
    if st.button(knop_label, use_container_width=True):
         st.session_state.manual_player_mode = True
         st.session_state.active_player_id = None

    if st.session_state.manual_player_mode:
        m_type = st.radio("Methode", ["🔍 Zoek in Database", "✍️ Nieuwe Naam (Tekst)"], key="inp_m_type")
        st.session_state.manual_player_type = "db_search" if "Database" in m_type else "manual_text"
        if st.session_state.manual_player_type == "db_search":
            search_txt = st.text_input("Zoek op naam:", placeholder="bv. De Bruyne")
            if search_txt:
                results = search_player_in_db(search_txt)
                if not results.empty:
                    for _, r in results.iterrows():
                        if st.button(f"👤 {r['commonname']}", key=f"srch_{r['id']}"):
                            st.session_state.active_player_id = str(r['id'])
                            st.session_state.manual_player_mode = False
                            st.rerun()
                else: st.warning("Geen spelers.")
        else:
            m_name = st.text_input("Naam Speler", value=st.session_state.manual_player_name_text, key="inp_m_text")
            if m_name: st.session_state.manual_player_name_text = m_name

# 

with col_editor:
    active_pid = None; active_pname = "Onbekend"
    active_match_key = selected_match_id if selected_match_id else custom_match_name
    
    if st.session_state.active_player_id and not (st.session_state.manual_player_mode and st.session_state.manual_player_type == "manual_text"):
        active_pid = str(st.session_state.active_player_id)
        if not df_players.empty and active_pid in df_players['player_id'].values:
             active_pname = df_players[df_players['player_id'] == active_pid].iloc[0]['commonname']
        else:
             res = run_query(f"SELECT commonname FROM public.players WHERE id = '{active_pid}'")
             if not res.empty: active_pname = res.iloc[0]['commonname']
        draft_key = f"{active_match_key}_{active_pid}_{current_scout_id}"
        if selected_match_id:
            where_clause = "scout_id = %s AND speler_id = %s AND wedstrijd_id = %s"
            params = (current_scout_id, active_pid, selected_match_id)
        else:
            where_clause = "scout_id = %s AND speler_id = %s AND custom_wedstrijd_naam = %s"
            params = (current_scout_id, active_pid, custom_match_name)
    elif st.session_state.manual_player_mode and st.session_state.manual_player_type == "manual_text" and st.session_state.manual_player_name_text:
        active_pname = st.session_state.manual_player_name_text
        draft_key = f"{active_match_key}_{active_pname}_{current_scout_id}"
        if selected_match_id:
            where_clause = "scout_id = %s AND custom_speler_naam = %s AND wedstrijd_id = %s"
            params = (current_scout_id, active_pname, selected_match_id)
        else:
            where_clause = "scout_id = %s AND custom_speler_naam = %s AND custom_wedstrijd_naam = %s"
            params = (current_scout_id, active_pname, custom_match_name)
    else:
        st.info("👈 Selecteer of zoek een speler."); st.stop()

    st.subheader(f"Rapport: {active_pname}")

    if draft_key not in st.session_state.scout_drafts:
        db_q = f"SELECT * FROM scouting.rapporten WHERE {where_clause}"
        existing = run_query(db_q, params=params)
        if not existing.empty:
            rec = existing.iloc[0]
            st.session_state.scout_drafts[draft_key] = {
                "positie": rec['positie_gespeeld'], "profiel": rec['profiel_code'], "advies": rec['advies'],
                "rating": int(rec['beoordeling']) if rec['beoordeling'] else 6,
                "tekst": rec['rapport_tekst'] or "", "gouden_buzzer": bool(rec['gouden_buzzer']), "shortlist": rec['shortlist_id'],
                "lengte": rec['speler_lengte'] if 'speler_lengte' in rec else 0,
                "contract": rec['contract_einde'] if 'contract_einde' in rec else None
            }
        else:
            st.session_state.scout_drafts[draft_key] = {
                "positie": None, "profiel": None, "advies": None, "rating": 6, "tekst": "", 
                "gouden_buzzer": False, "shortlist": None, "lengte": 0, "contract": None
            }
    
    draft = st.session_state.scout_drafts[draft_key]
    unique_suffix = f"{draft_key}"

    c1, c2 = st.columns(2)
    with c1:
        pos_opts = opties_posities['value'].tolist(); pos_lbls = opties_posities['label'].tolist()
        idx_pos = pos_opts.index(draft['positie']) if draft['positie'] in pos_opts else 0
        new_pos = st.selectbox("Positie", pos_opts, index=idx_pos, format_func=lambda x: pos_lbls[pos_opts.index(x)], key=f"pos_{unique_suffix}")
        new_lengte = st.number_input("Lengte (cm)", min_value=0, max_value=230, value=int(draft["lengte"] or 0), key=f"len_{unique_suffix}")
        new_rating = st.slider("Beoordeling", 1, 10, draft["rating"], key=f"rate_{unique_suffix}")

    with c2:
        adv_opts = opties_advies['value'].tolist(); adv_lbls = opties_advies['label'].tolist()
        idx_adv = adv_opts.index(draft['advies']) if draft['advies'] in adv_opts else 0
        new_adv = st.selectbox("Advies", adv_opts, index=idx_adv, format_func=lambda x: adv_lbls[adv_opts.index(x)], key=f"adv_{unique_suffix}")
        val_contract = draft["contract"]
        if isinstance(val_contract, str): val_contract = datetime.datetime.strptime(val_contract, '%Y-%m-%d').date()
        new_contract = st.date_input("Contract Einde", value=val_contract, key=f"con_{unique_suffix}")
        prof_opts = opties_profielen['value'].tolist(); prof_lbls = opties_profielen['label'].tolist()
        idx_prof = prof_opts.index(draft['profiel']) if draft['profiel'] in prof_opts else 0
        new_prof = st.selectbox("Profiel", prof_opts, index=idx_prof, format_func=lambda x: prof_lbls[prof_opts.index(x)], key=f"prof_{unique_suffix}")

    new_tekst = st.text_area("Rapportage", draft["tekst"], height=200, key=f"txt_{unique_suffix}")
    
    ce1, ce2 = st.columns(2)
    with ce1: new_gouden = st.checkbox("🏆 Gouden Buzzer", draft["gouden_buzzer"], key=f"gold_{unique_suffix}")
    with ce2:
        sl_opts = [None] + opties_shortlists['value'].tolist()
        sl_lbls = ["Geen"] + opties_shortlists['label'].tolist()
        idx_sl = sl_opts.index(draft['shortlist']) if draft['shortlist'] in sl_opts else 0
        new_sl = st.selectbox("Shortlist", sl_opts, index=idx_sl, format_func=lambda x: sl_lbls[sl_opts.index(x)] if x in sl_opts else "Geen", key=f"sl_{unique_suffix}")

    st.session_state.scout_drafts[draft_key] = {
        "positie": new_pos, "profiel": new_prof, "advies": new_adv,
        "rating": new_rating, "tekst": new_tekst, "gouden_buzzer": new_gouden, "shortlist": new_sl,
        "lengte": new_lengte, "contract": new_contract
    }

    st.markdown("---")
    if st.button("💾 Rapport Opslaan", type="primary", use_container_width=True, key=f"save_{unique_suffix}"):
        save_data = {
            "scout_id": current_scout_id, "speler_id": active_pid, "wedstrijd_id": selected_match_id, 
            "competitie_id": selected_comp_id, "custom_speler_naam": active_pname if not active_pid else None,
            "custom_wedstrijd_naam": custom_match_name if not selected_match_id else None,
            "positie_gespeeld": new_pos, "profiel_code": new_prof, "advies": new_adv,
            "beoordeling": new_rating, "rapport_tekst": new_tekst, 
            "gouden_buzzer": new_gouden, "shortlist_id": new_sl,
            "speler_lengte": new_lengte, "contract_einde": new_contract
        }
        if save_report_to_db(save_data):
            st.success("Opgeslagen!")
            st.balloons()
