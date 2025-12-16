import streamlit as st
import pandas as pd
import plotly.express as px
from utils import run_query

st.set_page_config(page_title="Scouting Dashboard", page_icon="📊", layout="wide")

# -----------------------------------------------------------------------------
# 0. AUTHENTICATIE & LEVEL CHECK
# -----------------------------------------------------------------------------
if 'user_info' not in st.session_state or not st.session_state.user_info:
    st.warning("⚠️ Log in AUB."); st.stop()

current_user_id = st.session_state.user_info.get('id')
try:
    lvl = int(st.session_state.user_info.get('toegangsniveau', 0))
except:
    lvl = 0

st.title("📊 Scouting Dashboard")

# -----------------------------------------------------------------------------
# 1. FILTERS (SIDEBAR)
# -----------------------------------------------------------------------------
st.sidebar.header("🔍 Filters Rapporten")

# Filter: Datum
date_range = st.sidebar.date_input("Datum Periode", [])

# Filter: Scouts (ALLEEN VOOR LEVEL 2+)
selected_scouts = []
if lvl > 1:
    try:
        df_scouts = run_query("SELECT id, naam FROM scouting.gebruikers WHERE rol != 'Admin' ORDER BY naam")
        if not df_scouts.empty:
            scout_opts = df_scouts['naam'].tolist()
            selected_scouts = st.sidebar.multiselect("Selecteer Scout(s)", scout_opts, default=scout_opts)
    except: pass
else:
    st.sidebar.info(f"👤 Je ziet alleen je eigen rapporten.")

# Filter: Advies
try:
    df_advies = run_query("SELECT DISTINCT advies FROM scouting.rapporten WHERE advies IS NOT NULL ORDER BY advies")
    if not df_advies.empty:
        advies_opts = df_advies['advies'].tolist()
        selected_advies = st.sidebar.multiselect("Filter op Advies", advies_opts)
    else:
        selected_advies = []
except:
    selected_advies = []

# Filter: Rating & Gouden Buzzer
min_rating = st.sidebar.slider("Minimale Beoordeling", 1, 10, 1)
show_only_gold = st.sidebar.checkbox("🏆 Toon enkel Gouden Buzzers")

# -----------------------------------------------------------------------------
# 2. TABS
# -----------------------------------------------------------------------------
tab1, tab2, tab3, tab4 = st.tabs([
    "📝 Alle Match Rapporten", 
    "⭐ Shortlists", 
    "📥 Aangeboden Spelers (Markt)",
    "📈 Scout Statistieken"
])

