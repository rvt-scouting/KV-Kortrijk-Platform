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
if "watched_players" not in st.session_state: st.session_state.watched_players = set()

# Check login
if 'user_info' not in st.session_state or not st.session_state.user_info:
    st.warning("⚠️ Log in AUB."); st.stop()

current_scout_id = str(st.session_state.user_info.get('id', '0'))
current_scout_name = st.session_state.user_info.get('naam', 'Onbekend')

# -----------------------------------------------------------------------------
# 1. HULPFUNCTIES (Gelijk gebleven aan jouw versie)
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
        label_col = next((c for c in cols if c in ['naam', 'label', 'status']), cols[1] if len(cols)>1 else cols[0])
        value_col = 'id' if 'id' in cols else cols[0]
        return df[[value_col, label_col]].rename(columns={value_col: 'value', label_col: 'label'})
    except: return fallback_data

def search_player_in_db(search_term):
    if not search_term or len(search_term) < 2: return pd.DataFrame()
    term = f"%{search_term}%"
    return run_query("SELECT id, commonname FROM public.players WHERE commonname ILIKE %s LIMIT 20", params=(term,))

def save_report_to_db(data):
    conn = None
    try:
        conn = init_connection(); cur = conn.cursor()
        # Identieke logica aan jouw save_report_to_db...
        # [Hier komt jouw bestaande INSERT/UPDATE logica]
        # ... (voor de beknoptheid weggelaten, maar behoud jouw versie)
        conn.commit(); cur.close(); return True
    except Exception as e:
        st.error(f"Save Error: {e}"); return False
    finally:
        if conn: conn.close()

# -----------------------------------------------------------------------------
# 2. WEDSTRIJD SELECTIE
# -----------------------------------------------------------------------------
st.title("📝 Live Match Scouting")
selected_match_id = None; selected_comp_id = None; custom_match_name = None
home_team_name = "Thuis"; away_team_name = "Uit"

st.sidebar.header("Match Setup")
is_manual_match = st.sidebar.checkbox("🔓 Manuele Wedstrijd")

if is_manual_match:
    custom_match_name = st.sidebar.text_input("Naam Wedstrijd", placeholder="bv. KVK - Harelbeke")
    if not custom_match_name: st.stop()
else:
    # ... (Jouw Seizoen/Competitie selectie logica)
    # Stel dat we hier selected_match_id, home_team_name en away_team_name uithalen
    # [Hetzelfde als jouw code]
    try:
        df_seasons = run_query("SELECT DISTINCT season FROM public.iterations ORDER BY season DESC")
        sel_season = st.sidebar.selectbox("Seizoen", df_seasons['season'].tolist())
        df_comps = run_query('SELECT DISTINCT "competitionName" FROM public.iterations WHERE season = %s', params=(sel_season,))
        sel_comp = st.sidebar.selectbox("Competitie", df_comps['competitionName'].tolist())
        match_query = """
            SELECT m.id, m."scheduledDate", h.name as home, a.name as away, m."iterationId"
            FROM public.matches m 
            JOIN public.squads h ON m."homeSquadId" = h.id 
            JOIN public.squads a ON m."awaySquadId" = a.id
            WHERE m."iterationId" IN (SELECT id FROM public.iterations WHERE season = %s AND "competitionName" = %s)
            ORDER BY m."scheduledDate" DESC
        """
        df_matches = run_query(match_query, params=(sel_season, sel_comp))
        if not df_matches.empty:
            match_opts = {f"{r['home']} - {r['away']}": r for _, r in df_matches.iterrows()}
            sel_m = st.sidebar.selectbox("Wedstrijd", list(match_opts.keys()))
            selected_match_id = str(match_opts[sel_m]['id'])
            selected_comp_id = str(match_opts[sel_m]['iterationId'])
            home_team_name = match_opts[sel_m]['home']
            away_team_name = match_opts[sel_m]['away']
    except: st.stop()

# -----------------------------------------------------------------------------
# 3. SPELERS OPHALEN (MET GEHEUGEN-LOGICA)
# -----------------------------------------------------------------------------
df_players = pd.DataFrame(columns=['player_id', 'commonname', 'shirt_number', 'side', 'is_watched', 'source'])

