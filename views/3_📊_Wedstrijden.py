import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from utils import run_query

st.set_page_config(page_title="Match Events", page_icon="🏟️", layout="wide")

# -----------------------------------------------------------------------------
# HELPER: ID NORMALISATIE & TIJD PARSEN
# -----------------------------------------------------------------------------
def normalize_id(val):
    """Zorgt dat IDs (int, float, str) altijd vergelijkbare strings zijn."""
    try:
        if pd.isna(val) or val == 'nan' or val == 'None':
            return None
        return str(int(float(val)))
    except:
        return str(val).strip()

def parse_gametime_to_min(t_str):
    """
    Zet 'MM:SS.ms' (bv. '53:31.7141') om naar minuten (float).
    Gebruikt pure string parsing, omdat gameTimeInSec onbetrouwbaar bleek.
    """
    try:
        if not isinstance(t_str, str): return 0.0
        # Pak het gedeelte voor de punt (eventuele milliseconden strippen)
        main_part = t_str.split('.')[0] 
        parts = main_part.split(':')
        if len(parts) >= 2:
            # Minuten + Seconden/60
            return float(parts[0]) + float(parts[1])/60.0
        elif len(parts) == 1:
            # Alleen minuten? Of seconden? Gok minuten
            return float(parts[0])
        return 0.0
    except:
        return 0.0

# -----------------------------------------------------------------------------
# 1. SELECTIE (SIDEBAR)
# -----------------------------------------------------------------------------
st.sidebar.header("🔍 Wedstrijd Selectie")

# A. Seizoen & Competitie
try:
    df_seasons = run_query("SELECT DISTINCT season FROM public.iterations ORDER BY season DESC")
    seasons = df_seasons['season'].tolist()
    idx_s = 0
    if "sb_season" in st.session_state and st.session_state.sb_season in seasons:
        idx_s = seasons.index(st.session_state.sb_season)
    sel_season = st.sidebar.selectbox("Seizoen", seasons, index=idx_s, key="sb_season")
except:
    st.error("Geen seizoenen gevonden."); st.stop()

if sel_season:
    df_comps = run_query('SELECT DISTINCT "competitionName" FROM public.iterations WHERE season = %s', (sel_season,))
    comps = df_comps['competitionName'].tolist()
    sel_comp = st.sidebar.selectbox("Competitie", comps)
else: st.stop()

# B. Wedstrijd
if sel_season and sel_comp:
    q_matches = """
        SELECT m.id, m."scheduledDate", h.name as home, a.name as away, 
               m."homeSquadId", m."awaySquadId"
        FROM public.matches m
        JOIN public.squads h ON m."homeSquadId" = h.id
        JOIN public.squads a ON m."awaySquadId" = a.id
        JOIN public.iterations i ON m."iterationId" = i.id
        WHERE i.season = %s AND i."competitionName" = %s
        ORDER BY m."scheduledDate" DESC
    """
    df_matches = run_query(q_matches, (sel_season, sel_comp))
    
    if df_matches.empty:
        st.warning("Geen wedstrijden gevonden.")
        st.stop()
        
    match_opts = {f"{r['home']} - {r['away']} ({r['scheduledDate'].strftime('%d-%m')})": r['id'] for _, r in df_matches.iterrows()}
    sel_match_label = st.sidebar.selectbox("Wedstrijd", list(match_opts.keys()))
    sel_match_id = str(match_opts[sel_match_label])
    match_row = df_matches[df_matches['id'] == sel_match_id].iloc[0]
else:
    st.stop()

st.title(f"🏟️ {match_row['home']} vs {match_row['away']}")
st.caption(f"Datum: {match_row['scheduledDate'].strftime('%d-%m-%Y %H:%M')} | Match ID: {sel_match_id}")

