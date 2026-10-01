
import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import plotly.graph_objects as go
import requests
import time
import smtplib
from email.mime.text import MIMEText

st.set_page_config(
    page_title="Smart Green Shelf Dashboard",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded",
)





# -----------------------------
# Firebase connection
# -----------------------------
DB_URL = st.secrets["FIREBASE_DB_URL"].rstrip("/")


# -----------------------------
# Email configuration
# -----------------------------
EMAIL_SENDER = st.secrets["EMAIL_SENDER"]
EMAIL_PASSWORD = st.secrets["EMAIL_PASSWORD"]
EMAIL_RECEIVER = st.secrets["EMAIL_RECEIVER"]
EMAIL_INTERVAL_SECONDS = 600  # 10 minutes


def send_email_report(item, temperature, humidity, mq135_raw, gas,
                      freshness, days_left, status, alerts, advice):
    """Send the current Smart Green Shelf report through Gmail SMTP."""
    now = datetime.now()

    if days_left <= 0:
        life_status = "🔴 FOOD LIFE OVER — REMOVE FROM SHELF"
    elif freshness < 25:
        life_status = "🔴 SPOILING"
    elif freshness < 50:
        life_status = "🟠 CONSUME / REMOVE SOON"
    elif freshness < 80:
        life_status = "🟡 MODERATE"
    else:
        life_status = "🟢 FRESH"

    if alerts:
        alert_lines = []
        for level, message in alerts:
            icon = "🚨" if level == "error" else "⚠️"
            alert_lines.append(f"{icon} {message}")
        alerts_text = "\n".join(alert_lines)
    else:
        alerts_text = "✅ No active alerts."

    if days_left <= 0:
        action = (
            "🗑️ ACTION REQUIRED: The estimated food life is over. "
            "Remove the food from the shelf and inspect/dispose of it appropriately."
        )
    elif freshness < 50:
        action = (
            "⚠️ ACTION REQUIRED: Food freshness is low. "
            "Consume soon or remove from the shelf."
        )
    else:
        action = "✅ No immediate removal is indicated by the current estimate."

    subject_prefix = "🚨 ACTION REQUIRED" if days_left <= 0 or freshness < 50 else "🌿 10-Minute Report"

    body = f"""Smart Green Shelf Report
Date: {now.strftime("%d %b %Y")}
Time: {now.strftime("%I:%M:%S %p")}

Food: {item}

CURRENT SENSOR DATA
-------------------
Temperature: {temperature:.1f} °C
Humidity: {humidity:.0f} %
MQ135 raw reading: {mq135_raw:.0f}
Gas value used by model: {gas:.0f}

FRESHNESS
---------
Freshness: {freshness} %
Status: {status}
Estimated remaining life: {days_left} days
Life status: {life_status}

ALERTS
------
{alerts_text}

RECOMMENDATION
--------------
{advice}

ACTION
------
{action}

This report is generated automatically by the Smart Green Shelf dashboard.
Freshness and remaining-life values are prototype estimates and should be
validated/calibrated before being used for food-safety decisions.
"""

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = f"{subject_prefix} - Smart Green Shelf"
    msg["From"] = EMAIL_SENDER
    msg["To"] = EMAIL_RECEIVER

    with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as server:
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        server.sendmail(EMAIL_SENDER, [EMAIL_RECEIVER], msg.as_string())


def maybe_send_email_report(item, temperature, humidity, mq135_raw, gas,
                            freshness, days_left, status, alerts, advice):
    """Send at most one report every 10 minutes for this Streamlit session."""
    now = datetime.now()
    last_sent = st.session_state.get("last_email_sent")

    if last_sent is None or (now - last_sent).total_seconds() >= EMAIL_INTERVAL_SECONDS:
        try:
            send_email_report(
                item, temperature, humidity, mq135_raw, gas,
                freshness, days_left, status, alerts, advice
            )
            st.session_state["last_email_sent"] = now
            st.session_state["email_status"] = (
                f"Last email sent: {now.strftime('%d %b %Y, %I:%M:%S %p')}"
            )
        except Exception as e:
            st.session_state["email_status"] = f"Email error: {e}"



def firebase_get(path):
    url = f"{DB_URL}/{path}.json"

    response = requests.get(
        url,
        timeout=8
    )

    response.raise_for_status()

    return response.json()


# Get latest sensor data from Firebase
def get_live_sensor_data():
    sensor_data = firebase_get("sensors") or {}

    temperature = float(sensor_data.get("temperature", 0))
    humidity = float(sensor_data.get("humidity", 0))
    mq135_raw = float(sensor_data.get("mq135_raw", 0))
    gas = float(sensor_data.get("gas_ppm", mq135_raw))

    return temperature, humidity, mq135_raw, gas



