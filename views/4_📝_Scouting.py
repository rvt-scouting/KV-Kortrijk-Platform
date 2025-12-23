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
            
def update_match_url():
    """Update de URL direct wanneer de scout een andere wedstrijd kiest."""
    if "match_selector" in st.session_state:
        sel_label = st.session_state.match_selector
        if "match_options_lookup" in st.session_state:
            # We gebruiken 'is not None' om de Pandas ValueError te voorkomen
            match_row = st.session_state.match_options_lookup.get(sel_label)
            if match_row is not None: 
                st.query_params["match_id"] = str(match_row['id'])
        
def sync_text_to_draft():
    """Slaat de getypte tekst direct op in de sessie-draft."""
    d_key = st.session_state.get('active_d_key')
    if d_key:
        st.session_state.scout_drafts[d_key]["txt"] = st.session_state[f"tx_{d_key}"]
        # We slaan ook het tijdstip van de laatste wijziging op
        st.session_state[f"last_sync_{d_key}"] = datetime.datetime.now().strftime("%H:%M:%S")


# -----------------------------------------------------------------------------
# 2. WEDSTRIJD SELECTIE
# -----------------------------------------------------------------------------
st.title("📝 Live Match Scouting")

# --- CRUCIAAL: Haal de opties ALTIJD op aan het begin ---
# Deze stonden waarschijnlijk in de vorige versie die je gewist hebt
opties_posities = get_scouting_options_safe('opties_posities')
opties_profielen = get_scouting_options_safe('opties_profielen')
opties_advies = get_scouting_options_safe('opties_advies')
opties_shortlists = get_scouting_options_safe('shortlists')

# Initialisatie basis variabelen (hou deze ook hier)
selected_match_id = None
selected_comp_id = None
custom_match_name = None
home_team_name = "Thuis"
away_team_name = "Uit"


st.sidebar.header("Match Setup")
is_manual_match = st.sidebar.checkbox("🔓 Manuele Wedstrijd", help="Voor oefenmatchen.")

if is_manual_match:
    custom_match_name = st.sidebar.text_input("Naam Wedstrijd", placeholder="bv. KVK - Harelbeke")
    if not custom_match_name: 
        st.info("👈 Voer een naam in."); st.stop()
    st.query_params.clear()
else:
    # 1. URL RECOVERY (Alleen bij eerste keer laden van de sessie)
    url_match_id = st.query_params.get("match_id")
    
    if url_match_id and not st.session_state.get('url_processed'):
        q_url = """
            SELECT m.id, i.season, i."competitionName"
            FROM public.matches m
            JOIN public.iterations i ON m."iterationId" = i.id
            WHERE m.id = %s
        """
        res_url = run_query(q_url, (url_match_id,))
        if res_url is not None and not res_url.empty:
            st.session_state.pre_season = res_url.iloc[0]['season']
            st.session_state.pre_comp = res_url.iloc[0]['competitionName']
            st.session_state.url_processed = True

    # --- DROPDOWNS ---
    # Seizoen selectie
    df_seasons = run_query("SELECT DISTINCT season FROM public.iterations ORDER BY season DESC")
    seasons = df_seasons['season'].tolist() if (df_seasons is not None and not df_seasons.empty) else []
    pre_s = st.session_state.get('pre_season')
    s_idx = seasons.index(pre_s) if pre_s in seasons else 0
    sel_season = st.sidebar.selectbox("1. Seizoen", seasons, index=s_idx)

    # Competitie selectie
    sel_comp = None
    if sel_season:
        df_comps = run_query('SELECT DISTINCT "competitionName" FROM public.iterations WHERE season = %s ORDER BY "competitionName"', params=(sel_season,))
        comps = df_comps['competitionName'].tolist() if (df_comps is not None and not df_comps.empty) else []
        pre_c = st.session_state.get('pre_comp')
        c_idx = comps.index(pre_c) if pre_c in comps else 0
        sel_comp = st.sidebar.selectbox("2. Competitie", comps, index=c_idx)

    # Wedstrijd selectie
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
        
        if df_matches is not None and not df_matches.empty:
            # We bouwen de dictionary voor de lookup
            match_opts = {
                f"{r['home']} vs {r['away']} ({r['scheduledDate'].strftime('%d-%m')})": r 
                for _, r in df_matches.iterrows()
            }
            # Sla de opties op voor de callback functie bovenaan
            st.session_state.match_options_lookup = match_opts
            options_list = list(match_opts.keys())
            
            # Zoek de juiste index op basis van de URL
            default_idx = 0
            if url_match_id:
                for i, (label, row) in enumerate(match_opts.items()):
                    if str(row['id']) == str(url_match_id):
                        default_idx = i
                        break
            
            # De dropdown die de URL bijwerkt
            sel_match_label = st.sidebar.selectbox(
                "3. Wedstrijd", 
                options_list, 
                index=default_idx,
                key="match_selector",
                on_change=update_match_url
            )
            
            sel_match_row = match_opts[sel_match_label]
            selected_match_id = str(sel_match_row['id'])
            selected_comp_id = str(sel_match_row['iterationId'])
            home_team_name = sel_match_row['home']
            away_team_name = sel_match_row['away']
            
            # Altijd de URL synchroniseren met de huidige keuze
            st.query_params["match_id"] = selected_match_id
        else:
            st.info("Geen wedstrijden gevonden voor deze selectie."); st.stop()

