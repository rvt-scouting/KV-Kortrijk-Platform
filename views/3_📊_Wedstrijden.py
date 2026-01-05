import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from utils import run_query
import json

st.set_page_config(page_title="Match Events", page_icon="🏟️", layout="wide")

# -----------------------------------------------------------------------------
# HELPER FUNCTIES
# -----------------------------------------------------------------------------
def normalize_id(val):
    try:
        if pd.isna(val) or val == 'nan' or val == 'None': return None
        return str(int(float(val)))
    except: return str(val).strip()

def parse_gametime_to_min(t_str):
    try:
        if not isinstance(t_str, str): return 0.0
        main_part = t_str.split('.')[0] 
        parts = main_part.split(':')
        if len(parts) >= 2: return float(parts[0]) + float(parts[1])/60.0
        return float(parts[0]) if len(parts) == 1 else 0.0
    except: return 0.0

# -----------------------------------------------------------------------------
# 1. SELECTIE
# -----------------------------------------------------------------------------
st.sidebar.header("🔍 Wedstrijd Selectie")

try:
    df_seasons = run_query("SELECT DISTINCT season FROM public.iterations ORDER BY season DESC")
    seasons = df_seasons['season'].tolist()
    idx_s = 0
    if "sb_season" in st.session_state and st.session_state.sb_season in seasons:
        idx_s = seasons.index(st.session_state.sb_season)
    sel_season = st.sidebar.selectbox("Seizoen", seasons, index=idx_s, key="sb_season")
except:
    st.error("Geen seizoenen gevonden.")
    st.stop()

if sel_season:
    df_comps = run_query('SELECT DISTINCT "competitionName" FROM public.iterations WHERE season = %s', (sel_season,))
    comps = df_comps['competitionName'].tolist()
    sel_comp = st.sidebar.selectbox("Competitie", comps)
else:
    st.stop()

if sel_season and sel_comp:
    q_matches = """
        SELECT m.id, m."scheduledDate", h.name as home, a.name as away, 
               m."homeSquadId", m."awaySquadId"
        FROM public.matches m
        JOIN public.squads h ON m."homeSquadId" = h.id
        JOIN public.squads a ON m."awaySquadId" = a.id
        JOIN public.iterations i ON m."iterationId" = i.id
        WHERE i.season = %s 
          AND i."competitionName" = %s
          AND m."scheduledDate" <= NOW()
        ORDER BY m."scheduledDate" DESC
    """
    df_matches = run_query(q_matches, (sel_season, sel_comp))
    if df_matches.empty:
        st.warning("Geen gespeelde wedstrijden gevonden.")
        st.stop()
        
    match_opts = {f"{r['home']} - {r['away']} ({r['scheduledDate'].strftime('%d-%m')})": r['id'] for _, r in df_matches.iterrows()}
    sel_match_label = st.sidebar.selectbox("Wedstrijd", list(match_opts.keys()))
    sel_match_id = str(match_opts[sel_match_label])
    match_row = df_matches[df_matches['id'] == sel_match_id].iloc[0]
else:
    st.stop()

st.title(f"🏟️ {match_row['home']} vs {match_row['away']}")
st.caption(f"Datum: {match_row['scheduledDate'].strftime('%d-%m-%Y %H:%M')}")

