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

# Basis Pagina's
pg_home = st.Page(welcome, title="Home", icon="🏠")

# Niveau 1: Scouts
pg_scout = st.Page("views/4_📝_Scouting.py", title="Scout Rapport Maken", icon="📝") 
pg_shortlists = st.Page("views/9_🎯_Shortlists.py", title="Shortlists Aanvullen", icon="🎯")

# Niveau 2: Coaches
pg_match = st.Page("views/3_📊_Wedstrijden.py", title="Wedstrijd Analyse", icon="📊")

# Niveau 3: Management / Admin (Extra pagina's bovenop de rest)
pg_dashboard = st.Page("views/7_📊_Scouting_Overzicht.py", title="Scouting Dashboard", icon="📈")
pg_offer = st.Page("views/6_📥_Aangeboden.py", title="Transfermarkt (Aangeboden)", icon="📥")
pg_disc = st.Page("views/5_🔎_Discover.py", title="Data Discover", icon="🔎")
pg_coach = st.Page("views/2_👔_Coaches.py", title="Coach Profielen", icon="👔")
pg_player = st.Page("views/1_⚽_Spelers_en_Teams.py", title="Diepte Analyse", icon="⚽")
pg_admin = st.Page("views/8_⚙️_Admin.py", title="Admin Beheer", icon="⚙️")

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
    
    # 1. Home is voor iedereen zichtbaar
    pages["Algemeen"] = [pg_home]

    # 2. Logica per Rol
    
    # --- NIVEAU 1: SCOUTS ---
    # "Scout rapporten maken en shortlists aanvullen. Enkel eigen rapporten."
    # (Doordat we Dashboard weglaten, zien ze elkaars rapporten niet)
    if lvl == 1:
        pages["Scouting"] = [pg_scout, pg_shortlists]

    # --- NIVEAU 2: COACHES ---
    # "Enkel wedstrijden.py bekijken"
    elif lvl == 2:
        pages["Performance"] = [pg_match]

    # --- NIVEAU 3: MANAGEMENT / ADMIN ---
    # "Toegang tot alles"
    elif lvl >= 3:
        pages["Scouting & Markt"] = [pg_dashboard, pg_scout, pg_shortlists, pg_offer]
        pages["Data Analyse"] = [pg_match, pg_player, pg_disc, pg_coach]
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
