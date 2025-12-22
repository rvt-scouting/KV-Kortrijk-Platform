import streamlit as st
import pandas as pd
import json
import datetime
from utils import run_query, init_connection

st.set_page_config(page_title="Live Speler Scouting", page_icon="📝", layout="wide")

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
# 1. HULPFUNCTIES (Met extra beveiliging tegen crashes)
# -----------------------------------------------------------------------------
@st.cache_data
def get_scouting_options_safe(table_name):
    fallback_df = pd.DataFrame(columns=['value', 'label'])
    try:
        df = run_query(f"SELECT * FROM scouting.{table_name}")
        if df is None or df.empty: return fallback_df
        cols = df.columns.tolist()
        val_col = 'id' if 'id' in cols else cols[0]
        lab_candidates = ['naam', 'label', 'omschrijving', 'waarde']
        lab_col = next((c for c in cols if c in lab_candidates), cols[1] if len(cols) > 1 else cols[0])
        final_df = df[[val_col, lab_col]].copy()
        final_df.columns = ['value', 'label']
        return final_df
    except: return fallback_df

def search_player_in_db(search_term):
    """Zoekt speler en toont de club voor context."""
    if not search_term or len(search_term) < 2: return pd.DataFrame()
    q = """
        SELECT p.id, p.commonname, s.name as team_naam
        FROM public.players p
        LEFT JOIN public.squads s ON p."currentSquadId" = s.id
        WHERE p.commonname ILIKE %s OR p.lastname ILIKE %s 
        LIMIT 25
    """
    term = f"%{search_term}%"
    return run_query(q, params=(term, term))

def save_report_to_db(data):
    conn = None
    try:
        conn = init_connection(); cur = conn.cursor()
        check_q = """
            SELECT id FROM scouting.rapporten 
            WHERE scout_id = %s 
            AND (speler_id = %s OR (speler_id IS NULL AND custom_speler_naam = %s))
            AND (wedstrijd_id = %s OR (wedstrijd_id IS NULL AND custom_wedstrijd_naam = %s))
        """
        cur.execute(check_q, (data['scout_id'], data['speler_id'], data['custom_speler_naam'], data['wedstrijd_id'], data['custom_wedstrijd_naam']))
        existing = cur.fetchone()

        if existing:
            query = """
                UPDATE scouting.rapporten SET
                    positie_gespeeld = %s, profiel_code = %s, advies = %s, beoordeling = %s,
                    rapport_tekst = %s, gouden_buzzer = %s, shortlist_id = %s,
                    speler_lengte = %s, contract_einde = %s, aangemaakt_op = NOW()
                WHERE id = %s
            """
            cur.execute(query, (data['positie_gespeeld'], data['profiel_code'], data['advies'], data['beoordeling'],
                               data['rapport_tekst'], data['gouden_buzzer'], data['shortlist_id'],
                               data['speler_lengte'], data['contract_einde'], existing[0]))
        else:
            query = """
                INSERT INTO scouting.rapporten (scout_id, speler_id, wedstrijd_id, competitie_id, custom_speler_naam, 
                custom_wedstrijd_naam, positie_gespeeld, profiel_code, advies, beoordeling, rapport_tekst, 
                gouden_buzzer, shortlist_id, speler_lengte, contract_einde, aangemaakt_op)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            """
            cur.execute(query, (data['scout_id'], data['speler_id'], data['wedstrijd_id'], data['competitie_id'], 
                               data['custom_speler_naam'], data['custom_wedstrijd_naam'], data['positie_gespeeld'], 
                               data['profiel_code'], data['advies'], data['beoordeling'], data['rapport_tekst'], 
                               data['gouden_buzzer'], data['shortlist_id'], data['speler_lengte'], data['contract_einde']))
        conn.commit(); cur.close(); return True
    except Exception as e:
        st.error(f"Save Error: {e}"); return False
    finally:
        if conn: conn.close()

def sync_text_to_draft():
    """Zorgt dat de getypte tekst direct in de draft-sessie wordt opgeslagen."""
    # We halen de huidige sleutel (match_player_scout) op
    d_key = st.session_state.get('active_d_key')
    if d_key:
        # We pakken de tekst uit het tekstvak en zetten die in de draft
        st.session_state.scout_drafts[d_key]["txt"] = st.session_state[f"tx_{d_key}"]

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
# 3. SPELERS OPHALEN (Gecorrigeerd voor match_details_full)
# -----------------------------------------------------------------------------
df_players = pd.DataFrame()
players_list = []