if selected_match_id or custom_match_name:
    all_found_players = []

    # BRON A: Officiële Database (JSON)
    if selected_match_id:
        df_json = run_query('SELECT "squadHome", "squadAway" FROM public.match_details_full WHERE "id" = %s', params=(selected_match_id,))
        if not df_json.empty:
            def parse_squad(js, side):
                res = []
                try:
                    d = js if isinstance(js, dict) else json.loads(js)
                    for p in d.get('players', []):
                        res.append({'player_id': str(p['id']), 'shirt_number': p.get('shirtNumber', 99), 'side': side, 'source': 'official'})
                except: pass
                return res
            all_found_players += parse_squad(df_json.iloc[0]['squadHome'], 'home')
            all_found_players += parse_squad(df_json.iloc[0]['squadAway'], 'away')

    # BRON B: Bestaande rapporten voor deze match (Handmatig toegevoegde spelers)
    # We kijken zowel naar spelers mét ID als spelers met enkel een NAAM
    q_reports = """
        SELECT DISTINCT 
            r.speler_id, 
            r.custom_speler_naam,
            p.commonname as db_name
        FROM scouting.rapporten r
        LEFT JOIN public.players p ON r.speler_id = p.id
        WHERE (r.wedstrijd_id = %s OR r.custom_wedstrijd_naam = %s)
    """
    df_existing_reports = run_query(q_reports, params=(selected_match_id, custom_match_name))
    
    for _, rep in df_existing_reports.iterrows():
        pid = str(rep['speler_id']) if rep['speler_id'] else None
        pname = rep['db_name'] if rep['db_name'] else rep['custom_speler_naam']
        
        # Voeg alleen toe als de speler nog niet in de lijst staat (uniek op ID of Naam)
        exists = any(p['player_id'] == pid for p in all_found_players if pid) or \
                 any(p['commonname'] == pname for p in all_found_players if not pid)
        
        if not exists:
            all_found_players.append({
                'player_id': pid,
                'commonname': pname,
                'shirt_number': 0, # Geven we 0 zodat ze herkenbaar zijn als extra
                'side': 'extra',   # We labelen ze als 'extra' (of kies home/away)
                'source': 'reported'
            })

    if all_found_players:
        df_players = pd.DataFrame(all_players_data) if 'all_players_data' in locals() else pd.DataFrame(all_found_players)
        
        # Namen ophalen voor de officiële IDs die we nog niet hebben
        missing_names_ids = tuple(df_players[df_players['commonname'].isna()]['player_id'].unique())
        if missing_names_ids:
            # [Query om namen op te halen voor IDs]
            pass 

        # Sorteren & Opschonen
        df_players['is_watched'] = df_players['player_id'].apply(lambda x: x in st.session_state.watched_players if x else False)
        # Sorteer op gepind eerst, dan op bron (official eerst), dan op nummer
        df_players = df_players.sort_values(by=['is_watched', 'source', 'shirt_number'], ascending=[False, True, True])

# -----------------------------------------------------------------------------
# 4. UI: SPLIT VIEW
# -----------------------------------------------------------------------------
col_list, col_editor = st.columns([1, 2])



with col_list:
    st.subheader("Selecties")
    if not df_players.empty:
        # Filter op tabbladen: Thuis, Uit, en de "Extra" spelers uit rapporten
        tabs = [home_team_name, away_team_name, "Extra/Handmatig"]
        team_tab = st.radio("Team", tabs, horizontal=True, label_visibility="collapsed")
        
        if team_tab == home_team_name: side_filter = 'home'
        elif team_tab == away_team_name: side_filter = 'away'
        else: side_filter = 'extra'
        
        filtered_df = df_players[df_players['side'] == side_filter]
        
        if filtered_df.empty:
            st.info("Geen spelers in deze categorie.")
        
        for _, row in filtered_df.iterrows():
            pid = str(row['player_id']) if row['player_id'] else None
            pname = row['commonname']
            
            # Unieke key maken (gebruik naam als ID er niet is)
            player_key = pid if pid else pname
            dkey = f"{selected_match_id if selected_match_id else custom_match_name}_{player_key}_{current_scout_id}"
            
            btn_type = "primary" if (st.session_state.active_player_id == pid and pid) else "secondary"
            icon = "📝" if dkey in st.session_state.scout_drafts else "👤"
            if row['source'] == 'reported': icon = "📥" # Ander icoontje voor spelers uit eerdere rapporten

            c_check, c_btn = st.columns([0.15, 0.85])
            with c_check:
                is_w = st.checkbox("📌", value=row['is_watched'], key=f"w_{player_key}", label_visibility="collapsed")
                if is_w != row['is_watched']:
                    if is_w: st.session_state.watched_players.add(player_key)
                    else: st.session_state.watched_players.discard(player_key)
                    st.rerun()

            with c_btn:
                if st.button(f"{icon} {pname}", key=f"btn_{player_key}", type=btn_type, use_container_width=True):
                    st.session_state.active_player_id = pid
                    st.session_state.manual_player_mode = (pid is None)
                    if not pid: st.session_state.manual_player_name_text = pname
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
