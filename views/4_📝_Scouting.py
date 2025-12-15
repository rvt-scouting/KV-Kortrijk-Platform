import streamlit as st
import pandas as pd
from utils import run_query, init_connection

st.set_page_config(page_title="Live Scouting", page_icon="📝", layout="wide")

# -----------------------------------------------------------------------------
# 1. HULPFUNCTIES & SETUP
# -----------------------------------------------------------------------------

# Helper om opties op te halen (cached voor snelheid)
@st.cache_data
def get_options_data(table_name):
    """ Haalt id en label op van een optie tabel """
    # We proberen slim te gokken welke kolom de naam bevat
    try:
        df = run_query(f"SELECT * FROM scouting.{table_name}")
        if df.empty: return pd.DataFrame()
        
        # Bepaal label kolom (naam, label, code, status...)
        cols = df.columns.tolist()
        label_col = next((c for c in cols if c in ['naam', 'label', 'status', 'omschrijving', 'code']), cols[1] if len(cols) > 1 else cols[0])
        value_col = 'id' if 'id' in cols else cols[0]
        
        return df[[value_col, label_col]].rename(columns={value_col: 'value', label_col: 'label'})
    except Exception as e:
        # st.error(f"Fout laden {table_name}: {e}") # Eventueel aanzetten voor debug
        return pd.DataFrame()