# -----------------------------------------------------------------------------
# 2. DATA OPHALEN
# -----------------------------------------------------------------------------
@st.cache_data
def get_match_data_optimized(match_id):
    # STAP 1: Events
    q_events = """
        SELECT 
            e.index as "Volgorde",
            e."squadId",
            e.action,
            e."actionType",
            e.result,
            (e.player ->> 'id') as player_id_raw,
            
            -- We halen de ruwe tijdstring op (bv. '53:31.7141')
            (e."gameTime" ->> 'gameTime') as "TijdString",
            
            CAST(e."start" -> 'coordinates' ->> 'x' AS FLOAT) as x_start,
            CAST(e."start" -> 'coordinates' ->> 'y' AS FLOAT) as y_start,
            CAST(e."end" -> 'coordinates' ->> 'x' AS FLOAT) as x_end,
            CAST(e."end" -> 'coordinates' ->> 'y' AS FLOAT) as y_end,
            CAST(e."pxT" ->> 'team' AS FLOAT) as "xT"
        FROM public.match_events e
        WHERE e."matchId" = %s 
        ORDER BY e.index ASC
    """
    df_ev = run_query(q_events, (match_id,))
    
    if df_ev.empty:
        return pd.DataFrame()
    
    # Python Tijd Parsing (Veiliger dan SQL gameTimeInSec)
    df_ev['Minuut'] = df_ev['TijdString'].apply(parse_gametime_to_min)

    # STAP 2: Teams
    squad_ids = df_ev['squadId'].dropna().unique().tolist()
    if squad_ids:
        s_ids_formatted = ", ".join(f"'{x}'" for x in squad_ids)
        q_squads = f"SELECT id, name FROM public.squads WHERE id IN ({s_ids_formatted})"
        df_sq = run_query(q_squads)
        if not df_sq.empty:
            squad_map = dict(zip(df_sq['id'].astype(str), df_sq['name']))
            df_ev['Team'] = df_ev['squadId'].astype(str).map(squad_map).fillna('Onbekend')
        else:
            df_ev['Team'] = 'Onbekend'
    else:
        df_ev['Team'] = 'Onbekend'

    # STAP 3: Spelers
    player_ids = df_ev['player_id_raw'].dropna().unique().tolist()
    player_ids = [str(pid) for pid in player_ids if str(pid).isdigit()]
    
    if player_ids:
        p_ids_formatted = ", ".join(f"'{x}'" for x in player_ids)
        q_players = f"SELECT id, commonname FROM public.players WHERE id IN ({p_ids_formatted})"
        df_pl = run_query(q_players)
        
        if not df_pl.empty:
            player_map = dict(zip(df_pl['id'].astype(str), df_pl['commonname']))
            df_ev['Speler'] = df_ev['player_id_raw'].astype(str).map(player_map).fillna('Onbekend')
        else:
            df_ev['Speler'] = 'Onbekend'
    else:
        df_ev['Speler'] = 'Onbekend'

    return df_ev

with st.spinner("Event data analyseren..."):
    df_events = get_match_data_optimized(sel_match_id)

if df_events.empty:
    st.warning(f"⚠️ Geen events gevonden (ID: {sel_match_id}).")
    st.stop()

# -----------------------------------------------------------------------------
# 3. VERWERKING & LOGICA
# -----------------------------------------------------------------------------
# Clean Data
df_events['action_clean'] = df_events['action'].astype(str).str.upper().str.strip()
df_events['result_clean'] = df_events['result'].astype(str).str.upper().str.strip()
df_events['squadId_clean'] = df_events['squadId'].apply(normalize_id)

tab1, tab2, tab3 = st.tabs(["📊 Stats & Tijdlijn", "📍 Pitch Map (Veld)", "📋 Data Lijst"])