if selected_match_id:
    # We gebruiken dubbele aanhalingstekens voor de hoofdlettergevoelige kolommen in Postgres
    query = 'SELECT "id", "squadHome", "squadAway" FROM public.match_details_full WHERE "id" = %s'
    df_json = run_query(query, params=(selected_match_id,))
    
    if df_json is not None and not df_json.empty:
        # In Postgres/Psycopg2 wordt jsonb vaak direct als dict teruggegeven
        for side in ['Home', 'Away']:
            col_name = f'squad{side}'
            raw_data = df_json.iloc[0][col_name]
            
            # Controleer of de data een string is (moet geload worden) of al een dict
            if isinstance(raw_data, str):
                try:
                    data = json.loads(raw_data)
                except Exception as e:
                    st.error(f"Fout bij parsen JSON voor {side}: {e}")
                    data = {}
            else:
                data = raw_data

            # Impect JSON structuur check: de spelers zitten meestal in een lijst 'players'
            if data and isinstance(data, dict) and 'players' in data:
                for p in data['players']:
                    players_list.append({
                        'player_id': str(p.get('id')), 
                        'shirt_number': p.get('shirtNumber', p.get('shirt_number', 0)), 
                        'side': side.lower(), 
                        'source': 'official',
                        'commonname': p.get('name', p.get('commonname', None)) # Probeer naam alvast uit JSON te halen
                    })
    else:
        st.warning(f"Geen match details gevonden in `public.match_details_full` voor ID: {selected_match_id}")

# B. Voeg spelers uit de scouting.rapporten toe (de 'extra' spelers)
q_rep = """
    SELECT r.speler_id, r.custom_speler_naam, p.commonname 
    FROM scouting.rapporten r 
    LEFT JOIN public.players p ON r.speler_id = p.id 
    WHERE (r.wedstrijd_id = %s OR r.custom_wedstrijd_naam = %s)
"""
df_rep = run_query(q_rep, params=(selected_match_id, custom_match_name))

if df_rep is not None and not df_rep.empty:
    for _, r in df_rep.iterrows():
        pid = str(r['speler_id']) if r['speler_id'] else None
        pname = r['commonname'] if r['commonname'] else r['custom_speler_naam']
        
        # Voorkom dubbele entries als een speler zowel officieel als in rapporten staat
        exists = any(p['player_id'] == pid for p in players_list if pid)
        if not exists:
            players_list.append({
                'player_id': pid, 
                'shirt_number': 0, 
                'side': 'extra', 
                'source': 'reported', 
                'commonname': pname
            })

# C. Namen aanvullen vanuit public.players als ze nog ontbreken
if players_list:
    df_players = pd.DataFrame(players_list)
    
    # Zoek IDs waar we nog geen naam voor hebben
    missing_mask = df_players['commonname'].isna() & df_players['player_id'].notna()
    ids_to_fetch = df_players.loc[missing_mask, 'player_id'].unique().tolist()
    
    if ids_to_fetch:
        # Veilig omzetten naar tuple voor SQL
        q_n = "SELECT id, commonname FROM public.players WHERE id IN %s"
        df_n = run_query(q_n, params=(tuple(ids_to_fetch),))
        
        if df_n is not None and not df_n.empty:
            df_n['id'] = df_n['id'].astype(str)
            name_dict = dict(zip(df_n['id'], df_n['commonname']))
            df_players['commonname'] = df_players.apply(
                lambda x: name_dict.get(x['player_id'], x['commonname']) if pd.isna(x['commonname']) else x['commonname'],
                axis=1
            )
    
    df_players['commonname'] = df_players['commonname'].fillna("Onbekende Speler")
    
    # Pinning logica
    df_players['is_watched'] = df_players.apply(
        lambda r: (str(r['player_id']) if r['player_id'] else r['commonname']) in st.session_state.watched_players, 
        axis=1
    )
    df_players = df_players.sort_values(by=['is_watched', 'side', 'shirt_number'], ascending=[False, True, True])

# -----------------------------------------------------------------------------
# 4. UI: SPELERSLIJST (LINKS)
# -----------------------------------------------------------------------------
col_list, col_editor = st.columns([1, 2])