# -----------------------------------------------------------------------------
# 2. DATA OPHALEN EVENTS
# -----------------------------------------------------------------------------
@st.cache_data
def get_match_data_optimized(match_id):
    q_events = """
        SELECT 
            e.index as "Volgorde",
            e."squadId", e.action, e."actionType", e.result,
            (e.player ->> 'id') as player_id_raw,
            (e."gameTime" ->> 'gameTime') as "TijdString",
            
            e."distanceToOpponent",
            e."phase",
            e."pressure",
            e."periodId",
            e."pressingPlayerId",
            
            CAST(e."start" -> 'coordinates' ->> 'x' AS FLOAT) as x_start,
            CAST(e."start" -> 'coordinates' ->> 'y' AS FLOAT) as y_start,
            CAST(e."end" -> 'coordinates' ->> 'x' AS FLOAT) as x_end,
            CAST(e."end" -> 'coordinates' ->> 'y' AS FLOAT) as y_end,
            
            CAST(e."pxT" ->> 'team' AS FLOAT) as "xT_Team_Raw",
            CAST(e."pxT" ->> 'opponent' AS FLOAT) as "xT_Opp_Raw"
        FROM public.match_events e
        WHERE e."matchId" = %s 
        ORDER BY e.index ASC
    """
    df_ev = run_query(q_events, (match_id,))
    if df_ev.empty: return pd.DataFrame()
    
    df_ev['Minuut'] = df_ev['TijdString'].apply(parse_gametime_to_min)
    
    # Teams Map
    squad_ids = df_ev['squadId'].dropna().unique().tolist()
    squad_map = {}
    if squad_ids:
        s_ids_formatted = ", ".join(f"'{x}'" for x in squad_ids)
        if s_ids_formatted:
            df_sq = run_query(f"SELECT id, name FROM public.squads WHERE id IN ({s_ids_formatted})")
            if not df_sq.empty:
                squad_map = dict(zip(df_sq['id'].astype(str), df_sq['name']))
    df_ev['Team'] = df_ev['squadId'].astype(str).map(squad_map).fillna('Onbekend')

    # Spelers Map
    p_ids_1 = df_ev['player_id_raw'].dropna().unique().tolist()
    p_ids_2 = df_ev['pressingPlayerId'].dropna().unique().tolist()
    all_p_ids = list(set(p_ids_1 + p_ids_2))
    all_p_ids = [str(pid) for pid in all_p_ids if str(pid).isdigit()]
    
    player_map = {}
    if all_p_ids:
        p_ids_formatted = ", ".join(f"'{x}'" for x in all_p_ids)
        if p_ids_formatted:
            df_pl = run_query(f"SELECT id, commonname FROM public.players WHERE id IN ({p_ids_formatted})")
            if not df_pl.empty:
                player_map = dict(zip(df_pl['id'].astype(str), df_pl['commonname']))
    
    df_ev['Speler'] = df_ev['player_id_raw'].astype(str).map(player_map).fillna('Onbekend')
    df_ev['PressingSpeler'] = df_ev['pressingPlayerId'].astype(str).map(player_map).fillna('-')

    return df_ev

# -----------------------------------------------------------------------------
# 3. DATA OPHALEN OPSTELLINGEN
# -----------------------------------------------------------------------------
@st.cache_data
def get_match_lineups(match_id):
    q = 'SELECT "squadHome", "squadAway" FROM public.match_details_full WHERE id = %s'
    df_details = run_query(q, (match_id,))
    
    if df_details.empty:
        return None, None
    
    row = df_details.iloc[0]
    
    def parse_squad_json(squad_data):
        if not squad_data: return {}
        if isinstance(squad_data, str):
            data = json.loads(squad_data)
        else:
            data = squad_data
            
        coach_id = data.get('coachId')
        players_raw = data.get('players', [])
        starting_raw = data.get('startingPositions', [])
        
        starters_map = {str(p['playerId']): p for p in starting_raw}
        
        roster = []
        player_ids_to_fetch = []
        
        for p in players_raw:
            pid = str(p['id'])
            shirt = p.get('shirtNumber', '-')
            player_ids_to_fetch.append(pid)
            
            if pid in starters_map:
                role = "Basis"
                pos = starters_map[pid].get('position', '?')
                pos_side = starters_map[pid].get('positionSide', '')
            else:
                role = "Wissel"
                pos = "Bank"
                pos_side = ""
            
            roster.append({
                'id': pid,
                'shirt': shirt,
                'role': role,
                'position': pos,
                'side': pos_side
            })
            
        return {
            'coachId': str(coach_id) if coach_id else None,
            'roster': roster,
            'ids': player_ids_to_fetch
        }

    home_parsed = parse_squad_json(row['squadHome'])
    away_parsed = parse_squad_json(row['squadAway'])
    
    all_player_ids = home_parsed['ids'] + away_parsed['ids']
    all_coach_ids = [x for x in [home_parsed['coachId'], away_parsed['coachId']] if x]
    
    p_map = {}
    if all_player_ids:
        clean_p_ids = [x for x in all_player_ids if x.isdigit()]
        if clean_p_ids:
            p_str = ", ".join(f"'{x}'" for x in clean_p_ids)
            df_p = run_query(f"SELECT id, commonname FROM public.players WHERE id IN ({p_str})")
            if not df_p.empty:
                p_map = dict(zip(df_p['id'].astype(str), df_p['commonname']))

    c_map = {}
    if all_coach_ids:
        clean_c_ids = [x for x in all_coach_ids if x.isdigit()]
        if clean_c_ids:
            c_str = ", ".join(f"'{x}'" for x in clean_c_ids)
            try:
                df_c = run_query(f"SELECT id, name FROM public.coaches WHERE id IN ({c_str})")
                if not df_c.empty:
                    c_map = dict(zip(df_c['id'].astype(str), df_c['name']))
            except: pass

    def enrich(parsed):
        parsed['coachName'] = c_map.get(parsed['coachId'], 'Onbekend')
        for p in parsed['roster']:
            p['name'] = p_map.get(p['id'], 'Onbekend')
        return parsed

    return enrich(home_parsed), enrich(away_parsed)


