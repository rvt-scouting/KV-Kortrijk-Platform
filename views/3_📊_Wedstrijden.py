import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from utils import run_query

st.set_page_config(page_title="Match Events", page_icon="🏟️", layout="wide")

# -----------------------------------------------------------------------------
# 1. SELECTIE (SIDEBAR)
# -----------------------------------------------------------------------------
st.sidebar.header("🔍 Wedstrijd Selectie")

# A. Seizoen & Competitie
try:
    df_seasons = run_query("SELECT DISTINCT season FROM public.iterations ORDER BY season DESC")
    seasons = df_seasons['season'].tolist()
    sel_season = st.sidebar.selectbox("Seizoen", seasons)
except:
    st.error("Geen seizoenen gevonden."); st.stop()

if sel_season:
    df_comps = run_query('SELECT DISTINCT "competitionName" FROM public.iterations WHERE season = %s', (sel_season,))
    comps = df_comps['competitionName'].tolist()
    sel_comp = st.sidebar.selectbox("Competitie", comps)
else: st.stop()

# B. Wedstrijd
if sel_season and sel_comp:
    # We halen matches op die 'beschikbaar' zijn
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
    sel_match_id = match_opts[sel_match_label]
    
    # Huidige wedstrijd info
    match_row = df_matches[df_matches['id'] == sel_match_id].iloc[0]
else:
    st.stop()

st.title(f"🏟️ {match_row['home']} vs {match_row['away']}")
st.caption(f"Datum: {match_row['scheduledDate'].strftime('%d-%m-%Y %H:%M')}")

# -----------------------------------------------------------------------------
# 2. DATA OPHALEN (EVENTS)
# -----------------------------------------------------------------------------
# We halen de JSON velden (start, end, gameTime, player) direct uit elkaar in SQL
@st.cache_data
def get_match_events(match_id):
    q = """
        SELECT 
            e.id,
            e."squadId",
            sq.name as "Team",
            e.action,
            e."actionType",
            e.result,
            e.player ->> 'name' as "Speler",
            (e."gameTime" ->> 'minute')::int as "Minuut",
            (e."start" ->> 'x')::float as x_start,
            (e."start" ->> 'y')::float as y_start,
            (e."end" ->> 'x')::float as x_end,
            (e."end" ->> 'y')::float as y_end
        FROM public.match_events e
        LEFT JOIN public.squads sq ON e."squadId" = sq.id
        WHERE e."matchId" = %s
        ORDER BY e.index ASC
    """
    return run_query(q, (match_id,))

with st.spinner("Event data laden..."):
    df_events = get_match_events(sel_match_id)

if df_events.empty:
    st.info("Geen event data beschikbaar voor deze wedstrijd.")
    st.stop()

# -----------------------------------------------------------------------------
# 3. STATS & TIMELINE
# -----------------------------------------------------------------------------
tab1, tab2, tab3 = st.tabs(["📊 Stats & Tijdlijn", "📍 Pitch Map (Veld)", "📋 Data Lijst"])

with tab1:
    # A. Scorebord (Simulatie o.b.v. Goals)
    goals = df_events[df_events['action'].isin(['Goal', 'Own Goal']) & (df_events['result'] == 'Success')] # Aanpassen aan jouw data labels!
    score_home = len(goals[goals['squadId'] == match_row['homeSquadId']])
    score_away = len(goals[goals['squadId'] == match_row['awaySquadId']])
    
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown(f"<h1 style='text-align: center;'>{score_home} - {score_away}</h1>", unsafe_allow_html=True)
    
    # B. Tijdlijn Chart
    st.subheader("Wedstrijdverloop")
    
    # We filteren op belangrijke events
    imp_events = df_events[df_events['action'].isin(['Goal', 'Card', 'Substitution'])].copy()
    if not imp_events.empty:
        fig_tl = px.scatter(
            imp_events, 
            x="Minuut", 
            y="Team", 
            color="action", 
            symbol="action",
            hover_data=["Speler", "actionType"],
            size_max=15,
            title="Tijdlijn Belangrijke Momenten"
        )
        fig_tl.update_traces(marker=dict(size=12))
        fig_tl.update_layout(xaxis=dict(range=[0, 95]), height=300)
        st.plotly_chart(fig_tl, use_container_width=True)
    else:
        st.info("Geen goals of kaarten gevonden in events.")

    # C. Basis Stats
    st.subheader("Team Statistieken")
    # Tel acties per team
    stats = df_events.groupby(['Team', 'action']).size().reset_index(name='Aantal')
    # Pivot voor mooie tabel
    stats_pivot = stats.pivot(index='action', columns='Team', values='Aantal').fillna(0).astype(int)
    st.dataframe(stats_pivot, use_container_width=True)

# -----------------------------------------------------------------------------
# 4. PITCH MAP (VELD ANALYSE)
# -----------------------------------------------------------------------------
with tab2:
    st.subheader("📍 Event Locaties")
    
    c_fil1, c_fil2, c_fil3 = st.columns(3)
    
    # Filters
    teams_list = df_events['Team'].unique().tolist()
    sel_teams_map = c_fil1.multiselect("Selecteer Team(s)", teams_list, default=teams_list)
    
    actions_list = df_events['action'].unique().tolist()
    default_actions = ['Shot', 'Goal'] if 'Shot' in actions_list else actions_list[:3]
    sel_actions_map = c_fil2.multiselect("Type Actie", actions_list, default=default_actions)
    
    players_list = df_events['Speler'].dropna().unique().tolist()
    sel_players_map = c_fil3.multiselect("Specifieke Speler(s) (Optioneel)", players_list)

    # Filter Data
    mask = (df_events['Team'].isin(sel_teams_map)) & (df_events['action'].isin(sel_actions_map))
    if sel_players_map:
        mask = mask & (df_events['Speler'].isin(sel_players_map))
    
    df_map = df_events[mask]
    
    if not df_map.empty:
        # PLOTLY VOETBALVELD (Schematisch)
        fig = go.Figure()

        # 1. Teken het veld (Simpel: Groene Rechthoek + Lijnen)
        # Aanname: x loopt van 0-100, y van 0-100 (Check je data! Soms is het 105x68)
        fig.add_shape(type="rect", x0=0, y0=0, x1=100, y1=100, line=dict(color="white"), fillcolor="green", layer="below")
        fig.add_shape(type="line", x0=50, y0=0, x1=50, y1=100, line=dict(color="white")) # Middenlijn
        fig.add_shape(type="circle", x0=40, y0=40, x1=60, y1=60, line=dict(color="white")) # Middencirkel
        
        # 2. Plot Events
        # We gebruiken verschillende kleuren per Team
        for team in sel_teams_map:
            dft = df_map[df_map['Team'] == team]
            fig.add_trace(go.Scatter(
                x=dft['x_start'],
                y=dft['y_start'],
                mode='markers',
                name=team,
                marker=dict(size=8, line=dict(width=1, color='black')),
                text=dft['Speler'] + " (" + dft['action'] + ")"
            ))

        # Layout settings
        fig.update_layout(
            width=800, height=600,
            xaxis=dict(range=[-5, 105], showgrid=False, visible=False),
            yaxis=dict(range=[-5, 105], showgrid=False, visible=False),
            plot_bgcolor='white',
            title=f"Locaties: {', '.join(sel_actions_map)}"
        )
        
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Geen events gevonden met deze filters.")

# -----------------------------------------------------------------------------
# 5. RAW DATA
# -----------------------------------------------------------------------------
with tab3:
    st.subheader("📋 Ruwe Data")
    st.dataframe(df_events, use_container_width=True)
