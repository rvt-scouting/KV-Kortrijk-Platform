import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from utils import run_query

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
except: st.error("Geen seizoenen gevonden."); st.stop()

if sel_season:
    df_comps = run_query('SELECT DISTINCT "competitionName" FROM public.iterations WHERE season = %s', (sel_season,))
    comps = df_comps['competitionName'].tolist()
    sel_comp = st.sidebar.selectbox("Competitie", comps)
else: st.stop()

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
    if df_matches.empty: st.warning("Geen wedstrijden."); st.stop()
        
    match_opts = {f"{r['home']} - {r['away']} ({r['scheduledDate'].strftime('%d-%m')})": r['id'] for _, r in df_matches.iterrows()}
    sel_match_label = st.sidebar.selectbox("Wedstrijd", list(match_opts.keys()))
    sel_match_id = str(match_opts[sel_match_label])
    match_row = df_matches[df_matches['id'] == sel_match_id].iloc[0]
else: st.stop()

st.title(f"🏟️ {match_row['home']} vs {match_row['away']}")
st.caption(f"Datum: {match_row['scheduledDate'].strftime('%d-%m-%Y %H:%M')}")

# -----------------------------------------------------------------------------
# 2. DATA OPHALEN
# -----------------------------------------------------------------------------
@st.cache_data
def get_match_data_optimized(match_id):
    q_events = """
        SELECT 
            e.index as "Volgorde",
            e."squadId", e.action, e."actionType", e.result,
            (e.player ->> 'id') as player_id_raw,
            (e."gameTime" ->> 'gameTime') as "TijdString",
            
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
        df_sq = run_query(f"SELECT id, name FROM public.squads WHERE id IN ({s_ids_formatted})")
        if not df_sq.empty: squad_map = dict(zip(df_sq['id'].astype(str), df_sq['name']))
    df_ev['Team'] = df_ev['squadId'].astype(str).map(squad_map).fillna('Onbekend')

    # Spelers Map
    player_ids = [str(pid) for pid in df_ev['player_id_raw'].dropna().unique().tolist() if str(pid).isdigit()]
    player_map = {}
    if player_ids:
        p_ids_formatted = ", ".join(f"'{x}'" for x in player_ids)
        df_pl = run_query(f"SELECT id, commonname FROM public.players WHERE id IN ({p_ids_formatted})")
        if not df_pl.empty: player_map = dict(zip(df_pl['id'].astype(str), df_pl['commonname']))
    df_ev['Speler'] = df_ev['player_id_raw'].astype(str).map(player_map).fillna('Onbekend')

    return df_ev

with st.spinner("Bezig met analyseren..."):
    df_events = get_match_data_optimized(sel_match_id)

if df_events.empty: st.warning("Geen data."); st.stop()

# -----------------------------------------------------------------------------
# 3. GEAVANCEERDE xT BEREKENING (DELTA)
# -----------------------------------------------------------------------------
df_events['action_clean'] = df_events['action'].astype(str).str.upper().str.strip()
df_events['result_clean'] = df_events['result'].astype(str).str.upper().str.strip()
home_id_str = normalize_id(match_row['homeSquadId'])
df_events['squadId_clean'] = df_events['squadId'].apply(normalize_id)

df_events['xT_Team_Raw'] = df_events['xT_Team_Raw'].fillna(0)
df_events['xT_Opp_Raw'] = df_events['xT_Opp_Raw'].fillna(0)

def calc_home_threat(row):
    if row['squadId_clean'] == home_id_str:
        return row['xT_Team_Raw'] - row['xT_Opp_Raw']
    else:
        return row['xT_Opp_Raw'] - row['xT_Team_Raw']

df_events['Home_Net_Threat_State'] = df_events.apply(calc_home_threat, axis=1)
df_events['xT_Generated_Raw'] = df_events['Home_Net_Threat_State'].shift(-1) - df_events['Home_Net_Threat_State']

def calc_player_xt(row):
    if pd.isna(row['xT_Generated_Raw']): return 0.0
    if row['squadId_clean'] == home_id_str:
        return row['xT_Generated_Raw']
    else:
        return -row['xT_Generated_Raw']

df_events['xT_Generated_Player'] = df_events.apply(calc_player_xt, axis=1)

# BASIS KLEUREN TEAM
team_colors = {match_row['home']: '#e74c3c', match_row['away']: '#3498db', 'Onbekend': '#95a5a6'} 

# -----------------------------------------------------------------------------
# 4. DASHBOARD
# -----------------------------------------------------------------------------
tab1, tab2, tab3, tab4 = st.tabs(["📊 Stats & Tijdlijn", "📍 Pitch Map", "🏃 Spelers xT (Top)", "📋 Data"])

with tab1:
    # --- SCOREBORD ---
    goals_home = df_events[(df_events['squadId_clean'] == home_id_str) & (df_events['action_clean'] == 'GOAL')]
    own_goals_home_benefit = df_events[(df_events['squadId_clean'] != home_id_str) & (df_events['action_clean'] == 'OWN_GOAL')]
    score_home = len(goals_home) + len(own_goals_home_benefit)

    goals_away = df_events[(df_events['squadId_clean'] != home_id_str) & (df_events['action_clean'] == 'GOAL')]
    own_goals_away_benefit = df_events[(df_events['squadId_clean'] == home_id_str) & (df_events['action_clean'] == 'OWN_GOAL')]
    score_away = len(goals_away) + len(own_goals_away_benefit)

    st.markdown(f"<h1 style='text-align: center; color: #333;'>{match_row['home']} {score_home} - {score_away} {match_row['away']}</h1>", unsafe_allow_html=True)

    # --- TIJDLIJN (Met kleuren) ---
    col_tl, col_st = st.columns([3, 2])
    with col_tl:
        st.subheader("Wedstrijdverloop")
        mask_hl = df_events['action_clean'].isin(['GOAL', 'OWN_GOAL', 'CARD', 'YELLOW_CARD', 'RED_CARD', 'SUBSTITUTION'])
        imp = df_events[mask_hl].copy()
        
        if not imp.empty:
            # Event kleuren
            event_colors = {
                "GOAL": "#2ecc71", "OWN_GOAL": "#e74c3c", 
                "CARD": "#f1c40f", "YELLOW_CARD": "#f1c40f", "RED_CARD": "#c0392b",
                "SUBSTITUTION": "#3498db"
            }
            
            fig_tl = px.scatter(imp, x="Minuut", y="Team", color="action_clean", symbol="action_clean",
                                color_discrete_map=event_colors, size_max=15, hover_data=["Speler"])
            fig_tl.update_traces(marker=dict(size=14, line=dict(width=1, color='DarkSlateGrey')))
            fig_tl.update_layout(height=350, showlegend=True) # Legende weer aan zodat je ziet wat de kleuren betekenen
            st.plotly_chart(fig_tl, use_container_width=True)
        else: st.info("Geen hoogtepunten.")

    with col_st:
        st.subheader("Team Stats")
        stats = df_events.groupby(['Team', 'action_clean']).size().reset_index(name='Cnt')
        piv = stats.pivot(index='action_clean', columns='Team', values='Cnt').fillna(0).astype(int)
        piv['Total'] = piv.sum(axis=1)
        st.dataframe(piv.sort_values('Total', ascending=False).drop(columns='Total'), use_container_width=True)

    # --- xT TOTAAL & PASSES ---
    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        st.write("**Total Expected Threat (xT) per Team**")
        # Som van raw xT_Team per team (Creatie van gevaar)
        xt_total = df_events.groupby('Team')['xT_Team_Raw'].sum().reset_index()
        
        fig_xt = px.bar(xt_total, x='Team', y='xT_Team_Raw', color='Team', 
                        color_discrete_map=team_colors, title="Totaal xT (Gevaar gecreëerd)")
        st.plotly_chart(fig_xt, use_container_width=True)

    with c2:
        st.write("**Pass Types**")
        passes = df_events[df_events['action_clean'].str.contains('PASS')].copy()
        if not passes.empty:
            pass_agg = passes.groupby(['Team', 'action_clean']).size().reset_index(name='Aantal')
            fig_pass = px.bar(pass_agg, x='action_clean', y='Aantal', color='Team', barmode='group',
                              color_discrete_map=team_colors)
            st.plotly_chart(fig_pass, use_container_width=True)

# -----------------------------------------------------------------------------
# TAB 2: PITCH MAP
# -----------------------------------------------------------------------------
with tab2:
    st.subheader("📍 Event Map")
    c1, c2, c3 = st.columns(3)
    teams = df_events['Team'].unique(); sel_teams = c1.multiselect("Teams", teams, default=teams)
    acts = df_events['action_clean'].unique(); sel_acts = c2.multiselect("Acties", acts, default=[x for x in ['SHOT','GOAL'] if x in acts])
    plys = df_events['Speler'].unique(); sel_plys = c3.multiselect("Speler", plys)
    
    df_m = df_events[(df_events['Team'].isin(sel_teams)) & (df_events['action_clean'].isin(sel_acts))]
    if sel_plys: df_m = df_m[df_m['Speler'].isin(sel_plys)]
    
    if not df_m.empty:
        fig = go.Figure()
        fig.add_shape(type="rect", x0=0, y0=0, x1=100, y1=100, line=dict(color="white"), fillcolor="#4CAF50", layer="below")
        fig.add_shape(type="line", x0=50, y0=0, x1=50, y1=100, line=dict(color="white"))
        
        for t in sel_teams:
            d = df_m[df_m['Team']==t]
            fig.add_trace(go.Scatter(x=d['x_start'], y=d['y_start'], mode='markers', name=t,
                                     marker=dict(color=team_colors.get(t,'grey'), size=8, line=dict(width=1,color='black')),
                                     text=d['Speler']+" ("+d['action']+")"))
        fig.update_layout(width=800, height=600, xaxis=dict(visible=False, range=[-5,105]), yaxis=dict(visible=False, range=[-5,105]))
        st.plotly_chart(fig, use_container_width=True)

# -----------------------------------------------------------------------------
# TAB 3: SPELERS xT (NIEUW)
# -----------------------------------------------------------------------------
with tab3:
    st.subheader("🏆 Top xT Generators")
    st.caption("Som van xT verschil (Delta) per speler. Positief = Speler heeft situaties gevaarlijker gemaakt.")
    
    xt_stats = df_events[df_events['Speler']!='Onbekend'].groupby(['Speler', 'Team'])['xT_Generated_Player'].sum().reset_index()
    xt_stats = xt_stats.sort_values('xT_Generated_Player', ascending=False).head(20)
    
    c1, c2 = st.columns([1, 2])
    with c1: st.dataframe(xt_stats, use_container_width=True, hide_index=True)
    with c2:
        fig_bar = px.bar(xt_stats, x='xT_Generated_Player', y='Speler', color='Team', orientation='h',
                         color_discrete_map=team_colors, title="Top 20 xT Spelers")
        # MARGE FIX: Meer ruimte links voor namen
        fig_bar.update_layout(
            yaxis={'categoryorder':'total ascending'},
            margin=dict(l=150) 
        )
        st.plotly_chart(fig_bar, use_container_width=True)

# -----------------------------------------------------------------------------
# TAB 4: RAW
# -----------------------------------------------------------------------------
with tab4:
    cols = ['Volgorde', 'Minuut', 'Team', 'Speler', 'action', 'xT_Generated_Player', 'Home_Net_Threat_State']
    st.dataframe(df_events[cols], use_container_width=True)
