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
    st.write("Gebruik het menu links om te navigeren.")

def test_page_func():
    st.title("🛠️ Systeem Info")
    st.write(f"Ingelogd als: {st.session_state.user_info.get('naam')} (Rol: {st.session_state.user_info.get('rol')})")

# Basis
pg_home = st.Page(welcome, title="Home", icon="🏠")
pg_test = st.Page(test_page_func, title="Mijn Profiel", icon="👤")

# Scouting Modules
pg_scout = st.Page("views/4_📝_Scouting.py", title="Scouting Input", icon="📝") 
pg_disc = st.Page("views/5_🔎_Discover.py", title="Discover", icon="🔎")
pg_offer = st.Page("views/6_📥_Aangeboden.py", title="Aangeboden Spelers", icon="📥")
pg_dashboard = st.Page("views/7_📊_Scouting_Overzicht.py", title="Scouting Dashboard", icon="📊")

# Data Modules
pg_match = st.Page("views/3_📊_Wedstrijden.py", title="Wedstrijden Analyse", icon="📊")
pg_coach = st.Page("views/2_👔_Coaches.py", title="Coaches", icon="👔")
pg_player = st.Page("views/1_⚽_Spelers_en_Teams.py", title="Spelers & Teams", icon="⚽")

# Admin Module (NIEUW)
pg_admin = st.Page("views/8_⚙️_Admin.py", title="Admin Panel", icon="⚙️")

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
    
    # GROEP 1: ALGEMEEN
    pages["Algemeen"] = [pg_home, pg_test]

    # GROEP 2: MODULES (Op basis van rechten)
    modules = []
    
    # Level 1: Scouts (Input & Lijsten)
    if lvl >= 1: 
        modules.extend([pg_scout, pg_offer, pg_dashboard, pg_disc])
        
    # Level 2: Coaches/Managers (Data Analyse)
    if lvl >= 2: 
        modules.extend([pg_match, pg_coach])
        
    # Level 3: Directie/Head of Data (Diepe data)
    if lvl >= 3: 
        modules.extend([pg_player])

    if modules:
        pages["Scouting App"] = modules

    # GROEP 3: ADMIN (Alleen Level 3)
    if lvl >= 3:
        pages["Beheer"] = [pg_admin]

    # START DE NAVIGATIE
    with st.sidebar:
        st.title("KV Kortrijk")
        
    pg = st.navigation(pages)
    pg.run()

    with st.sidebar:
        st.divider()
        if st.button("Uitloggen"):
            logout()
