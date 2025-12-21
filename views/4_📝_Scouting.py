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
# 1. HULPFUNCTIES
# -----------------------------------------------------------------------------
@st.cache_data
def get_scouting_options_safe(table_name):
    try:
        df = run_query(f"SELECT * FROM scouting.{table_name}")
        if df.empty: return pd.DataFrame(columns=['value', 'label'])
        cols = df.columns.tolist()
        label_col = next((c for c in cols if c in ['naam', 'label', 'omschrijving']), cols[1] if len(cols)>1 else cols[0])
        value_col = 'id' if 'id' in cols else cols[0]
        return df[[value_col, label_col]].rename(columns={value_col: 'value', label_col: 'label'})
    except:
        return pd.DataFrame(columns=['value', 'label'])

def search_player_in_db(search_term):
    """ Zoekt speler en haalt ook de clubnaam op voor context. """
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
    """ Slaat rapport op inclusief de nieuwe velden. """
    conn = None
    try:
        conn = init_connection(); cur = conn.cursor()
        
        # Check of rapport al bestaat voor deze combi
        check_q = """
            SELECT id FROM scouting.rapporten 
            WHERE scout_id = %s 
            AND (speler_id = %s OR custom_speler_naam = %s)
            AND (wedstrijd_id = %s OR custom_wedstrijd_naam = %s)
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
else:
    try:
        df_seasons = run_query("SELECT DISTINCT season FROM public.iterations ORDER BY season DESC")
        sel_season = st.sidebar.selectbox("1. Seizoen", df_seasons['season'].tolist())
        df_comps = run_query('SELECT DISTINCT "competitionName" FROM public.iterations WHERE season = %s ORDER BY "competitionName"', params=(sel_season,))
        sel_comp = st.sidebar.selectbox("2. Competitie", df_comps['competitionName'].tolist())
        
        match_query = """
            SELECT m.id, h.name as home, a.name as away, m."iterationId", m."scheduledDate"
            FROM public.matches m JOIN public.squads h ON m."homeSquadId" = h.id JOIN public.squads a ON m."awaySquadId" = a.id
            WHERE m."iterationId" IN (SELECT id FROM public.iterations WHERE season = %s AND "competitionName" = %s)
            ORDER BY m."scheduledDate" DESC
        """
        df_m = run_query(match_query, params=(sel_season, sel_comp))
        if not df_m.empty:
            match_opts = {f"{r['home']} - {r['away']} ({r['scheduledDate'].strftime('%d-%m')})": r for _, r in df_m.iterrows()}
            sel_label = st.sidebar.selectbox("3. Wedstrijd", list(match_opts.keys()))
            selected_match_id = str(match_opts[sel_label]['id'])
            selected_comp_id = str(match_opts[sel_label]['iterationId'])
            home_team_name, away_team_name = match_opts[sel_label]['home'], match_opts[sel_label]['away']
    except: pass

if not selected_match_id and not custom_match_name:
    st.info("👈 Selecteer een wedstrijd in de sidebar."); st.stop()

# -----------------------------------------------------------------------------
# 3. SPELERS OPHALEN (OFFICIEEL + GEHEUGEN)
# -----------------------------------------------------------------------------
df_players = pd.DataFrame()
players_list = []

# A. Haal officiële spelers uit match details
if selected_match_id:
    df_json = run_query('SELECT "squadHome", "squadAway" FROM public.match_details_full WHERE "id" = %s', params=(selected_match_id,))
    if not df_json.empty:
        for side in ['Home', 'Away']:
            try:
                data = json.loads(df_json.iloc[0][f'squad{side}'])
                for p in data.get('players', []):
                    players_list.append({'player_id': str(p['id']), 'shirt_number': p.get('shirtNumber', 99), 'side': side.lower(), 'source': 'official'})
            except: pass

# B. Haal handmatig toegevoegde spelers uit eerdere rapporten van deze match
q_rep = """
    SELECT r.speler_id, r.custom_speler_naam, p.commonname as db_name
    FROM scouting.rapporten r LEFT JOIN public.players p ON r.speler_id = p.id
    WHERE (r.wedstrijd_id = %s OR r.custom_wedstrijd_naam = %s)
