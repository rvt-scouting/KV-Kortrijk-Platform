import streamlit as st
from utils import check_login

# -----------------------------------------------------------------------------
# 1. SETUP
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="KVK Platform", 
    page_icon="🔴", 
    layout="wide",
    initial_sidebar_state="expanded" 
)

# -----------------------------------------------------------------------------
# 2. LOGIN LOGICA
# -----------------------------------------------------------------------------
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_info" not in st.session_state:
    st.session_state.user_info = None

def login_screen():
    st.title("🔴⚪ KVK Login")
    with st.form("login"):
        email = st.text_input("Email")
        pwd = st.text_input("Wachtwoord", type="password")
        if st.form_submit_button("Inloggen"):
            user = check_login(email, pwd)
            if user:
                st.session_state.logged_in = True
                st.session_state.user_info = user
                st.rerun()
            else:
                st.error("Fout: Ongeldige inloggegevens of account inactief.")

def logout():
    st.session_state.logged_in = False
    st.session_state.user_info = None
    st.rerun()

# -----------------------------------------------------------------------------
# 3. PAGINA DEFINITIES
# -----------------------------------------------------------------------------
def welcome():
    st.title(f"Welkom {st.session_state.user_info.get('naam')}")
    st.info(f"Je bent ingelogd als: {st.session_state.user_info.get('rol')} (Niveau {st.session_state.user_info.get('toegangsniveau')})")
    st.write("Gebruik het menu links om te navigeren.")

def test_page_func():
    st.title("👤 Mijn Profiel")
    st.write(f"Naam: {st.session_state.user_info.get('naam')}")
    st.write(f"Rol: {st.session_state.user_info.get('rol')}")
    st.write(f"Email: {st.session_state.user_info.get('email', '-')}")

# Basis Pagina's
pg_home = st.Page(welcome, title="Home", icon="🏠")
pg_profile = st.Page(test_page_func, title="Mijn Profiel", icon="👤")

# HOOFD ANALYSE (GESPLITST)
pg_kvk = st.Page("views/11_🔴_KV_Kortrijk.py", title="KV Kortrijk", icon="🔴")
pg_player_analysis = st.Page("views/1_⚽_Spelers.py", title="Spelers Analyse", icon="⚽")
pg_team_analysis = st.Page("views/10_🛡️_Teams.py", title="Team Analyse", icon="🛡️")

# Scouting Modules
pg_scout = st.Page("views/4_📝_Scouting.py", title="Scout Rapport Maken", icon="📝") 
pg_shortlists = st.Page("views/9_🎯_Shortlists.py", title="Shortlists Aanvullen", icon="🎯")
pg_dashboard = st.Page("views/7_📊_Scouting_Overzicht.py", title="Scouting Dashboard", icon="📈")
pg_offer = st.Page("views/6_📥_Aangeboden.py", title="Transfermarkt (Aangeboden)", icon="📥")
pg_disc = st.Page("views/5_🔎_Discover.py", title="Data Discover", icon="🔎")

# Performance Modules
pg_match = st.Page("views/3_📊_Wedstrijden.py", title="Wedstrijd Analyse", icon="📊")
pg_coach = st.Page("views/2_👔_Coaches.py", title="Coach Profielen", icon="👔")

# Admin & Tools Module
pg_admin = st.Page("views/8_⚙️_Admin.py", title="Admin Beheer", icon="⚙️")
# --- NIEUWE PAGINA ---
pg_import = st.Page("views/import_tool.py", title="Legacy Import Tool", icon="🏗️")

# -----------------------------------------------------------------------------
# 4. NAVIGATIE BOUWER
# -----------------------------------------------------------------------------
if not st.session_state.logged_in:
    login_screen()
else:
    # Haal niveau op (veilig)
    try:
        lvl = int(st.session_state.user_info.get('toegangsniveau', 0))
    except:
        lvl = 0

    # Bouw de dictionary
    pages = {}
    
    # 1. ALGEMEEN (Altijd zichtbaar)
    pages["Algemeen"] = [pg_home, pg_profile]

    # 2. LOGICA PER ROL
    
    # --- NIVEAU 1: SCOUTS ---
    if lvl == 1:
        # Scouts zien direct hun input tools
        pages["Scouting"] = [pg_scout, pg_shortlists]

    # --- NIVEAU 2: COACHES ---
    elif lvl == 2:
        # Coaches zien direct hun wedstrijd analyses
        pages["Performance"] = [pg_match]

    # --- NIVEAU 3: MANAGEMENT / ADMIN ---
    elif lvl >= 3:
        # 1. Hoofd Analyse (De kern)
        pages["🔍 Hoofd Analyse"] = [pg_kvk, pg_player_analysis, pg_team_analysis]
        
        # 2. Scouting & Markt
        pages["Scouting & Markt"] = [pg_dashboard, pg_scout, pg_shortlists, pg_offer, pg_disc]
        
        # 3. Overige Data
        pages["Performance Data"] = [pg_match, pg_coach]
        
        # 4. Beheer (HIER IS DE IMPORT TOOL TOEGEVOEGD)
        pages["Beheer"] = [pg_admin, pg_import]

    # START DE NAVIGATIE
    with st.sidebar:
        st.title("KV Kortrijk")
        
    pg = st.navigation(pages)
    pg.run()

    with st.sidebar:
        st.divider()
        if st.button("Uitloggen"):
            logout()