with col_list:
    st.subheader("Selecties")
    sel_tab = st.radio("Team", [home_team_name, away_team_name, "Extra"], horizontal=True, label_visibility="collapsed")
    side_f = 'home' if sel_tab == home_team_name else ('away' if sel_tab == away_team_name else 'extra')
    
    if not df_players.empty:
        filtered = df_players[df_players['side'] == side_f]
        for _, row in filtered.iterrows():
            p_id = row['player_id']
            p_name = row['commonname']
            p_key = p_id if p_id else p_name
            d_key = f"{selected_match_id if selected_match_id else custom_match_name}_{p_key}_{current_scout_id}"
            
            c_pin, c_btn = st.columns([0.15, 0.85])
            with c_pin:
                is_p = st.checkbox("📌", value=row['is_watched'], key=f"p_{p_key}", label_visibility="collapsed")
                if is_p != row['is_watched']:
                    st.session_state.watched_players.add(p_key) if is_p else st.session_state.watched_players.discard(p_key)
                    st.rerun()
            with c_btn:
                style = "primary" if st.session_state.active_player_id == p_id and p_id else "secondary"
                icon = "📝" if d_key in st.session_state.scout_drafts else ("📥" if row['source'] == 'reported' else "👤")
                if st.button(f"{icon} {p_name}", key=f"b_{p_key}", type=style, use_container_width=True):
                    st.session_state.active_player_id, st.session_state.manual_player_mode = p_id, (p_id is None)
                    if not p_id: st.session_state.manual_player_name_text = p_name
                    st.rerun()
    
    st.divider()
    if st.button("➕ Zoeken / Manueel Toevoegen", use_container_width=True):
        st.session_state.manual_player_mode = True; st.session_state.active_player_id = None

    if st.session_state.manual_player_mode:
        m_t = st.radio("Methode", ["🔍 Zoek Database", "✍️ Vrije Tekst"], horizontal=True)
        if "Database" in m_t:
            s_t = st.text_input("Naam (bv. Otavio):")
            if s_t:
                res = search_player_in_db(s_t)
                for _, r in res.iterrows():
                    club_txt = f" ({r['team_naam']})" if r['team_naam'] else ""
                    if st.button(f"👤 {r['commonname']}{club_txt}", key=f"s_{r['id']}", use_container_width=True):
                        st.session_state.active_player_id = str(r['id']); st.session_state.manual_player_mode = False; st.rerun()
        else:
            st.session_state.manual_player_name_text = st.text_input("Naam Speler:")