with st.spinner("Bezig met analyseren..."):
    df_events = get_match_data_optimized(sel_match_id)
    lineup_home, lineup_away = get_match_lineups(sel_match_id)

# -----------------------------------------------------------------------------
# VERWERKING LOGICA (ROBUUST GEMAAKT)
# -----------------------------------------------------------------------------
# Als df_events leeg is, voeg de kolommen toe om errors te voorkomen
if df_events.empty:
    st.warning("⚠️ Geen events data beschikbaar voor deze wedstrijd.")
    cols_needed = [
        "action", "result", "squadId", "xT_Team_Raw", "xT_Opp_Raw", 
        "periodId", "distanceToOpponent", "pressure", "phase", 
        "Team", "Speler", "PressingSpeler", "TijdString", "Minuut", 
        "x_start", "y_start", "x_end", "y_end"
    ]
    for c in cols_needed:
        if c not in df_events.columns:
            df_events[c] = pd.Series(dtype='object')

# Nu kunnen we veilig transformeren, zelfs als het leeg is
df_events['action_clean'] = df_events['action'].astype(str).str.upper().str.strip()
df_events['result_clean'] = df_events['result'].astype(str).str.upper().str.strip()
home_id_str = normalize_id(match_row['homeSquadId'])
df_events['squadId_clean'] = df_events['squadId'].apply(normalize_id)

df_events['xT_Team_Raw'] = df_events['xT_Team_Raw'].fillna(0)
df_events['xT_Opp_Raw'] = df_events['xT_Opp_Raw'].fillna(0)

if not df_events.empty:
    max_x = df_events['x_start'].max()
    min_x = df_events['x_start'].min()
    
    # Als de data groter is dan 55 (dus waarschijnlijk 100 of 105) 
    # EN er zijn geen negatieve waardes (dus 0 is de start), dan moeten we shiften.
    if max_x > 55 and min_x >= 0:
        # Aanname: Bron is 0-100 of 0-105. We schalen naar 105x68 meters.
        # Factor berekenen (is de data 0-100 of 0-1 ?)
        scale_x = 105.0 / 100.0 if max_x <= 100 else 1.0 # Als max rond 100 is, schaal iets op naar 105m
        scale_y = 68.0 / 100.0 if df_events['y_start'].max() <= 100 else 1.0

        # Formule: (Waarde - 50%) * Schaal
        # Dit zet 0 om naar -52.5 en 100 om naar +52.5
        # Let op: Soms moet Y omgedraaid worden (100-y), check dit in de app!
        df_events['x_start'] = (df_events['x_start'] - 50) * (105/100)
        df_events['y_start'] = (df_events['y_start'] - 50) * (68/100) # Pas aan naar (68/100) * -1 als het ondersteboven is
        
        # Doe hetzelfde voor end coordinates
        df_events['x_end'] = (df_events['x_end'] - 50) * (105/100)
        df_events['y_end'] = (df_events['y_end'] - 50) * (68/100)

def calc_home_threat(row):
    if row['squadId_clean'] == home_id_str:
        return row['xT_Team_Raw'] - row['xT_Opp_Raw']
    else:
        return row['xT_Opp_Raw'] - row['xT_Team_Raw']

df_events['Home_Net_Threat_State'] = df_events.apply(calc_home_threat, axis=1)
df_events['xT_Generated_Raw'] = df_events['Home_Net_Threat_State'].shift(-1) - df_events['Home_Net_Threat_State']

def calc_player_xt(row):
    if pd.isna(row['xT_Generated_Raw']): return 0.0
    if row['squadId_clean'] == home_id_str: return row['xT_Generated_Raw']
    else: return -row['xT_Generated_Raw']