# -----------------------------
# Demo / calculation functions
# -----------------------------
FRUIT_PROFILES = {
    "Tomato": {"base_days": 14, "ideal_temp": (18, 24), "ideal_humidity": (75, 90)},
    "Apple": {"base_days": 30, "ideal_temp": (2, 8), "ideal_humidity": (90, 95)},
    "Banana": {"base_days": 10, "ideal_temp": (13, 18), "ideal_humidity": (85, 95)},
    "Carrot": {"base_days": 21, "ideal_temp": (0, 5), "ideal_humidity": (90, 95)},
    "Potato": {"base_days": 30, "ideal_temp": (7, 10), "ideal_humidity": (85, 95)},
    "Onion": {"base_days": 45, "ideal_temp": (0, 5), "ideal_humidity": (65, 75)},
    "Orange": {"base_days": 21, "ideal_temp": (3, 8), "ideal_humidity": (85, 90)},
}

def calculate_freshness(item, temperature, humidity, gas, days_stored):
    p = FRUIT_PROFILES[item]

    score = 100.0

    tmin, tmax = p["ideal_temp"]
    hmin, hmax = p["ideal_humidity"]

    if temperature < tmin:
        score -= min(15, (tmin - temperature) * 1.2)
    elif temperature > tmax:
        score -= min(30, (temperature - tmax) * 2.0)

    if humidity < hmin:
        score -= min(20, (hmin - humidity) * 0.7)
    elif humidity > hmax:
        score -= min(20, (humidity - hmax) * 0.7)

    # Demo gas-risk score. Replace with calibrated sensor/ML output later.
    gas_excess = max(0, gas - 100)
    score -= min(25, gas_excess / 20)

    score -= min(35, days_stored * (35 / max(p["base_days"], 1)))

    return int(np.clip(round(score), 0, 100))


def remaining_days(item, freshness):
    base = FRUIT_PROFILES[item]["base_days"]
    return max(0, int(round(base * freshness / 100)))


def freshness_status(freshness):
    if freshness >= 80:
        return "Fresh", "🟢"
    if freshness >= 50:
        return "Moderate", "🟡"
    if freshness >= 25:
        return "Ripening", "🟠"
    return "Spoiling", "🔴"


def recommendation(item, temp, humidity, gas, freshness):
    tmin, tmax = FRUIT_PROFILES[item]["ideal_temp"]
    hmin, hmax = FRUIT_PROFILES[item]["ideal_humidity"]

    advice = []

    if temp > tmax:
        advice.append("Temperature is high — cooling is recommended.")
    elif temp < tmin:
        advice.append("Temperature is below the selected storage range.")
    else:
        advice.append("Temperature is within the selected range.")

    if humidity < hmin:
        advice.append("Humidity is low — humidification is recommended.")
    elif humidity > hmax:
        advice.append("Humidity is high — improve ventilation.")
    else:
        advice.append("Humidity is within the selected range.")

    if gas > 180:
        advice.append("Gas level is high — inspect the produce for rapid ripening.")
    elif gas > 130:
        advice.append("Gas level is increasing — monitor freshness closely.")

    if freshness < 50:
        advice.append("Consume or remove this item soon.")

    return " ".join(advice)