st.sidebar.divider()
st.sidebar.write(f"👤 **Scout:** {current_scout_name}")

# -----------------------------------------------------------------------------
# 3. SPELERS OPHALEN (Gecorrigeerd voor Naam-Recovery & Extra Spelers)
# -----------------------------------------------------------------------------
df_players = pd.DataFrame()
players_list = []

# A. Officiele Spelers uit Match Details JSON
if selected_match_id:
    df_json = run_query('SELECT "squadHome", "squadAway" FROM public.match_details_full WHERE "id" = %s', params=(selected_match_id,))
    if df_json is not None and not df_json.empty:
        for side in ['Home', 'Away']:
            raw_data = df_json.iloc[0][f'squad{side}']
            # Verwerk JSON ongeacht of het als string of dict uit de DB komt
            data = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
            
            if data and isinstance(data, dict) and 'players' in data:
                for p in data['players']:
                    p_id = p.get('id')
                    if p_id:
                        # Probeer verschillende mogelijke naam-velden uit de JSON
                        p_name = p.get('name') or p.get('shortName') or p.get('commonName') or p.get('commonname')
                        players_list.append({
                            'player_id': str(p_id), 
                            'shirt_number': p.get('shirtNumber', p.get('shirt_number', 0)), 
                            'side': side.lower(), 
                            'source': 'official',
                            'commonname': p_name # Kan None zijn, herstellen we in stap D
                        })

# B. Reeds gerapporteerde spelers uit de database (Extra spelers)
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
        
        # Voorkom dubbelen in de lijst
        exists = any(p['player_id'] == pid for p in players_list if pid) or \
                 any(p['commonname'] == pname for p in players_list if not pid)
        
        if not exists:
            players_list.append({
                'player_id': pid, 'shirt_number': 0, 'side': 'extra', 
                'source': 'reported', 'commonname': pname
            })

# C. LIVE INJECTIE: Speler die via de zoekfunctie is gekozen of wordt getypt
a_pid = st.session_state.active_player_id
if a_pid and not any(p['player_id'] == str(a_pid) for p in players_list):
    players_list.append({
        'player_id': str(a_pid), 'shirt_number': 0, 'side': 'extra', 
        'source': 'pending_db', 'commonname': None # Wordt in stap D opgehaald
    })

if st.session_state.manual_player_mode and st.session_state.manual_player_name_text:
    m_name = st.session_state.manual_player_name_text
    if not any(p['commonname'] == m_name for p in players_list):
        players_list.append({
            'player_id': None, 'shirt_number': 0, 'side': 'extra', 
            'source': 'draft', 'commonname': m_name
        })

