
import streamlit as st
import firebase_admin
from firebase_admin import credentials, db

st.title("Green Shelf - Firebase Test")

try:
    DB_URL = st.secrets["firebase"]["database_url"]

    if not firebase_admin._apps:
        service_account_info = dict(
            st.secrets["firebase_service_account"]
        )

        cred = credentials.Certificate(service_account_info)

        firebase_admin.initialize_app(
            cred,
            {"databaseURL": DB_URL}
        )

    sensor_ref = db.reference("sensors")
    data = sensor_ref.get()

    st.success("Firebase connected successfully!")

    if data is not None:
        st.write("Sensor data received:")
        st.json(data)
    else:
        st.warning("Connected, but no sensor data exists at /sensors.")

except Exception as e:
    st.error("Firebase connection failed")
    st.write(str(e))
