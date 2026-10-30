import { initializeApp } from "https://www.gstatic.com/firebasejs/11.6.0/firebase-app.js";
import { getDatabase, onValue, ref } from "https://www.gstatic.com/firebasejs/11.6.0/firebase-database.js";

const firebaseConfig = {
  apiKey: "AIzaSyDOVirxIqW1o9sNyWpvohl-bNrj-saP3RA",
  authDomain: "green-shelf-63225.firebaseapp.com",
  databaseURL: "https://green-shelf-63225-default-rtdb.firebaseio.com",
  projectId: "green-shelf-63225",
  storageBucket: "green-shelf-63225.firebasestorage.app",
  messagingSenderId: "552251202293",
  appId: "1:552251202293:web:2d4230d5ddd799032983bc"
};

const app = initializeApp(firebaseConfig);
const database = getDatabase(app);

const elements = {
  temperature: document.querySelector("#temperature"),
  humidity: document.querySelector("#humidity"),
  gas: document.querySelector("#gas"),
  updated: document.querySelector("#updated"),
  updatedDetail: document.querySelector("#updated-detail"),
  status: document.querySelector("#connection-status"),
  details: document.querySelector("#sensor-details"),
  history: document.querySelector("#history-body"),
  error: document.querySelector("#error-message")
};

function number(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function setConnection(state, message) {
  elements.status.className = `connection ${state}`;
  elements.status.textContent = message;
}

function formatTime(value) {
  if (value === undefined || value === null || value === "") return "—";
  const date = new Date(Number(value) || value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
}

function renderSensorData(data = {}) {
  const temperature = number(data.temperature);
  const humidity = number(data.humidity);
  const rawGas = data.gas_ppm ?? data.mq135_raw;
  const gas = number(rawGas);
  const timestamp = data.timestamp ?? data.updated_at ?? data.time;

  elements.temperature.textContent = temperature.toFixed(1);
  elements.humidity.textContent = humidity.toFixed(0);
  elements.gas.textContent = gas.toFixed(0);
  elements.updated.textContent = timestamp ? formatTime(timestamp) : new Date().toLocaleTimeString();
  elements.updatedDetail.textContent = timestamp ? "Firebase timestamp" : "Received just now";

  elements.details.innerHTML = "";
  const rows = [
    ["Temperature", `${temperature.toFixed(1)} °C`],
    ["Humidity", `${humidity.toFixed(0)} %`],
    ["MQ135 raw reading", number(data.mq135_raw).toFixed(0)],
    ["Gas value", `${gas.toFixed(0)} ppm / reading`],
    ["Sensor timestamp", formatTime(timestamp)]
  ];
  for (const [label, value] of rows) {
    const row = document.createElement("div");
    row.className = "detail-row";
    const labelElement = document.createElement("span");
    labelElement.textContent = label;
    const valueElement = document.createElement("strong");
    valueElement.textContent = value;
    row.append(labelElement, valueElement);
    elements.details.append(row);
  }
}

function historyEntries(data) {
  if (!data) return [];
  const entries = Array.isArray(data)
    ? data.map((value, index) => [index, value])
    : Object.entries(data);
  return entries
    .map(([key, value]) => [key, value || {}])
    .sort((left, right) => number(right[1].timestamp ?? right[1].time ?? right[0]) - number(left[1].timestamp ?? left[1].time ?? left[0]))
    .slice(0, 12);
}

function renderHistory(data) {
  const entries = historyEntries(data);
  if (!entries.length) {
    elements.history.replaceChildren();
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 4;
    cell.className = "empty-state";
    cell.textContent = "No history available.";
    row.append(cell);
    elements.history.append(row);
    return;
  }
  elements.history.replaceChildren();
  for (const [key, value] of entries) {
    const timestamp = value.timestamp ?? value.updated_at ?? value.time ?? key;
    const gas = value.gas_ppm ?? value.mq135_raw;
    const row = document.createElement("tr");
    for (const text of [
      formatTime(timestamp),
      `${number(value.temperature).toFixed(1)} °C`,
      `${number(value.humidity).toFixed(0)} %`,
      number(gas).toFixed(0)
    ]) {
      const cell = document.createElement("td");
      cell.textContent = text;
      row.append(cell);
    }
    elements.history.append(row);
  }
}

function showError(error) {
  console.error(error);
  setConnection("disconnected", "Connection error");
  elements.error.textContent = "Check Firebase Realtime Database rules and configuration.";
}

onValue(ref(database, "sensors"), (snapshot) => {
  renderSensorData(snapshot.val());
  setConnection("connected", "Live · connected");
  elements.error.textContent = "";
}, showError);

onValue(ref(database, "history"), (snapshot) => {
  renderHistory(snapshot.val());
}, showError);