with tab1:
    # A. SCOREBORD (Fix: Result 'SUCCESS' alleen voor acties waar dat relevant is, niet voor GOAL/OWN_GOAL want die zijn leeg)
    home_id = normalize_id(match_row['homeSquadId'])
    away_id = normalize_id(match_row['awaySquadId'])

    # Home Goals: Action=GOAL & HomeID  OF  Action=OWN_GOAL & AwayID
    # We checken GEEN resultaat voor goals, omdat dit 'NaN' is in jouw data.
    goals_home = df_events[
        (df_events['squadId_clean'] == home_id) & 
        (df_events['action_clean'] == 'GOAL')
    ]
    own_goals_for_home = df_events[
        (df_events['squadId_clean'] == away_id) & 
        (df_events['action_clean'] == 'OWN_GOAL')
    ]
    score_home = len(goals_home) + len(own_goals_for_home)

    # Away Goals
    goals_away = df_events[
        (df_events['squadId_clean'] == away_id) & 
        (df_events['action_clean'] == 'GOAL')
    ]
    own_goals_for_away = df_events[
        (df_events['squadId_clean'] == home_id) & 
        (df_events['action_clean'] == 'OWN_GOAL')
    ]
    score_away = len(goals_away) + len(own_goals_for_away)

    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown(f"""
            <div style='text-align: center; border: 2px solid #ddd; border-radius:10px; padding:15px; background-color: #f8f9fa; color: #333333; margin-bottom: 20px;'>
                <h1 style='margin:0; font-size: 3em;'>{score_home} - {score_away}</h1>
                <p style='margin:0; font-size: 1.1em; color: #666;'>Eindstand</p>
            </div>
            """, unsafe_allow_html=True)

    # B. STATS & TIJDLIJN
    col_timeline, col_stats = st.columns([3, 2])

    with col_timeline:
        st.subheader("Wedstrijdverloop")
        
        # 1. Goals & Own Goals (Geen result check)
        mask_goals = df_events['action_clean'].isin(['GOAL', 'OWN_GOAL'])
        
        # 2. Kaarten & Wissels
        mask_cards_subs = df_events['action_clean'].isin(['CARD', 'YELLOW_CARD', 'RED_CARD', 'SUBSTITUTION'])
        
        imp_events = df_events[mask_goals | mask_cards_subs].copy()
        
        if not imp_events.empty:
            color_map = {
                "GOAL": "#2ecc71", 
                "OWN_GOAL": "#e74c3c", 
                "CARD": "#f1c40f", 
                "YELLOW_CARD": "#f1c40f", 
                "RED_CARD": "#c0392b",
                "SUBSTITUTION": "#3498db"
            }
            
            fig_tl = px.scatter(
                imp_events, x="Minuut", y="Team", color="action_clean", symbol="action_clean",
                hover_data=["Speler", "TijdString"], size_max=15, 
                color_discrete_map=color_map,
                title="Tijdlijn"
            )
            fig_tl.update_traces(marker=dict(size=14, line=dict(width=1, color='DarkSlateGrey')))
            fig_tl.update_layout(height=400, legend=dict(orientation="h", y=1.1))
            st.plotly_chart(fig_tl, use_container_width=True)
        else:
            st.info("Geen hoogtepunten gevonden.")

    with col_stats:
        st.subheader("Statistieken")
        stats_counts = df_events.groupby(['Team', 'action_clean']).size().reset_index(name='Aantal')
        stats_pivot = stats_counts.pivot(index='action_clean', columns='Team', values='Aantal').fillna(0).astype(int)
        
        if not stats_pivot.empty:
            stats_pivot['Totaal'] = stats_pivot.sum(axis=1)
            stats_pivot = stats_pivot.sort_values('Totaal', ascending=False).drop(columns='Totaal')
        
        st.dataframe(stats_pivot, use_container_width=True)

    # C. EXTRA GRAFIEKEN
    st.divider()
    c_xt1, c_xt2 = st.columns(2)
    with c_xt1:
        st.write("**Expected Threat (xT)**")
        if 'xT' in df_events.columns:
            xt_stats = df_events.groupby('Team')['xT'].sum().reset_index()
            fig_xt = px.bar(xt_stats, x='Team', y='xT', color='Team', color_discrete_sequence=px.colors.qualitative.Pastel)
            st.plotly_chart(fig_xt, use_container_width=True)
    with c_xt2:
        st.write("**Succesvolle Passes**")
        # Hier checken we WEL op SUCCESS, want bij passes is result wel ingevuld
        mask_pass = (df_events['action_clean'].str.contains('PASS')) & (df_events['result_clean'] == 'SUCCESS')
        passes = df_events[mask_pass]
        if not passes.empty:
            p_counts = passes['Team'].value_counts().reset_index()
            p_counts.columns = ['Team', 'Passes']
            fig_pie = px.pie(p_counts, values='Passes', names='Team', hole=0.4, color_discrete_sequence=px.colors.qualitative.Pastel)
            st.plotly_chart(fig_pie, use_container_width=True)