# =============================================================================
# TAB 1: ALLE MATCH RAPPORTEN (MET LEES MODUS)
# =============================================================================
with tab1:
    col_head, col_btn = st.columns([6, 1])
    with col_head:
        st.header("Alle Scouting Rapporten")
    with col_btn:
        if st.button("🔄 Ververs Data", type="primary"):
            st.cache_data.clear()
            st.rerun()
    
    # We halen ook r.scout_id op om te kunnen filteren op ID
    query = """
        SELECT 
            r.id,
            r.scout_id, 
            r.aangemaakt_op as "Datum",
            s.naam as "Scout",
            COALESCE(p.commonname, r.custom_speler_naam, 'Onbekend') as "Speler",
            COALESCE(CONCAT(sq_h.name, ' vs ', sq_a.name), r.custom_wedstrijd_naam, 'Onbekend') as "Wedstrijd",
            r.positie_gespeeld as "Positie",
            r.beoordeling as "Rating",
            r.advies as "Advies",
            r.gouden_buzzer as "Gold",
            r.rapport_tekst as "Rapport"
        FROM scouting.rapporten r
        LEFT JOIN scouting.gebruikers s ON r.scout_id = s.id
        LEFT JOIN public.players p ON r.speler_id = p.id
        LEFT JOIN public.matches m ON r.wedstrijd_id = m.id
        LEFT JOIN public.squads sq_h ON m."homeSquadId" = sq_h.id
        LEFT JOIN public.squads sq_a ON m."awaySquadId" = sq_a.id
        ORDER BY r.aangemaakt_op DESC
    """
    
    try:
        df_reports = run_query(query)
        
        if not df_reports.empty:
            # --- FILTERS ---
            
            # LOGICA LEVEL 1: Filter hard op eigen ID
            if lvl == 1:
                df_reports = df_reports[df_reports['scout_id'] == current_user_id]
            # LOGICA LEVEL 2+: Gebruik de sidebar filter
            elif selected_scouts:
                df_reports = df_reports[df_reports['Scout'].isin(selected_scouts)]

            if selected_advies:
                df_reports = df_reports[df_reports['Advies'].isin(selected_advies)]
            
            df_reports = df_reports[df_reports['Rating'] >= min_rating]
            
            if show_only_gold:
                df_reports = df_reports[df_reports['Gold'] == True]
            
            if len(date_range) == 2:
                start_date, end_date = date_range
                df_reports['Datum'] = pd.to_datetime(df_reports['Datum'])
                df_reports = df_reports[
                    (df_reports['Datum'].dt.date >= start_date) & 
                    (df_reports['Datum'].dt.date <= end_date)
                ]

            # Styling functie
            def color_advice(val):
                val_str = str(val).lower().strip()
                if val_str in ['sign', 'future sign', 'a', 'a+']:
                    return 'color: #2ecc71; font-weight: bold'
                return ''
            
            if not df_reports.empty:
                st.info("💡 **Tip:** Klik op een rij in de tabel om het volledige rapport te lezen!")

                # --- INTERACTIEVE TABEL ---
                event = st.dataframe(
                    df_reports.style.applymap(color_advice, subset=['Advies']),
                    use_container_width=True,
                    hide_index=True,
                    on_select="rerun",          
                    selection_mode="single-row", 
                    column_config={
                        "id": None, 
                        "scout_id": None, # Verberg ID kolom
                        "Datum": st.column_config.DatetimeColumn(format="DD-MM-YYYY"),
                        "Rating": st.column_config.NumberColumn(format="%d/10"),
                        "Gold": st.column_config.CheckboxColumn("🏆"),
                        "Rapport": st.column_config.TextColumn("Tekst", width="medium"), 
                    }
                )
                
                # --- DETAIL WEERGAVE ---
                if len(event.selection.rows) > 0:
                    selected_idx = event.selection.rows[0]
                    row = df_reports.iloc[selected_idx]
                    
                    st.divider()
                    st.subheader(f"📄 Rapport Details: {row['Speler']}")
                    
                    with st.container(border=True):
                        c1, c2, c3, c4 = st.columns(4)
                        c1.markdown(f"**Scout:** {row['Scout']}")
                        c2.markdown(f"**Wedstrijd:** {row['Wedstrijd']}")
                        c3.markdown(f"**Beoordeling:** {row['Rating']}/10 {'🏆' if row['Gold'] else ''}")
                        
                        advies_color = "green" if str(row['Advies']).lower() in ['sign', 'a', 'future sign'] else "orange"
                        c4.markdown(f"**Advies:** :{advies_color}[{row['Advies']}]")
                        
                        st.divider()
                        st.markdown("#### 📝 Analyse")
                        st.markdown(row['Rapport'] if row['Rapport'] else "*Geen tekst ingevoerd.*")
                        st.caption(f"Positie: {row['Positie']} | Datum rapport: {row['Datum']}")
            else:
                st.info("Geen rapporten gevonden voor jou.")

        else:
            st.info("Nog geen rapporten in de database.")
            
    except Exception as e:
        st.error(f"Fout bij laden rapporten: {e}")

# =============================================================================
# TAB 2: SHORTLISTS
# =============================================================================
with tab2:
    st.header("🎯 Shortlists")
    try:
        # LOGICA LEVEL 1: Alleen eigen shortlists zien
        base_query = "SELECT id, naam FROM scouting.shortlists"
        if lvl == 1:
            q_opt = base_query + " WHERE eigenaar_id = %s ORDER BY id"
            sl_opts = run_query(q_opt, params=(current_user_id,))
        else:
            q_opt = base_query + " ORDER BY id"
            sl_opts = run_query(q_opt)

        if not sl_opts.empty:
            sl_tabs = st.tabs(sl_opts['naam'].tolist())
            for i, row in sl_opts.iterrows():
                sl_id = row['id']
                with sl_tabs[i]:
                    q_sl = """
                        SELECT DISTINCT ON (r.speler_id, r.custom_speler_naam)
                            COALESCE(p.commonname, r.custom_speler_naam) as "Speler",
                            r.positie_gespeeld as "Positie",
                            r.beoordeling as "Rating",
                            r.advies as "Advies",
                            r.rapport_tekst as "Laatste Info",
                            s.naam as "Scout",
                            r.aangemaakt_op as "Datum"
                        FROM scouting.rapporten r
                        LEFT JOIN public.players p ON r.speler_id = p.id
                        LEFT JOIN scouting.gebruikers s ON r.scout_id = s.id
                        WHERE r.shortlist_id = %s
                        ORDER BY r.speler_id, r.custom_speler_naam, r.aangemaakt_op DESC
                    """
                    df_sl = run_query(q_sl, params=(sl_id,))
                    if not df_sl.empty:
                        def color_advice_simple(val):
                            val_str = str(val).lower().strip()
                            if val_str in ['sign', 'future sign', 'a']: return 'color: #2ecc71; font-weight: bold'
                            return ''
                        st.dataframe(df_sl.style.applymap(color_advice_simple, subset=['Advies']), use_container_width=True, hide_index=True)
                    else: st.info(f"Nog geen rapporten.")
        else: st.warning("Geen shortlists gevonden.")
    except Exception as e: st.error(f"Fout shortlists: {e}")