# -----------------------------
# CSS
# -----------------------------
st.markdown(
    """
    <style>
    .main {
        background-color: #f5f7f6;
    }
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
    }
    .hero {
        padding: 1.2rem 1.4rem;
        border-radius: 18px;
        background: linear-gradient(135deg, #eaf7ee 0%, #ffffff 60%, #edf8f1 100%);
        border: 1px solid #d7e9dc;
        margin-bottom: 1rem;
    }
    .hero h1 {
        margin: 0;
        color: #174d2b;
        font-size: 2.1rem;
    }
    .hero p {
        margin: 0.3rem 0 0;
        color: #55705d;
    }
    .metric-card {
        padding: 1rem;
        border-radius: 16px;
        background: white;
        border: 1px solid #e1e8e3;
        box-shadow: 0 2px 10px rgba(0,0,0,0.04);
        min-height: 125px;
    }
    .metric-label {
        color: #66736a;
        font-size: 0.9rem;
        margin-bottom: 0.25rem;
    }
    .metric-value {
        font-size: 1.8rem;
        font-weight: 700;
        color: #173b24;
    }
    .small-note {
        color: #718078;
        font-size: 0.78rem;
    }
    .status-box {
        padding: 1rem 1.2rem;
        border-radius: 16px;
        background: white;
        border: 1px solid #e1e8e3;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# -----------------------------
# Sidebar
# -----------------------------
with st.sidebar:

    st.header("Shelf Controls")

    item = st.selectbox(
        "Detected fruit / vegetable",
        list(FRUIT_PROFILES.keys())
    )

    days_stored = st.number_input(
        "Days stored",
        min_value=0,
        max_value=365,
        value=3,
        step=1,
    )





@st.fragment(run_every="5s")
def live_dashboard():
    temperature, humidity, mq135_raw, gas = get_live_sensor_data()

    # -----------------------------
    # Calculations
    # -----------------------------
    freshness = calculate_freshness(item, temperature, humidity, gas, days_stored)
    days_left = remaining_days(item, freshness)
    status, status_icon = freshness_status(freshness)
    advice = recommendation(item, temperature, humidity, gas, freshness)

    tmin, tmax = FRUIT_PROFILES[item]["ideal_temp"]
    hmin, hmax = FRUIT_PROFILES[item]["ideal_humidity"]

    # -----------------------------
    # Header
    # -----------------------------
    st.markdown(
        f"""
        <div class="hero">
            <h1>🌿 Smart Green Shelf</h1>
            <p>AI + IoT dashboard for fruit and vegetable freshness monitoring</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    top1, top2 = st.columns([1.2, 1])

    with top1:
        st.markdown(
            f"""
            <div class="status-box">
                <b>Shelf status</b><br>
                <span style="font-size:1.4rem;">{status_icon} {status}</span>
                <div class="small-note">Last update: {datetime.now().strftime("%d %b %Y, %I:%M:%S %p")}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with top2:
        st.markdown(
            f"""
            <div class="status-box">
                <b>Estimated remaining life</b><br>
                <span style="font-size:1.4rem;">📅 {days_left} days</span>
                <div class="small-note">Estimated from demo freshness model</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.write("")

    # -----------------------------
    # Sensor cards
    # -----------------------------
    c1, c2, c3, c4 = st.columns(4)

    cards = [
        (c1, "🌡️ Temperature", f"{temperature:.1f} °C", f"Ideal: {tmin}–{tmax} °C"),
        (c2, "💧 Humidity", f"{humidity:.0f} %", f"Ideal: {hmin}–{hmax} %"),
        (c3, "🫧 Gas level", f"{gas:.0f}", "MQ135 reading"),
        (c4, "🌱 Freshness", f"{freshness} %", "Estimated freshness score"),
    ]

    for col, label, value, note in cards:
        with col:
            st.markdown(
                f"""
                <div class="metric-card">
                    <div class="metric-label">{label}</div>
                    <div class="metric-value">{value}</div>
                    <div class="small-note">{note}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.write("")

    # -----------------------------
    # Freshness gauge + recommendation
    # -----------------------------
    left, right = st.columns([1, 1.3])

    with left:
        st.subheader("Freshness Score")

        fig = go.Figure(
            go.Indicator(
                mode="gauge+number",
                value=freshness,
                number={"suffix": "%"},
                gauge={
                    "axis": {"range": [0, 100]},
                    "bar": {"thickness": 0.25},
                    "steps": [
                        {"range": [0, 25], "color": "#f7d6d6"},
                        {"range": [25, 50], "color": "#f6e0c8"},
                        {"range": [50, 80], "color": "#f4edc7"},
                        {"range": [80, 100], "color": "#d9f0df"},
                    ],
                },
            )
        )
        fig.update_layout(height=270, margin=dict(l=20, r=20, t=20, b=10))
        st.plotly_chart(fig, use_container_width=True)

    with right:
        st.subheader("🤖 AI / Storage Recommendation")

        st.info(advice)

        st.markdown(
            f"""
            **Freshness classification:** {status_icon} **{status}**

            **Estimated remaining fresh days:** **{days_left} days**

            **Selected storage range:**  
            Temperature: **{tmin}–{tmax} °C**  
            Humidity: **{hmin}–{hmax} %**
            """
        )

    # -----------------------------
    # Live Sensor History
    # -----------------------------
    st.subheader("📈 Live Sensor History")

    try:
        history_data = firebase_get("history") or {}
        history_rows = []

        # Support Firebase history stored as either a dictionary or a list.
        if isinstance(history_data, dict):
            entries = history_data.items()
        elif isinstance(history_data, list):
            entries = enumerate(history_data)
        else:
            entries = []

        for key, value in entries:
            if not isinstance(value, dict):
                continue

            history_rows.append({
                "Key": str(key),
                "Time": value.get("timestamp", value.get("time", "")),
                "Temperature": float(value.get("temperature", 0) or 0),
                "Humidity": float(value.get("humidity", 0) or 0),
                "Gas": float(value.get("gas_ppm", value.get("mq135_raw", 0)) or 0),
            })

        history = pd.DataFrame(history_rows)

        if history.empty:
            st.info("No historical sensor data available yet. Make sure the ESP32 is writing data to Firebase/history.")
        else:
            # Always keep the Firebase insertion order as a safe fallback.
            history["Reading No."] = range(1, len(history) + 1)

            # Use timestamp only when Firebase actually provides valid timestamps.
            history["Parsed Time"] = pd.to_datetime(history["Time"], errors="coerce")
            has_time = history["Parsed Time"].notna().any()

            if has_time:
                history = history.sort_values("Parsed Time", na_position="last").tail(100)
                x_values = history["Parsed Time"]
                x_title = "Time"
            else:
                history = history.tail(100)
                x_values = history["Reading No."]
                x_title = "Reading"

            tab1, tab2, tab3 = st.tabs(["🌡 Temperature", "💧 Humidity", "🫧 Gas Level"])

            with tab1:
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=x_values, y=history["Temperature"],
                    mode="lines+markers", name="Temperature",
                    connectgaps=True
                ))
                fig.update_layout(
                    height=320,
                    yaxis_title="Temperature (°C)",
                    xaxis_title=x_title,
                    hovermode="x unified",
                    margin=dict(l=20, r=20, t=20, b=20)
                )
                st.plotly_chart(fig, use_container_width=True, key="temperature_history_chart")

            with tab2:
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=x_values, y=history["Humidity"],
                    mode="lines+markers", name="Humidity",
                    connectgaps=True
                ))
                fig.update_layout(
                    height=320,
                    yaxis_title="Humidity (%)",
                    xaxis_title=x_title,
                    hovermode="x unified",
                    margin=dict(l=20, r=20, t=20, b=20)
                )
                st.plotly_chart(fig, use_container_width=True, key="humidity_history_chart")

            with tab3:
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=x_values, y=history["Gas"],
                    mode="lines+markers", name="MQ135",
                    connectgaps=True
                ))
                fig.update_layout(
                    height=320,
                    yaxis_title="MQ135 Reading",
                    xaxis_title=x_title,
                    hovermode="x unified",
                    margin=dict(l=20, r=20, t=20, b=20)
                )
                st.plotly_chart(fig, use_container_width=True, key="gas_history_chart")

    except Exception as e:
        st.error(f"Unable to read Firebase history: {e}")

    # -----------------------------
    # Alerts
    # -----------------------------
    st.subheader("🔔 Alerts")

    alerts = []

    if temperature > tmax:
        alerts.append(("warning", f"Temperature is above the recommended range for {item}."))
    elif temperature < tmin:
        alerts.append(("warning", f"Temperature is below the recommended range for {item}."))

    if humidity > hmax:
        alerts.append(("warning", "Humidity is above the selected storage range."))
    elif humidity < hmin:
        alerts.append(("warning", "Humidity is below the selected storage range."))

    if gas > 180:
        alerts.append(("error", "High gas level detected. Inspect the produce for rapid ripening/spoilage."))
    elif gas > 130:
        alerts.append(("warning", "Gas level is elevated. Continue monitoring."))

    if freshness < 50:
        alerts.append(("error", f"Freshness has dropped to {freshness}%. Consume or remove the item soon."))

    if days_left <= 0:
        alerts.append(("error", f"Estimated food life for {item} is over. Remove the food from the shelf."))

    if not alerts:
        st.success("✅ All monitored parameters are currently within the selected safe range.")
    else:
        for level, message in alerts:
            if level == "error":
                st.error(message)
            else:
                st.warning(message)

    # -----------------------------
    # Automatic email report
    # -----------------------------
    maybe_send_email_report(
        item,
        temperature,
        humidity,
        mq135_raw,
        gas,
        freshness,
        days_left,
        status,
        alerts,
        advice,
    )

    email_status = st.session_state.get("email_status")
    if email_status:
        st.caption(f"📧 {email_status}")

    # -----------------------------
    # Data table + footer
    # -----------------------------
    with st.expander("📋 Latest sensor data"):
        current = pd.DataFrame(
            {
                "Parameter": [
                    "Fruit / Vegetable",
                    "Temperature",
                    "Humidity",
                    "Gas Level",
                    "Freshness",
                    "Remaining Days",
                    "Status",
                ],
                "Value": [
                    item,
                    f"{temperature:.1f} °C",
                    f"{humidity:.0f} %",
                    f"{gas:.0f}",
                    f"{freshness} %",
                    f"{days_left} days",
                    status,
                ],
            }
        )
        st.dataframe(current, use_container_width=True, hide_index=True)

    st.caption(
        "Prototype dashboard for the Smart Green Shelf project. "
        "The freshness and remaining-days values are demonstration estimates until "
        "calibrated sensor data and a validated AI model are connected."
    )


live_dashboard()
