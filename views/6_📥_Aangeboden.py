import streamlit as st
import pandas as pd
from utils import run_query # We hebben dit nodig om later naar de DB te schrijven

st.set_page_config(page_title="Aangeboden Spelers", page_icon="📥", layout="wide")

st.title("📥 Aangeboden Spelers")

# We gebruiken Tabs voor een nette indeling
tab1, tab2 = st.tabs(["➕ Nieuwe speler toevoegen", "📋 Overzichtlijst"])

with tab1:
    st.header("Nieuwe speler registreren")
    st.info("Hier registreren we spelers die door makelaars zijn aangeboden.")
    
    with st.form("offered_player_form"):
        c1, c2 = st.columns(2)
        with c1:
            naam = st.text_input("Naam Speler")
            leeftijd = st.number_input("Leeftijd", min_value=15, max_value=45, step=1)
            positie = st.selectbox("Positie", ["Doelman", "Verdediger", "Middenvelder", "Aanvaller"])
            club = st.text_input("Huidige Club")
        
        with c2:
            makelaar = st.text_input("Makelaar / Bureau")
            vraagprijs = st.number_input("Vraagprijs (geschat)", min_value=0, step=10000)
            video_link = st.text_input("Link naar Video (Wyscout/YouTube)")
            status = st.selectbox("Status", ["Te bekijken", "Interessant", "Afgekeurd", "Onderhandeling"])
            
        opmerkingen = st.text_area("Korte Opmerking / Profiel")
        
        # De knop om te verzenden
        submitted = st.form_submit_button("💾 Opslaan in Database")
        
        if submitted:
            if naam and makelaar:
                # LATER: Hier komt de SQL INSERT query
                st.success(f"Speler **{naam}** succesvol toegevoegd (Simulatie)!")
                st.balloons()
            else:
                st.error("Vul minstens de naam en makelaar in.")

with tab2:
    st.header("📋 Recente aanbiedingen")
    
    # LATER: Hier halen we data uit de database: SELECT * FROM scouting.offered_players
    # Voor nu maken we even dummy data zodat je het idee ziet
    dummy_data = {
        "Naam": ["Lionel Messi", "Cristiano Ronaldo", "Kevin De Bruyne"],
        "Leeftijd": [36, 39, 32],
        "Club": ["Inter Miami", "Al Nassr", "Man City"],
        "Makelaar": ["Jorge Messi", "Mendes", "Roc Nation"],
        "Status": ["Te duur", "Afgekeurd", "Interessant"]
    }
    df_dummy = pd.DataFrame(dummy_data)
    
    st.dataframe(df_dummy, use_container_width=True)