def save_report_to_db(data):
    """ 
    Slaat rapport op.
    Checkt eerst of er al een rapport is voor deze combinatie (Upsert logica).
    """
    conn = None
    try:
        conn = init_connection()
        cur = conn.cursor()
        
        # 1. Check of rapport bestaat
        check_q = """
            SELECT id FROM scouting.rapporten 
            WHERE scout_id = %s AND speler_id = %s AND wedstrijd_id = %s
        """
        cur.execute(check_q, (data['scout_id'], data['speler_id'], data['wedstrijd_id']))
        existing = cur.fetchone()
        
        if existing:
            # UPDATE
            report_id = existing[0]
            update_q = """
                UPDATE scouting.rapporten SET
                    positie_gespeeld = %s,
                    profiel_code = %s,
                    advies = %s,
                    beoordeling = %s,
                    rapport_tekst = %s,
                    gouden_busser = %s,
                    shortlist_id = %s,
                    aangemaakt_op = NOW()
                WHERE id = %s
            """
            cur.execute(update_q, (
                data['positie_gespeeld'], data['profiel_code'], data['advies'], 
                data['beoordeling'], data['rapport_tekst'], data['gouden_busser'], 
                data['shortlist_id'], report_id
            ))
        else:
            # INSERT
            insert_q = """
                INSERT INTO scouting.rapporten 
                (scout_id, speler_id, wedstrijd_id, competitie_id, positie_gespeeld, 
                 profiel_code, advies, beoordeling, rapport_tekst, gouden_busser, shortlist_id, aangemaakt_op)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            """
            cur.execute(insert_q, (
                data['scout_id'], data['speler_id'], data['wedstrijd_id'], data['competitie_id'],
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

# Initialiseer Draft State
if "scout_drafts" not in st.session_state:
    st.session_state.scout_drafts = {}

# Check Login
if 'user_info' not in st.session_state or not st.session_state.user_info:
    st.warning("⚠️ Je bent niet ingelogd. Log in om te kunnen scouten.")
    st.stop()

current_scout_id = st.session_state.user_info.get('id')
current_scout_name = st.session_state.user_info.get('naam', 'Onbekend')

# -----------------------------------------------------------------------------
# 2. WEDSTRIJD SELECTIE
# -----------------------------------------------------------------------------
st.title("📝 Live Match Scouting")

# Haal opties op (voor we beginnen)
opties_posities = get_options_data('opties_posities')
opties_profielen = get_options_data('opties_profielen')
opties_advies = get_options_data('opties_advies')
opties_shortlists = get_options_data('shortlists')

# Sidebar Filters
try:
    df_seasons = run_query("SELECT DISTINCT season FROM public.iterations ORDER BY season DESC")
    seasons = df_seasons['season'].tolist()
    sel_season = st.sidebar.selectbox("Seizoen", seasons)
except: st.error("DB Connectie fout"); st.stop()

match_query = """
    SELECT m.id, m."scheduledDate", m."iterationId", h.name as home, a.name as away
    FROM public.matches m
    JOIN public.squads h ON m."homeSquadId" = h.id
    JOIN public.squads a ON m."awaySquadId" = a.id
    WHERE m."iterationId" IN (SELECT id FROM public.iterations WHERE season = %s)
    ORDER BY m."scheduledDate" DESC
"""
df_matches = run_query(match_query, params=(sel_season,))

if df_matches.empty:
    st.info("Geen wedstrijden."); st.stop()

# Match Selector
match_opts = {f"{r['home']} vs {r['away']} ({r['scheduledDate'].strftime('%d-%m')})": r for _, r in df_matches.iterrows()}
sel_match_label = st.sidebar.selectbox("Selecteer Wedstrijd", list(match_opts.keys()))
sel_match_row = match_opts[sel_match_label]
selected_match_id = sel_match_row['id']
selected_comp_id = sel_match_row['iterationId']

st.sidebar.divider()
st.sidebar.write(f"👤 **Scout:** {current_scout_name}")

# -----------------------------------------------------------------------------
# 3. SPELERS OPHALEN
# -----------------------------------------------------------------------------
players_query = """
    SELECT md.player_id, p.commonname, md.shirt_number, md.side, sq.name as team_name
    FROM analysis.match_details md
    JOIN public.players p ON md.player_id = CAST(p.id as text)
    JOIN public.squads sq ON md.team_id = sq.id
    WHERE md.match_id = %s
    ORDER BY md.side DESC, md.shirt_number ASC
"""
try:
    df_players = run_query(players_query, params=(selected_match_id,))
except Exception as e: st.error(f"Fout spelers laden: {e}"); st.stop()

if df_players.empty: st.warning("Geen spelers gevonden."); st.stop()

# -----------------------------------------------------------------------------
# 4. UI: SPLIT VIEW
# -----------------------------------------------------------------------------
col_list, col_editor = st.columns([1, 2])

# --- LINKERKOLOM: SPELERSLIJST ---
with col_list:
    st.subheader("Selecties")
    home_team = df_players[df_players['side'] == 'home']['team_name'].iloc[0] if not df_players[df_players['side'] == 'home'].empty else "Thuis"
    away_team = df_players[df_players['side'] == 'away']['team_name'].iloc[0] if not df_players[df_players['side'] == 'away'].empty else "Uit"
    
    team_tab = st.radio("Team", [home_team, away_team], horizontal=True, label_visibility="collapsed")
    side_filter = 'home' if team_tab == home_team else 'away'
    filtered_df = df_players[df_players['side'] == side_filter]
    
    if "active_player_id" not in st.session_state: st.session_state.active_player_id = None

    for _, row in filtered_df.iterrows():
        pid = row['player_id']
        pname = f"{row['shirt_number']}. {row['commonname']}"
        
        # Check draft status
        draft_key = f"{selected_match_id}_{pid}_{current_scout_id}"
        has_draft = draft_key in st.session_state.scout_drafts
        
        btn_type = "primary" if st.session_state.active_player_id == pid else "secondary"
        icon = "📝" if has_draft else "👤"
        
        if st.button(f"{icon} {pname}", key=f"btn_{pid}", type=btn_type, use_container_width=True):
            st.session_state.active_player_id = pid
            st.rerun()

# --- RECHTERKOLOM: RAPPORT EDITOR ---
with col_editor:
    if st.session_state.active_player_id:
        p_row = df_players[df_players['player_id'] == st.session_state.active_player_id].iloc[0]
        st.subheader(f"{p_row['commonname']}")
        
        # Unieke sleutel
        draft_key = f"{selected_match_id}_{st.session_state.active_player_id}_{current_scout_id}"
        
        # 1. Initieer draft als die er nog niet is (haal uit DB of maak leeg)
        if draft_key not in st.session_state.scout_drafts:
            # Check DB
            db_q = "SELECT * FROM scouting.rapporten WHERE scout_id = %s AND speler_id = %s AND wedstrijd_id = %s"
            existing = run_query(db_q, params=(current_scout_id, int(st.session_state.active_player_id), selected_match_id))
            
            if not existing.empty:
                rec = existing.iloc[0]
                st.session_state.scout_drafts[draft_key] = {
                    "positie": rec['positie_gespeeld'],
                    "profiel": rec['profiel_code'],
                    "advies": rec['advies'],
                    "rating": int(rec['beoordeling']) if rec['beoordeling'] else 6,
                    "tekst": rec['rapport_tekst'] or "",
                    "gouden": bool(rec['gouden_busser']),
                    "shortlist": rec['shortlist_id']
                }
            else:
                st.session_state.scout_drafts[draft_key] = {
                    "positie": None, "profiel": None, "advies": None,
                    "rating": 6, "tekst": "", "gouden": False, "shortlist": None
                }
        
        draft = st.session_state.scout_drafts[draft_key]

        # --- HET FORMULIER ---
        c1, c2 = st.columns(2)
        with c1:
            # Positie Dropdown
            pos_opts = opties_posities['value'].tolist() if not opties_posities.empty else []
            pos_lbls = opties_posities['label'].tolist() if not opties_posities.empty else []
            
            # Helper om index te vinden
            def get_idx(val, opts): 
                return opts.index(val) if val in opts else 0
                
            new_pos = st.selectbox("Positie Gespeeld", pos_opts, index=get_idx(draft['positie'], pos_opts), format_func=lambda x: pos_lbls[pos_opts.index(x)] if x in pos_opts else x, key="inp_pos")
            
            # Beoordeling
            new_rating = st.slider("Beoordeling (1-10)", 1, 10, draft["rating"], key="inp_rate")

        with c2:
            # Advies Dropdown
            adv_opts = opties_advies['value'].tolist() if not opties_advies.empty else []
            adv_lbls = opties_advies['label'].tolist() if not opties_advies.empty else []
            new_adv = st.selectbox("Advies", adv_opts, index=get_idx(draft['advies'], adv_opts), format_func=lambda x: adv_lbls[adv_opts.index(x)] if x in adv_opts else x, key="inp_adv")

            # Profiel Dropdown
            prof_opts = opties_profielen['value'].tolist() if not opties_profielen.empty else []
            prof_lbls = opties_profielen['label'].tolist() if not opties_profielen.empty else []
            new_prof = st.selectbox("Profiel Type", prof_opts, index=get_idx(draft['profiel'], prof_opts), format_func=lambda x: prof_lbls[prof_opts.index(x)] if x in prof_opts else x, key="inp_prof")

        # Tekst
        new_tekst = st.text_area("Rapportage (Plus/Min/Samenvatting)", draft["tekst"], height=200, key="inp_txt")
        
        # Extra's
        ce1, ce2 = st.columns(2)
        with ce1:
            new_gouden = st.checkbox("🏆 Gouden Busser (Uitblinker)", draft["gouden"], key="inp_gold")
        with ce2:
            # Shortlist Dropdown (Optioneel)
            sl_opts = [None] + (opties_shortlists['value'].tolist() if not opties_shortlists.empty else [])
            sl_lbls = ["Geen"] + (opties_shortlists['label'].tolist() if not opties_shortlists.empty else [])
            
            # Format func moet safe zijn voor None
            def fmt_sl(x):
                if x is None: return "Geen"
                if x in sl_opts: return sl_lbls[sl_opts.index(x)]
                return str(x)
                
            new_sl = st.selectbox("Zet op Shortlist", sl_opts, index=sl_opts.index(draft['shortlist']) if draft['shortlist'] in sl_opts else 0, format_func=fmt_sl, key="inp_sl")

        # UPDATE DRAFT
        st.session_state.scout_drafts[draft_key] = {
            "positie": new_pos, "profiel": new_prof, "advies": new_adv,
            "rating": new_rating, "tekst": new_tekst, "gouden": new_gouden, "shortlist": new_sl
        }

        st.markdown("---")
        if st.button("💾 Rapport Opslaan", type="primary", use_container_width=True):
            save_data = {
                "scout_id": current_scout_id,
                "speler_id": int(st.session_state.active_player_id),
                "wedstrijd_id": selected_match_id,
                "competitie_id": selected_comp_id,
                "positie_gespeeld": new_pos,
                "profiel_code": new_prof,
                "advies": new_adv,
                "beoordeling": new_rating,
                "rapport_tekst": new_tekst,
                "gouden_busser": new_gouden,
                "shortlist_id": new_sl
            }
            
            if save_report_to_db(save_data):
                st.success(f"Rapport voor {p_row['commonname']} opgeslagen!")
                st.balloons()
            
    else:
        st.info("👈 Selecteer een speler uit de lijst om te beginnen.")