# -----------------------------------------------------------------------------
# 5. EDITOR (RECHTS)
# -----------------------------------------------------------------------------
with col_editor:
    a_pid = st.session_state.active_player_id
    a_pname = st.session_state.manual_player_name_text if not a_pid else "Laden..."
    if a_pid:
        res_n = run_query("SELECT commonname FROM public.players WHERE id = %s", params=(a_pid,))
        if not res_n.empty: a_pname = res_n.iloc[0]['commonname']
    
    if not a_pname or a_pname == "Laden...":
        st.info("👈 Selecteer een speler om een rapport te maken."); st.stop()

    st.subheader(f"Rapport: {a_pname}")
    match_key = selected_match_id if selected_match_id else custom_match_name
    p_key = a_pid if a_pid else a_pname
    d_key = f"{match_key}_{p_key}_{current_scout_id}"
    st.session_state.active_d_key = d_key # Nodig voor de sync_text functie

    # CHECK: Hebben we dit rapport al in ons tijdelijk geheugen OF in de database?
    if d_key not in st.session_state.scout_drafts:
        # Zoek in de database of er al een bestaand rapport is 
        q_ex = """
            SELECT * FROM scouting.rapporten 
            WHERE scout_id=%s AND (speler_id=%s OR custom_speler_naam=%s) 
            AND (wedstrijd_id=%s OR custom_wedstrijd_naam=%s)
        """
        db_r = run_query(q_ex, (current_scout_id, a_pid, a_pname, selected_match_id, custom_match_name))
        
        if db_r is not None and not db_r.empty:
            # ER IS DATA: Laad deze in de sessie 
            rec = db_r.iloc[0]
            st.session_state.scout_drafts[d_key] = {
                "pos": rec.get('positie_gespeeld'), 
                "rate": int(rec.get('beoordeling', 6)), 
                "adv": rec.get('advies'), 
                "txt": rec.get('rapport_tekst', ""),
                "gold": bool(rec.get('gouden_buzzer', False)), 
                "sl": rec.get('shortlist_id'), 
                "len": int(rec.get('speler_lengte', 0) or 0), 
                "con": rec.get('contract_einde'),
                "prof": rec.get('profiel_code')
            }
        else:
            # GEEN DATA: Maak een nieuw leeg rapport 
            st.session_state.scout_drafts[d_key] = {
                "pos": None, "rate": 6, "adv": None, "txt": "", 
                "gold": False, "sl": None, "len": 0, 
                "con": datetime.date.today(), "prof": None
            }

    draft = st.session_state.scout_drafts[d_key]
    c1, c2 = st.columns(2)
    with c1:
        p_opts = opties_posities['value'].tolist() if not opties_posities.empty else ["Doelman", "Verdediger", "Middenvelder", "Aanvaller"]
        p_lbls = opties_posities['label'].tolist() if not opties_posities.empty else p_opts
        p_idx = p_opts.index(draft.get('pos')) if draft.get('pos') in p_opts else 0
        new_pos = st.selectbox("Positie", p_opts, index=p_idx, format_func=lambda x: p_lbls[p_opts.index(x)], key=f"pos_{d_key}")
        new_len = st.number_input("Lengte (cm)", 0, 230, int(draft.get('len', 0)), key=f"len_{d_key}")
        new_rate = st.slider("Beoordeling", 1, 10, int(draft.get('rate', 6)), key=f"rt_{d_key}")

    with c2:
        # --- DYNAMISCH PROFIEL (Gekoppeld aan scouting.opties_profielen) ---
        pr_opts = opties_profielen['value'].tolist() if not opties_profielen.empty else ["P1"]
        pr_idx = pr_opts.index(draft.get('prof')) if draft.get('prof') in pr_opts else 0
        new_prof = st.selectbox("Profiel Code", pr_opts, index=pr_idx, key=f"prof_{d_key}")

        a_opts = opties_advies['value'].tolist() if not opties_advies.empty else ["Sign", "Follow", "No"]
        a_lbls = opties_advies['label'].tolist() if not opties_advies.empty else a_opts
        a_idx = a_opts.index(draft.get('adv')) if draft.get('adv') in a_opts else 0
        new_adv = st.selectbox("Advies", a_opts, index=a_idx, format_func=lambda x: a_lbls[a_opts.index(x)], key=f"adv_{d_key}")
        
        new_con = st.date_input("Contract Einde", value=draft.get('con') if draft.get('con') else datetime.date.today(), key=f"cn_{d_key}")
        s_opts = [None] + (opties_shortlists['value'].tolist() if not opties_shortlists.empty else [])
        s_lbls = ["Geen"] + (opties_shortlists['label'].tolist() if not opties_shortlists.empty else [])
        s_idx = s_opts.index(draft.get('sl')) if draft.get('sl') in s_opts else 0
        new_sl = st.selectbox("Shortlist", s_opts, index=s_idx, format_func=lambda x: s_lbls[s_opts.index(x)], key=f"sl_{d_key}")

    new_txt = st.text_area("Analyse", draft.get('txt', ""), height=250, key=f"tx_{d_key}")
    new_gold = st.checkbox("🏆 Gouden Buzzer", draft.get('gold', False), key=f"gd_{d_key}")

    if st.button("💾 Rapport Opslaan", type="primary", use_container_width=True):
        s_d = {
            "scout_id": current_scout_id, "speler_id": a_pid, "wedstrijd_id": selected_match_id, "competitie_id": selected_comp_id,
            "custom_speler_naam": a_pname if not a_pid else None, "custom_wedstrijd_naam": custom_match_name if not selected_match_id else None,
            "positie_gespeeld": new_pos, 
            "profiel_code": new_prof, # Gebruikt nu de geselecteerde waarde uit de database
            "advies": new_adv, "beoordeling": new_rate, "rapport_tekst": new_txt,
            "gouden_buzzer": new_gold, "shortlist_id": new_sl, "speler_lengte": new_len, "contract_einde": new_con
        }
        if save_report_to_db(s_d):
            st.session_state.scout_drafts[d_key] = {
                "pos": new_pos, "rate": new_rate, "adv": new_adv, "txt": new_txt, 
                "gold": new_gold, "sl": new_sl, "len": new_len, "con": new_con, "prof": new_prof
            }
            st.success(f"Rapport voor {a_pname} opgeslagen!"); st.balloons()
