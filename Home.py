import streamlit as st

st.set_page_config(page_title="KVK Home", page_icon="🔴", layout="wide")

st.title("🔴⚪ KV Kortrijk Data Platform 2.0")

st.markdown("""
### Welkom bij het nieuwe scouting platform

Gebruik het menu aan de linkerkant om te navigeren:

* **⚽ Spelers en Teams:** De volledige analyse module (Huidige App).
* **👔 Coaches:** Analyse van speelstijlen van coaches (In ontwikkeling).
* **📝 Scouting:** Rapporten invoeren en bekijken (In ontwikkeling).
* **📊 Wedstrijden:** Match analyses (In ontwikkeling).
""")

st.info("👈 Selecteer een module in de zijbalk.")