# =============================================================================
# TAB 3: AANGEBODEN SPELERS (MARKT) - ALLEEN ZICHTBAAR VOOR NIV 2+?
# =============================================================================
# Je kan ervoor kiezen dit te verbergen voor Level 1, of laten staan.
# Ik laat het staan, maar je kan `if lvl > 1:` toevoegen als ze dit niet mogen zien.
with tab3:
    st.header("📥 Aangeboden Spelers")
    status_filter = st.multiselect("Filter op Status", ["Interessant", "Te bekijken", "Onderhandeling", "In de gaten houden", "Afgekeurd"], default=["Interessant", "Te bekijken", "Onderhandeling"])
    if status_filter:
        q_market = f"""
            SELECT p.commonname as "Naam", sq.name as "Huidig Team", EXTRACT(YEAR FROM AGE(p.birthdate)) as "Leeftijd",
            o.status as "Status", o.vraagprijs as "Prijs (€)", o.makelaar as "Makelaar", o.opmerkingen as "Scoutingsverslag",
            o.video_link as "Video", o.tmlink as "TM"
            FROM scouting.offered_players o JOIN public.players p ON o.player_id = p.id
            LEFT JOIN public.squads sq ON p."currentSquadId" = sq.id
            WHERE o.status IN ({','.join([f"'{s}'" for s in status_filter])}) ORDER BY o.aangeboden_datum DESC
        """
        try:
            df_market = run_query(q_market)
            if not df_market.empty:
                def color_status(val):
                    color = 'black'
                    if val == 'Interessant': color = '#27ae60' 
                    elif val == 'Afgekeurd': color = '#c0392b' 
                    elif val == 'Onderhandeling': color = '#f39c12' 
                    return f'color: {color}; font-weight: bold'
                st.dataframe(
                    df_market.style.applymap(color_status, subset=['Status']), use_container_width=True, hide_index=True,
                    column_config={"Prijs (€)": st.column_config.NumberColumn(format="€ %.2f"), "Video": st.column_config.LinkColumn("📺"), "TM": st.column_config.LinkColumn("TM"), "Scoutingsverslag": st.column_config.TextColumn(width="large")}
                )
            else: st.info("Geen spelers gevonden.")
        except Exception as e: st.error(f"Fout markt: {e}")
    else: st.warning("Selecteer status.")

# =============================================================================
# TAB 4: SCOUT STATISTIEKEN (ALLEEN NIV 2+)
# =============================================================================
with tab4:
    st.header("📈 Activiteit Scouts")
    
    if lvl > 1:
        c1, c2 = st.columns(2)
        with c1:
            df_stats = run_query("SELECT s.naam as \"Scout\", COUNT(r.id) as \"Aantal Rapporten\" FROM scouting.rapporten r JOIN scouting.gebruikers s ON r.scout_id = s.id GROUP BY s.naam ORDER BY \"Aantal Rapporten\" DESC")
            if not df_stats.empty: st.plotly_chart(px.bar(df_stats, x="Scout", y="Aantal Rapporten", title="Rapporten per Scout", color="Aantal Rapporten", color_continuous_scale="Reds"), use_container_width=True)
        with c2:
            df_adv = run_query("SELECT advies, COUNT(id) as \"Aantal\" FROM scouting.rapporten GROUP BY advies")
            if not df_adv.empty: st.plotly_chart(px.pie(df_adv, values="Aantal", names="advies", title="Verdeling Adviezen", hole=0.4, color_discrete_sequence=px.colors.sequential.RdBu), use_container_width=True)

        st.markdown("---"); st.subheader("Laatste 10 Activiteiten")
        df_log = run_query("SELECT r.aangemaakt_op, s.naam, COALESCE(p.commonname, r.custom_speler_naam) as speler, r.beoordeling FROM scouting.rapporten r JOIN scouting.gebruikers s ON r.scout_id = s.id LEFT JOIN public.players p ON r.speler_id = p.id ORDER BY r.aangemaakt_op DESC LIMIT 10")
        if not df_log.empty:
            for _, row in df_log.iterrows(): st.text(f"{row['aangemaakt_op'].strftime('%d-%m %H:%M')} - {row['naam']} scoutte {row['speler']} (Rating: {row['beoordeling']})")
    else:
        st.info("Statistieken zijn alleen zichtbaar voor management.")
