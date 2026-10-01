import streamlit as st
import requests

st.title("🌿 Smart Green Shelf - Firebase Test")

# Get Firebase URL
DB_URL = st.secrets["FIREBASE_DB_URL"].rstrip("/")

# Read sensors from Firebase
url = f"{DB_URL}/sensors.json"

response = requests.get(url)

if response.status_code == 200:

    data = response.json()

    st.success("✅ Firebase Connected!")

    st.write("Sensor data received from Firebase:")

    st.json(data)

else:

    st.error("❌ Firebase connection failed")

    st.write(response.text)