"""
df_rep = run_query(q_rep, params=(selected_match_id, custom_match_name))
for _, r in df_rep.iterrows():
    pid = str(r['speler_id']) if r['speler_id'] else None
    pname = r['db_name'] if r['db_name'] else r['custom_speler_naam']
    # Check of speler al in lijst staat
    if not any(p['player_id'] == pid for p in players_list if pid) and not any(p['commonname'] == pname for p in players_list if not pid):
        players_list.append({'player_id': pid, 'shirt_number': 0, 'side': 'extra', 'source': 'reported', 'commonname': pname})

if players_list:
    df_players = pd.DataFrame(players_list)
    # Haal ontbrekende namen op voor officiële IDs
    ids_to_fetch = tuple(df_players[df_players['commonname'].isna()]['player_id'].unique())
    if ids_to_fetch:
        q_names = f"SELECT id, commonname FROM public.players WHERE id IN %s"
        df_n = run_query(q_names, params=(ids_to_fetch,))
        df_n['id'] = df_n['id'].astype(str)
        for _, rn in df_n.iterrows():
            df_players.loc[df_players['player_id'] == rn['id'], 'commonname'] = rn['commonname']
    
    df_players['commonname'] = df_players['commonname'].fillna("Onbekend")
    # Pinnen & Sorteren
    df_players['is_watched'] = df_players.apply(lambda r: (str(r['player_id']) if r['player_id'] else r['commonname']) in st.session_state.watched_players, axis=1)
    df_players = df_players.sort_values(by=['is_watched', 'side', 'shirt_number'], ascending=[False, True, True])

# -----------------------------------------------------------------------------
# 4. UI: SPLIT VIEW
# -----------------------------------------------------------------------------
col_list, col_editor = st.columns([1, 2])

with col_list:
    st.subheader("Selecties")
    tab_labels = [home_team_name, away_team_name, "Extra/Handmatig"]
    sel_tab = st.radio("Team", tab_labels, horizontal=True, label_visibility="collapsed")
    side_filter = 'home' if sel_tab == home_team_name else ('away' if sel_tab == away_team_name else 'extra')
    
    if not df_players.empty:
        filtered = df_players[df_players['side'] == side_filter]
        for _, row in filtered.iterrows():
            pid, pname = row['player_id'], row['commonname']
            p_key = pid if pid else pname
            dkey = f"{selected_match_id if selected_match_id else custom_match_name}_{p_key}_{current_scout_id}"
            
            c_pin, c_btn = st.columns([0.15, 0.85])
            with c_pin:
                is_p = st.checkbox("📌", value=row['is_watched'], key=f"p_{p_key}", label_visibility="collapsed")
                if is_p != row['is_watched']:
                    st.session_state.watched_players.add(p_key) if is_p else st.session_state.watched_players.discard(p_key)
                    st.rerun()
            with c_btn:
                style = "primary" if st.session_state.active_player_id == pid and pid else "secondary"
                icon = "📝" if dkey in st.session_state.scout_drafts else ("📥" if row['source'] == 'reported' else "👤")
                if st.button(f"{icon} {pname}", key=f"b_{p_key}", type=style, use_container_width=True):
                    st.session_state.active_player_id, st.session_state.manual_player_mode = pid, (pid is None)
                    if not pid: st.session_state.manual_player_name_text = pname
                    st.rerun()

    st.divider()
    if st.button("➕ Speler Zoeken / Toevoegen", use_container_width=True):
        st.session_state.manual_player_mode = True; st.session_state.active_player_id = None

    if st.session_state.manual_player_mode:
        m_type = st.radio("Methode", ["🔍 Database", "✍️ Manuele Naam"], horizontal=True)
        if "Database" in m_type:
            s_txt = st.text_input("Zoek speler (Otavio, ...):")
            if s_txt:
                res = search_player_in_db(s_txt)
                for _, r in res.iterrows():
                    c_info = f" ({r['team_naam']})" if r['team_naam'] else ""
                    if st.button(f"👤 {r['commonname']}{c_info}", key=f"s_{r['id']}", use_container_width=True):
                        st.session_state.active_player_id = str(r['id']); st.session_state.manual_player_mode = False; st.rerun()
        else:
            m_n = st.text_input("Naam Speler:"); st.session_state.manual_player_name_text = m_n

# -----------------------------------------------------------------------------
# 5. EDITOR (RECHTER KOLOM)
# -----------------------------------------------------------------------------
with col_editor:
    # A. BEPAAL DE NAAM VAN DE ACTIEVE SPELER
    a_pid = st.session_state.active_player_id
    a_pname = st.session_state.manual_player_name_text if not a_pid else "Laden..."
    
    # Als we een ID hebben, halen we de officiële naam op uit de DB
    if a_pid:
        res_n = run_query("SELECT commonname FROM public.players WHERE id = %s", params=(a_pid,))
        if not res_n.empty: 
            a_pname = res_n.iloc[0]['commonname']
    
    # Stop als er nog geen speler is geselecteerd
    if not a_pname or a_pname == "Laden...":
        st.info("👈 Selecteer een speler uit de lijst of zoek een speler om het rapport te starten.")
        st.stop()

    st.subheader(f"Rapport: {a_pname}")
    
    # B. DRAFT LOGICA (Laden uit DB of Session State)
    # Maak een unieke sleutel voor dit specifieke rapport
    match_key = selected_match_id if selected_match_id else custom_match_name
    player_key = a_pid if a_pid else a_pname
    d_key = f"{match_key}_{player_key}_{current_scout_id}"
    
    # Als dit rapport nog niet in het geheugen (session_state) zit, probeer het uit de database te halen
    if d_key not in st.session_state.scout_drafts:
        q_ex = """
            SELECT * FROM scouting.rapporten 
            WHERE scout_id=%s 
            AND (speler_id=%s OR custom_speler_naam=%s) 
            AND (wedstrijd_id=%s OR custom_wedstrijd_naam=%s)
        """
        db_r = run_query(q_ex, (current_scout_id, a_pid, a_pname, selected_match_id, custom_match_name))
        
        if not db_r.empty:
            rec = db_r.iloc[0]
            # Map de database kolommen naar onze geheugen-sleutels
            st.session_state.scout_drafts[d_key] = {
                "pos": rec.get('positie_gespeeld'), 
                "rate": int(rec.get('beoordeling', 6)), 
                "adv": rec.get('advies'), 
                "txt": rec.get('rapport_tekst', ""),
                "gold": bool(rec.get('gouden_buzzer', False)), 
                "sl": rec.get('shortlist_id'), 
                "len": int(rec.get('speler_lengte', 0) or 0), 
                "con": rec.get('contract_einde')
            }
        else:
            # Helemaal nieuw rapport: start met lege waarden
            st.session_state.scout_drafts[d_key] = {
                "pos": "Middenvelder", "rate": 6, "adv": "Follow", "txt": "", 
                "gold": False, "sl": None, "len": 0, "con": datetime.date.today()
            }

    # Haal de huidige data uit de session_state (gebruik .get() voor extra veiligheid)
    draft = st.session_state.scout_drafts[d_key]
    
    # C. FORMULIER INVULLEN
    c1, c2 = st.columns(2)
    
    with c1:
        pos_options = ["Doelman", "Verdediger", "Middenvelder", "Aanvaller"]
        # Zoek welke index we moeten tonen
        current_pos = draft.get('pos')
        pos_idx = pos_options.index(current_pos) if current_pos in pos_options else 2 # Default Middenvelder
        
        new_pos = st.selectbox("Positie", pos_options, index=pos_idx, key=f"pos_{d_key}")
        
        # LENGTE (De fix voor de KeyError)
        val_len = int(draft.get('len', 0) or 0)
        new_len = st.number_input("Lengte (cm)", 0, 230, val_len, key=f"len_{d_key}")
        
        new_rate = st.slider("Beoordeling", 1, 10, int(draft.get('rate', 6)), key=f"rt_{d_key}")

    with c2:
        adv_options = ["Sign", "Follow", "No"]
        current_adv = draft.get('adv')
        adv_idx = adv_options.index(current_adv) if current_adv in adv_options else 1
        
        new_adv = st.selectbox("Advies", adv_options, index=adv_idx, key=f"adv_{d_key}")
        
        # CONTRACT
        val_con = draft.get('con')
        if not val_con: val_con = datetime.date.today()
        new_con = st.date_input("Contract Einde", value=val_con, key=f"cn_{d_key}")
        
        # SHORTLIST (Optioneel: haal lijst op uit je opties_shortlists indien beschikbaar)
        new_sl = st.selectbox("Shortlist", [None, 1], format_func=lambda x: "Geen" if x is None else "Hoofd Shortlist", key=f"sl_{d_key}")

    new_txt = st.text_area("Analyse / Rapportage", draft.get('txt', ""), height=250, key=f"tx_{d_key}")
    new_gold = st.checkbox("🏆 Gouden Buzzer", draft.get('gold', False), key=f"gd_{d_key}")

    # D. OPSLAAN LOGICA
    st.divider()
    if st.button("💾 Rapport Opslaan", type="primary", use_container_width=True):
        save_data = {
            "scout_id": current_scout_id, 
            "speler_id": a_pid, 
            "wedstrijd_id": selected_match_id, 
            "competitie_id": selected_comp_id,
            "custom_speler_naam": a_pname if not a_pid else None, 
            "custom_wedstrijd_naam": custom_match_name if not selected_match_id else None,
            "positie_gespeeld": new_pos, 
            "profiel_code": "P1", # Je kunt dit later dynamisch maken
            "advies": new_adv, 
            "beoordeling": new_rate, 
            "rapport_tekst": new_txt,
            "gouden_buzzer": new_gold, 
            "shortlist_id": new_sl, 
            "speler_lengte": new_len, 
            "contract_einde": new_con
        }
        
        if save_report_to_db(save_data):
            # Update de session state zodat de UI synchroon blijft (vooral handig voor de vinkjes in de lijst)
            st.session_state.scout_drafts[d_key] = {
                "pos": new_pos, "rate": new_rate, "adv": new_adv, "txt": new_txt, 
                "gold": new_gold, "sl": new_sl, "len": new_len, "con": new_con
            }
            st.success(f"Rapport voor {a_pname} succesvol opgeslagen!")
            st.balloons()
            # Optioneel: st.rerun() om de icoontjes in de spelerslijst direct te updaten naar 📝