df_events['xT_Generated_Player'] = df_events.apply(calc_player_xt, axis=1)

team_colors = {match_row['home']: '#e74c3c', match_row['away']: '#3498db', 'Onbekend': '#95a5a6'} 
result_colors = {'SUCCESS': '#2ecc71', 'FAIL': '#e74c3c', 'OFFSIDE': '#95a5a6', 'NONE': '#bdc3c7', 'nan': '#bdc3c7', '': '#bdc3c7'}

# -----------------------------------------------------------------------------
# 4. DASHBOARD TABS
# -----------------------------------------------------------------------------
tab1, tab2, tab3, tab4, tab5 = st.tabs(["👥 Opstellingen", "📊 Stats & Tijdlijn", "📍 Pitch Map & Radar", "🏃 Spelers xT", "📋 Data"])

# --- TAB 1: OPSTELLINGEN ---
with tab1:
    st.subheader("👥 Opstellingen")
    if lineup_home and lineup_away:
        col_h, col_a = st.columns(2)
        def render_lineup(data, team_name, color):
            with st.container():
                st.markdown(f"<h3 style='color:{color}'>{team_name}</h3>", unsafe_allow_html=True)
                st.write(f"**Coach:** {data['coachName']}")
                
                st.markdown("#### Basiself")
                basis = [p for p in data['roster'] if p['role'] == 'Basis']
                df_basis = pd.DataFrame(basis)
                if not df_basis.empty:
                    df_basis = df_basis[['shirt', 'name', 'position', 'side']]
                    st.dataframe(df_basis, hide_index=True, use_container_width=True)
                else:
                    st.write("Geen basiself gevonden.")
                
                st.markdown("#### Wissels")
                bank = [p for p in data['roster'] if p['role'] == 'Wissel']
                df_bank = pd.DataFrame(bank)
                if not df_bank.empty:
                    df_bank = df_bank[['shirt', 'name']]
                    st.dataframe(df_bank, hide_index=True, use_container_width=True)
                else:
                    st.write("Geen wisselspelers gevonden.")
        
        with col_h: render_lineup(lineup_home, match_row['home'], team_colors.get(match_row['home'], 'black'))
        with col_a: render_lineup(lineup_away, match_row['away'], team_colors.get(match_row['away'], 'black'))
    else:
        st.info("Geen opstellingsdata beschikbaar.")