# D. NAAM HERSTEL & SORTERING
if players_list:
    df_players = pd.DataFrame(players_list)
    
    # Als namen ontbreken, haal ze in één keer op uit public.players
    mask_missing = (df_players['commonname'].isna() | (df_players['commonname'] == "")) & df_players['player_id'].notna()
    ids_to_fetch = df_players.loc[mask_missing, 'player_id'].unique().tolist()
    
    if ids_to_fetch:
        df_n = run_query("SELECT id, commonname FROM public.players WHERE id IN %s", (tuple(ids_to_fetch),))
        if df_n is not None and not df_n.empty:
            name_map = dict(zip(df_n['id'].astype(str), df_n['commonname']))
            df_players.loc[mask_missing, 'commonname'] = df_players.loc[mask_missing, 'player_id'].map(name_map)
    
    df_players['commonname'] = df_players['commonname'].fillna("Onbekende Speler")
    
    # Pinning logica & Sortering
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
    
    # Automatisch naar tabblad 'Extra' springen bij manuele mode of database-zoekopdracht
    has_extra = not df_players.empty and not df_players[df_players['side'] == 'extra'].empty
    default_tab = 2 if (st.session_state.manual_player_mode or a_pid) and has_extra else 0
    
    sel_tab = st.radio("Team", [home_team_name, away_team_name, "Extra"], 
                       index=default_tab, horizontal=True, label_visibility="collapsed")
    side_f = 'home' if sel_tab == home_team_name else ('away' if sel_tab == away_team_name else 'extra')
    
    if not df_players.empty:
        filtered = df_players[df_players['side'] == side_f]
        if filtered.empty:
            st.info(f"Geen spelers gevonden.")
        
        for _, row in filtered.iterrows():
            p_id, p_name = row['player_id'], row['commonname']
            p_nr = int(row['shirt_number']) if row['shirt_number'] != 0 else "?"
            p_key = p_id if p_id else p_name
            d_key = f"{selected_match_id if selected_match_id else custom_match_name}_{p_key}_{current_scout_id}"
            
            c_pin, c_btn = st.columns([0.15, 0.85])
            with c_pin:
                is_p = st.checkbox("📌", value=row['is_watched'], key=f"p_{p_key}_{side_f}", label_visibility="collapsed")
                if is_p != row['is_watched']:
                    if is_p: st.session_state.watched_players.add(p_key)
                    else: st.session_state.watched_players.discard(p_key)
                    st.rerun()
            with c_btn:
                # Icoon status bepalen
                if d_key in st.session_state.scout_drafts: icon = "✅" 
                elif row['source'] == 'pending_db': icon = "🔍" 
                elif row['source'] == 'reported': icon = "📥" 
                elif row['source'] == 'draft': icon = "✍️" 
                else: icon = "👤"
                
                style = "primary" if st.session_state.active_player_id == p_id and p_id else "secondary"
                # Knop met rugnummer en herstelde naam
                if st.button(f"{icon} #{p_nr} {p_name}", key=f"b_{p_key}", type=style, use_container_width=True):
                    st.session_state.active_player_id = p_id
                    st.session_state.manual_player_mode = (p_id is None)
                    if not p_id: st.session_state.manual_player_name_text = p_name
                    st.rerun()
    
    st.divider()
    if st.button("➕ Zoeken / Manueel Toevoegen", use_container_width=True):
        st.session_state.manual_player_mode = True
        st.session_state.active_player_id = None
        st.rerun()

    if st.session_state.manual_player_mode:
        m_t = st.radio("Methode", ["🔍 Zoek Database", "✍️ Vrije Tekst"], horizontal=True)
        if "Database" in m_t:
            s_t = st.text_input("Naam (bv. Otavio):")
            if s_t:
                res = search_player_in_db(s_t)
                for _, r in res.iterrows():
                    if st.button(f"👤 {r['commonname']} ({r.get('team_naam', 'Geen club')})", key=f"s_{r['id']}", use_container_width=True):
                        st.session_state.active_player_id = str(r['id'])
                        st.session_state.manual_player_mode = False
                        st.rerun()
        else:
            st.text_input("Naam Speler:", key="manual_player_name_text")

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
        st.info("👈 Selecteer een speler om het rapport te openen."); st.stop()

    match_key = selected_match_id if selected_match_id else custom_match_name
    p_key = a_pid if a_pid else a_pname
    d_key = f"{match_key}_{p_key}_{current_scout_id}"
    st.session_state.active_d_key = d_key 

    if d_key not in st.session_state.scout_drafts:
        q_ex = """
            SELECT * FROM scouting.rapporten WHERE scout_id = %s 
            AND (speler_id = %s OR custom_speler_naam = %s) 
            AND (wedstrijd_id = %s OR custom_wedstrijd_naam = %s)
            ORDER BY aangemaakt_op DESC LIMIT 1
        """
        db_r = run_query(q_ex, (current_scout_id, a_pid, a_pname, selected_match_id, custom_match_name))
        
        if db_r is not None and not db_r.empty:
            rec = db_r.iloc[0]
            st.session_state.scout_drafts[d_key] = {
                "pos": rec.get('positie_gespeeld'), "rate": int(rec.get('beoordeling', 6)), 
                "adv": rec.get('advies'), "txt": rec.get('rapport_tekst', ""),
                "gold": bool(rec.get('gouden_buzzer', False)), "sl": rec.get('shortlist_id'), 
                "prof": rec.get('profiel_code'), "len": int(rec.get('speler_lengte', 0) or 0), 
                "con": rec.get('contract_einde', datetime.date.today())
            }
            st.session_state[f"status_{d_key}"] = "Rapport geladen."
        else:
            st.session_state.scout_drafts[d_key] = {
                "pos": None, "rate": 6, "adv": None, "txt": "", 
                "gold": False, "sl": None, "len": 0, "con": datetime.date.today(), "prof": None
            }

    draft = st.session_state.scout_drafts[d_key]

    # Header & Status
    h1, h2 = st.columns([0.7, 0.3])
    with h1: st.subheader(f"📝 Rapport: {a_pname}")
    with h2:
        sync_t = st.session_state.get(f"last_sync_{d_key}", "")
        st.caption(f"🛡️ {sync_t}" if sync_t else st.session_state.get(f"status_{d_key}", ""))

    c1, c2 = st.columns(2)
    with c1:
        p_opts = opties_posities['value'].tolist() if not opties_posities.empty else ["?"]
        p_lbls = opties_posities['label'].tolist() if not opties_posities.empty else ["?"]
        p_idx = p_opts.index(draft.get('pos')) if draft.get('pos') in p_opts else 0
        new_pos = st.selectbox("Positie", p_opts, index=p_idx, format_func=lambda x: p_lbls[p_opts.index(x)], key=f"pos_{d_key}")
        new_len = st.number_input("Lengte (cm)", 0, 230, int(draft.get('len', 0)), key=f"len_{d_key}")
        new_rate = st.slider("Beoordeling", 1, 10, int(draft.get('rate', 6)), key=f"rt_{d_key}")
    with c2:
        pr_opts = opties_profielen['value'].tolist() if not opties_profielen.empty else ["P1"]
        pr_idx = pr_opts.index(draft.get('prof')) if draft.get('prof') in pr_opts else 0
        new_prof = st.selectbox("Profiel", pr_opts, index=pr_idx, key=f"prof_{d_key}")
        a_opts = opties_advies['value'].tolist() if not opties_advies.empty else ["No"]
        a_idx = a_opts.index(draft.get('adv')) if draft.get('adv') in a_opts else 0
        new_adv = st.selectbox("Advies", a_opts, index=a_idx, key=f"adv_{d_key}")
        new_con = st.date_input("Contract", value=draft.get('con'), key=f"cn_{d_key}")

    new_txt = st.text_area("Analyse", value=draft.get('txt', ""), height=300, key=f"tx_{d_key}", on_change=sync_text_to_draft)
    new_gold = st.checkbox("🏆 Gouden Buzzer", draft.get('gold', False), key=f"gd_{d_key}")

    if st.button("💾 DEFINITIEF OPSLAAN", type="primary", use_container_width=True):
        s_d = {
            "scout_id": current_scout_id, "speler_id": a_pid, "wedstrijd_id": selected_match_id, "competitie_id": selected_comp_id,
            "custom_speler_naam": a_pname if not a_pid else None, "custom_wedstrijd_naam": custom_match_name if not selected_match_id else None,
            "positie_gespeeld": new_pos, "profiel_code": new_prof, "advies": new_adv, "beoordeling": new_rate, 
            "rapport_tekst": new_txt, "gouden_buzzer": new_gold, "shortlist_id": None, "speler_lengte": new_len, "contract_einde": new_con
        }
        if save_report_to_db(s_d):
            st.success("Opgeslagen!"); st.balloons()