# -----------------------------------------------------------------------------
# 4. PITCH MAP
# -----------------------------------------------------------------------------
with tab2:
    st.subheader("📍 Event Locaties")
    cf1, cf2, cf3 = st.columns(3)
    
    teams = df_events['Team'].dropna().unique().tolist()
    sel_teams = cf1.multiselect("Teams", teams, default=teams)
    
    actions = df_events['action_clean'].unique().tolist()
    defs = [x for x in ['SHOT', 'MID_RANGE_SHOT', 'GOAL', 'LOW_PASS'] if x in actions]
    if not defs: defs = actions[:3] if len(actions)>3 else actions
    sel_actions = cf2.multiselect("Acties", actions, default=defs)
    
    players = df_events['Speler'].dropna().unique().tolist()
    sel_players = cf3.multiselect("Speler (Optioneel)", players)
    
    show_lines = st.checkbox("Toon Pass/Looplijnen", value=False)

    df_m = df_events[(df_events['Team'].isin(sel_teams)) & (df_events['action_clean'].isin(sel_actions))]
    if sel_players: df_m = df_m[df_m['Speler'].isin(sel_players)]
        
    if not df_m.empty:
        fig = go.Figure()
        # Veld (100x100)
        fig.add_shape(type="rect", x0=0, y0=0, x1=100, y1=100, line=dict(color="white"), fillcolor="#4CAF50", layer="below")
        fig.add_shape(type="line", x0=50, y0=0, x1=50, y1=100, line=dict(color="white", width=2))
        fig.add_shape(type="circle", x0=40, y0=40, x1=60, y1=60, line=dict(color="white", width=2))
        fig.add_shape(type="rect", x0=0, y0=20, x1=17, y1=80, line=dict(color="white", width=2))
        fig.add_shape(type="rect", x0=83, y0=20, x1=100, y1=80, line=dict(color="white", width=2))
        
        colors = px.colors.qualitative.Bold
        for i, team in enumerate(sel_teams):
            dft = df_m[df_m['Team'] == team]
            color = colors[i % len(colors)]
            
            fig.add_trace(go.Scatter(
                x=dft['x_start'], y=dft['y_start'], mode='markers', name=team,
                marker=dict(size=8, color=color, line=dict(width=1, color='black')),
                text=dft['Speler'] + " (" + dft['action'] + ")",
                hovertemplate="%{text}<br>Min: %{customdata[0]}", customdata=dft[['Minuut']]
            ))
            
            if show_lines and len(dft) < 1000:
                for _, row in dft.iterrows():
                    if pd.notnull(row['x_end']) and pd.notnull(row['y_end']):
                        fig.add_trace(go.Scatter(
                            x=[row['x_start'], row['x_end']], y=[row['y_start'], row['y_end']],
                            mode='lines', line=dict(color=color, width=1), opacity=0.4, showlegend=False, hoverinfo='skip'
                        ))

        fig.update_layout(width=800, height=650, xaxis=dict(visible=False, range=[-5,105]), yaxis=dict(visible=False, range=[-5,105]), plot_bgcolor='rgba(0,0,0,0)')
        st.plotly_chart(fig, use_container_width=True)
    else: st.info("Geen events.")

# -----------------------------------------------------------------------------
# 5. RAW DATA
# -----------------------------------------------------------------------------
with tab3:
    st.subheader("📋 Ruwe Data")
    cols = ['Volgorde', 'TijdString', 'Team', 'Speler', 'action', 'result', 'xT']
    remaining = [c for c in df_events.columns if c not in cols]
    st.dataframe(df_events[cols + remaining], use_container_width=True)