# --- TAB 2: STATS & TIJDLIJN ---
with tab2:
    if df_events.empty:
        st.info("Geen data om weer te geven.")
    else:
        # Scorebord
        goals_home = df_events[(df_events['squadId_clean'] == home_id_str) & (df_events['action_clean'] == 'GOAL')]
        own_goals_home_benefit = df_events[(df_events['squadId_clean'] != home_id_str) & (df_events['action_clean'] == 'OWN_GOAL')]
        score_home = len(goals_home) + len(own_goals_home_benefit)

        goals_away = df_events[(df_events['squadId_clean'] != home_id_str) & (df_events['action_clean'] == 'GOAL')]
        own_goals_away_benefit = df_events[(df_events['squadId_clean'] == home_id_str) & (df_events['action_clean'] == 'OWN_GOAL')]
        score_away = len(goals_away) + len(own_goals_away_benefit)

        st.markdown(f"<h1 style='text-align: center; color: #333;'>{match_row['home']} {score_home} - {score_away} {match_row['away']}</h1>", unsafe_allow_html=True)

        col_tl, col_st = st.columns([3, 2])
        with col_tl:
            st.subheader("Wedstrijdverloop")
            mask_hl = df_events['action_clean'].isin(['GOAL', 'OWN_GOAL', 'CARD', 'YELLOW_CARD', 'RED_CARD', 'SUBSTITUTION'])
            imp = df_events[mask_hl].copy()
            
            if not imp.empty:
                event_colors = {
                    "GOAL": "#2ecc71", "OWN_GOAL": "#e74c3c", 
                    "CARD": "#f1c40f", "YELLOW_CARD": "#f1c40f", "RED_CARD": "#c0392b",
                    "SUBSTITUTION": "#3498db"
                }
                fig_tl = px.scatter(imp, x="Minuut", y="Team", color="action_clean", symbol="action_clean",
                                    color_discrete_map=event_colors, size_max=15, hover_data=["Speler"])
                fig_tl.update_traces(marker=dict(size=14, line=dict(width=1, color='DarkSlateGrey')))
                fig_tl.update_layout(height=350, showlegend=True)
                st.plotly_chart(fig_tl, use_container_width=True)
            else:
                st.info("Geen hoogtepunten.")

        with col_st:
            st.subheader("Team Stats")
            stats = df_events.groupby(['Team', 'action_clean']).size().reset_index(name='Cnt')
            if not stats.empty:
                piv = stats.pivot(index='action_clean', columns='Team', values='Cnt').fillna(0).astype(int)
                piv['Total'] = piv.sum(axis=1)
                st.dataframe(piv.sort_values('Total', ascending=False).drop(columns='Total'), use_container_width=True)
            else:
                st.info("Geen stats.")

        st.divider()
        c1, c2 = st.columns(2)
        with c1:
            st.write("**Total Expected Threat (xT)**")
            xt_total = df_events.groupby('Team')['xT_Team_Raw'].sum().reset_index()
            if not xt_total.empty:
                fig_xt = px.bar(xt_total, x='Team', y='xT_Team_Raw', color='Team', 
                                color_discrete_map=team_colors, title="Totaal Gecreëerde xT")
                st.plotly_chart(fig_xt, use_container_width=True)
            else:
                st.info("Geen xT data.")

        with c2:
            st.write("**Pass Types (Succesratio)**")
            passes = df_events[df_events['action_clean'].str.contains('PASS')].copy()
            if not passes.empty:
                pass_agg = passes.groupby(['Team', 'action_clean']).agg(
                    Totaal=('action', 'count'),
                    Succes=('result_clean', lambda x: (x == 'SUCCESS').sum())
                ).reset_index()
                
                df_melt = pass_agg.melt(id_vars=['Team', 'action_clean'], value_vars=['Totaal', 'Succes'], 
                                        var_name='Status', value_name='Aantal')
                fig_pass = px.bar(
                    df_melt, x='action_clean', y='Aantal', 
                    color='Status', barmode='group',
                    facet_col='Team', 
                    color_discrete_map={'Totaal': '#95a5a6', 'Succes': '#2ecc71'},
                    title="Passes: Totaal vs Succes"
                )
                fig_pass.update_xaxes(title=None, tickangle=-45)
                st.plotly_chart(fig_pass, use_container_width=True)
            else:
                st.info("Geen passes.")

# --- TAB 3: PITCH MAP & RADAR ---
with tab3:
    st.subheader("📍 Event Map Analysis")
    if df_events.empty:
        st.info("Geen data.")
    else:
        c1, c2, c3, c4 = st.columns(4)
        teams = df_events['Team'].unique()
        sel_teams = c1.multiselect("Teams", teams, default=teams, key="pm_teams")
        acts = df_events['action_clean'].unique()
        def_acts = [x for x in ['SHOT','GOAL'] if x in acts]
        sel_acts = c2.multiselect("Acties", acts, default=def_acts, key="pm_acts")
        periods = sorted(df_events['periodId'].astype(str).unique())
        sel_period = c3.multiselect("Periode / Helft", periods, default=periods, key="pm_period")
        plys = df_events['Speler'].unique()
        sel_plys = c4.multiselect("Speler", plys, key="pm_plys")
        
        st.markdown("### Extra Filters & Opties")
        f_c1, f_c2, f_c3 = st.columns(3)
        try:
            dist_vals = df_events['distanceToOpponent'].dropna().unique()
            dist_opts = sorted(dist_vals, key=lambda x: float(x))
        except:
            dist_opts = sorted(df_events['distanceToOpponent'].dropna().astype(str).unique())
        sel_dist = f_c1.multiselect("Afstand tot Opponent", dist_opts, key="pm_dist")
        
        try:
            pres_vals = df_events['pressure'].dropna().unique()
            pres_opts = sorted(pres_vals, key=lambda x: float(x))
        except:
            pres_opts = sorted(df_events['pressure'].dropna().astype(str).unique())
        sel_pres = f_c2.multiselect("Pressure", pres_opts, key="pm_pres")
        
        phases = sorted(df_events['phase'].dropna().astype(str).unique().tolist())
        sel_phase = f_c3.multiselect("Spelfase", phases, key="pm_phase")
        
        v_c1, v_c2 = st.columns(2)
        show_lines = v_c1.checkbox("Toon Pass/Looplijnen", value=False, key="pm_lines")
        color_mode = v_c2.radio("Kleur op basis van:", ["Team", "Resultaat (Succes/Fail)"], horizontal=True, key="pm_color")

        # Filter
        df_m = df_events[(df_events['Team'].isin(sel_teams)) & (df_events['action_clean'].isin(sel_acts))].copy() 
        if sel_period: df_m = df_m[df_m['periodId'].astype(str).isin(sel_period)]
        if sel_dist: df_m = df_m[df_m['distanceToOpponent'].isin(sel_dist)]
        if sel_pres: df_m = df_m[df_m['pressure'].isin(sel_pres)]
        if sel_phase: df_m = df_m[df_m['phase'].isin(sel_phase)]
        if sel_plys: df_m = df_m[df_m['Speler'].isin(sel_plys)]
        
        if not df_m.empty:
            # --- 1. DE SCATTER MAP ---
            fig = go.Figure()
            # Veld
            fig.add_shape(type="rect", x0=-52.5, y0=-34, x1=52.5, y1=34, line=dict(color="white"), fillcolor="#4CAF50", layer="below")
            fig.add_shape(type="line", x0=0, y0=-34, x1=0, y1=34, line=dict(color="white"))
            fig.add_shape(type="circle", x0=-9.15, y0=-9.15, x1=9.15, y1=9.15, line=dict(color="white"))
            fig.add_shape(type="rect", x0=-52.5, y0=-20.16, x1=-36, y1=20.16, line=dict(color="white"))
            fig.add_shape(type="rect", x0=-52.5, y0=-9.16, x1=-46.5, y1=9.16, line=dict(color="white"))
            fig.add_shape(type="rect", x0=36, y0=-20.16, x1=52.5, y1=20.16, line=dict(color="white"))
            fig.add_shape(type="rect", x0=46.5, y0=-9.16, x1=52.5, y1=9.16, line=dict(color="white"))

            if color_mode == "Team":
                groups = sel_teams
            else:
                df_m['result_plot'] = df_m['result_clean'].replace({'': 'NONE', 'nan': 'NONE'}).fillna('NONE')
                groups = df_m['result_plot'].unique()

            for key in groups:
                if color_mode == "Team":
                    d = df_m[df_m['Team'] == key]
                    color = team_colors.get(key, '#95a5a6')
                    name_lbl = key
                else:
                    d = df_m[df_m['result_plot'] == key]
                    color = result_colors.get(key, '#bdc3c7')
                    name_lbl = key

                if d.empty: continue

                fig.add_trace(go.Scatter(
                    x=d['x_start'], y=d['y_start'], mode='markers', name=name_lbl,
                    marker=dict(color=color, size=8, line=dict(width=1,color='black')),
                    text=d['Speler'] + " (" + d['action'] + ") [" + d['result_clean'] + "]",
                    hovertemplate="%{text}<br>DistOpp: %{customdata[1]}<br>Press: %{customdata[2]}<br>Pressing Speler: %{customdata[3]}",
                    customdata=d[['TijdString', 'distanceToOpponent', 'pressure', 'PressingSpeler']]
                ))
                
                if show_lines and len(d) < 2000:
                    x_lines = []
                    y_lines = []
                    for _, row in d.iterrows():
                        if pd.notnull(row['x_end']) and pd.notnull(row['y_end']):
                            x_lines.extend([row['x_start'], row['x_end'], None])
                            y_lines.extend([row['y_start'], row['y_end'], None])
                    
                    if x_lines:
                        fig.add_trace(go.Scatter(
                            x=x_lines, y=y_lines, mode='lines',
                            line=dict(color=color, width=1), opacity=0.5, showlegend=False, hoverinfo='skip'
                        ))

            fig.update_layout(
                width=800, height=550, 
                xaxis=dict(visible=False, range=[-55, 55]), 
                yaxis=dict(visible=False, range=[-36, 36], scaleanchor="x", scaleratio=1),
                plot_bgcolor='rgba(0,0,0,0)', margin=dict(l=0, r=0, t=20, b=0)
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # --- 2. DE SPIDER DIAGRAM ---
            st.divider()
            st.subheader("🕸️ Spider Diagram: Team Vergelijking")
            if len(sel_acts) > 0:
                radar_agg = df_m.groupby(['Team', 'action_clean']).size().reset_index(name='Count')
                fig_rad = go.Figure()
                for t in sel_teams:
                    vals = []
                    for a in sel_acts:
                        row = radar_agg[(radar_agg['Team'] == t) & (radar_agg['action_clean'] == a)]
                        vals.append(row['Count'].values[0] if not row.empty else 0)
                    if vals:
                        vals_plot = vals + [vals[0]]
                        thetas_plot = sel_acts + [sel_acts[0]]
                        fig_rad.add_trace(go.Scatterpolar(r=vals_plot, theta=thetas_plot, fill='toself', name=t, line_color=team_colors.get(t, '#95a5a6')))
                fig_rad.update_layout(polar=dict(radialaxis=dict(visible=True)), showlegend=True, height=500)
                st.plotly_chart(fig_rad, use_container_width=True)

            # --- 3. DE NIEUWE HEATMAP ---
            st.divider()
            st.subheader("🔥 Actie Heatmap")
            st.caption("Dichtheid van de geselecteerde acties")
            
            fig_hm = go.Figure()
            # Veld (Hetzelfde als hierboven)
            fig_hm.add_shape(type="rect", x0=-52.5, y0=-34, x1=52.5, y1=34, line=dict(color="white"), fillcolor="#4CAF50", layer="below")
            fig_hm.add_shape(type="line", x0=0, y0=-34, x1=0, y1=34, line=dict(color="white"))
            fig_hm.add_shape(type="circle", x0=-9.15, y0=-9.15, x1=9.15, y1=9.15, line=dict(color="white"))
            fig_hm.add_shape(type="rect", x0=-52.5, y0=-20.16, x1=-36, y1=20.16, line=dict(color="white"))
            fig_hm.add_shape(type="rect", x0=-52.5, y0=-9.16, x1=-46.5, y1=9.16, line=dict(color="white"))
            fig_hm.add_shape(type="rect", x0=36, y0=-20.16, x1=52.5, y1=20.16, line=dict(color="white"))
            fig_hm.add_shape(type="rect", x0=46.5, y0=-9.16, x1=52.5, y1=9.16, line=dict(color="white"))

            # Heatmap layer
            fig_hm.add_trace(go.Histogram2dContour(
                x=df_m['x_start'],
                y=df_m['y_start'],
                colorscale='Hot',
                reversescale=True,
                xaxis='x',
                yaxis='y',
                ncontours=15,
                showscale=False,
                opacity=0.7
            ))

            fig_hm.update_layout(
                width=800, height=550, 
                xaxis=dict(visible=False, range=[-55, 55]), 
                yaxis=dict(visible=False, range=[-36, 36], scaleanchor="x", scaleratio=1),
                plot_bgcolor='rgba(0,0,0,0)', margin=dict(l=0, r=0, t=20, b=0)
            )
            st.plotly_chart(fig_hm, use_container_width=True)

        else:
            st.info("Geen events met deze filters.")

# --- TAB 4: SPELERS xT ---
with tab4:
    st.subheader("🏆 Top xT Generators")
    st.caption("Som van xT verschil (Delta) per speler.")
    if not df_events.empty:
        xt_stats = df_events[df_events['Speler']!='Onbekend'].groupby(['Speler', 'Team'])['xT_Generated_Player'].sum().reset_index()
        xt_stats = xt_stats.sort_values('xT_Generated_Player', ascending=False).head(20)
        
        c1, c2 = st.columns([1, 2])
        with c1: st.dataframe(xt_stats, use_container_width=True, hide_index=True)
        with c2:
            fig_bar = px.bar(xt_stats, x='xT_Generated_Player', y='Speler', color='Team', orientation='h',
                             color_discrete_map=team_colors, title="Top 20 xT Spelers")
            fig_bar.update_layout(yaxis={'categoryorder':'total ascending'}, margin=dict(l=150))
            st.plotly_chart(fig_bar, use_container_width=True)
    else:
        st.info("Geen data.")

# --- TAB 5: DATA ---
with tab5:
    cols = ['Volgorde', 'periodId', 'Minuut', 'Team', 'Speler', 'PressingSpeler', 'action', 'result', 'distanceToOpponent', 'pressure', 'phase']
    existing_cols = [c for c in cols if c in df_events.columns]
    st.dataframe(df_events[existing_cols], use_container_width=True)
