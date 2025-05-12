/**
 * unknownPgnsView.js - Handles the Unknown PGNs view logic for the rvc2api Web UI
 *
 * Responsibilities:
 * - Fetching and rendering unknown Parameter Group Numbers (PGNs)
 * - Providing detailed table and card views for each PGN, with as much data as possible
 * - UI feedback (toasts, error messages)
 * - Toggle between table and card view
 *
 * Author: Ryan Holt
 * Last updated: 2025-05-12
 */

import { fetchData } from "../api.js";
import { showToast } from "../utils.js";
import { apiBasePath } from "../config.js";

const unknownPgnsView = document.getElementById("unknown-pgns-view");
const unknownPgnsContent = document.getElementById("unknown-pgns-container");

function renderUnknownPgnsTable(data) {
  if (!unknownPgnsContent) return;
  unknownPgnsContent.innerHTML = "";
  if (Object.keys(data).length === 0) {
    unknownPgnsContent.innerHTML = "<p>No unknown PGNs found.</p>";
    return;
  }
  const table = document.createElement("table");
  table.className = "min-w-full bg-gray-800 rounded-lg shadow text-sm";
  table.innerHTML = `
    <thead>
      <tr class="text-gray-300 border-b border-gray-700">
        <th class="px-4 py-2 text-left">PGN</th>
        <th class="px-4 py-2 text-left">Count</th>
        <th class="px-4 py-2 text-left">First Seen</th>
        <th class="px-4 py-2 text-left">Last Seen</th>
        <th class="px-4 py-2 text-left">Last Data</th>
      </tr>
    </thead>
    <tbody>
      ${Object.entries(data)
        .map(
          ([pgn, item]) => `
            <tr class="border-b border-gray-700 hover:bg-gray-700">
              <td class="px-4 py-2 font-mono text-blue-300">${pgn}</td>
              <td class="px-4 py-2 text-yellow-200 font-bold">${
                item.count?.toLocaleString?.() ?? ""
              }</td>
              <td class="px-4 py-2 text-gray-400">${
                item.first_seen_timestamp
                  ? new Date(item.first_seen_timestamp * 1000).toLocaleString()
                  : ""
              }</td>
              <td class="px-4 py-2 text-gray-400">${
                item.last_seen_timestamp
                  ? new Date(item.last_seen_timestamp * 1000).toLocaleString()
                  : ""
              }</td>
              <td class="px-4 py-2 text-green-400 font-mono">${
                item.last_data_hex || ""
              }</td>
            </tr>
          `
        )
        .join("")}
    </tbody>
  `;
  unknownPgnsContent.appendChild(table);
}

function renderUnknownPgnsCards(data) {
  if (!unknownPgnsContent) return;
  unknownPgnsContent.innerHTML = "";
  if (Object.keys(data).length === 0) {
    unknownPgnsContent.innerHTML = "<p>No unknown PGNs found.</p>";
    return;
  }
  const container = document.createElement("div");
  container.className = "space-y-4";
  Object.entries(data).forEach(([pgn, item]) => {
    const card = document.createElement("div");
    card.className = "bg-gray-800 rounded-lg shadow p-4";
    card.innerHTML = `
      <div class="flex flex-col md:flex-row md:items-center md:justify-between mb-2">
        <span class="font-mono text-blue-300 text-lg font-semibold">PGN: ${pgn}</span>
        <span class="inline-block bg-yellow-700 text-yellow-200 text-xs font-bold px-2 py-1 rounded mt-2 md:mt-0">Count: ${
          item.count?.toLocaleString?.() ?? ""
        }</span>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-x-4 gap-y-2 text-sm mb-2">
        <p><strong>First Seen:</strong> ${
          item.first_seen_timestamp
            ? new Date(item.first_seen_timestamp * 1000).toLocaleString()
            : ""
        }</p>
        <p><strong>Last Seen:</strong> ${
          item.last_seen_timestamp
            ? new Date(item.last_seen_timestamp * 1000).toLocaleString()
            : ""
        }</p>
        <p class="md:col-span-2"><strong>Last Data Hex:</strong> <code class="text-green-400">${
          item.last_data_hex || ""
        }</code></p>
      </div>
    `;
    container.appendChild(card);
  });
  unknownPgnsContent.appendChild(container);
}

export function renderUnknownPgnsWithToggle(data) {
  if (!unknownPgnsContent) return;
  unknownPgnsContent.innerHTML = "";
  // Add toggle buttons
  const toggleContainer = document.createElement("div");
  toggleContainer.className = "mb-4 flex gap-2 items-center";
  const tableBtn = document.createElement("button");
  tableBtn.textContent = "Table View";
  tableBtn.className =
    "px-3 py-1 rounded bg-gray-700 text-gray-200 hover:bg-gray-600 focus:outline-none";
  const cardBtn = document.createElement("button");
  cardBtn.textContent = "Card View";
  cardBtn.className =
    "px-3 py-1 rounded bg-gray-700 text-gray-200 hover:bg-gray-600 focus:outline-none";
  toggleContainer.appendChild(tableBtn);
  toggleContainer.appendChild(cardBtn);
  unknownPgnsContent.appendChild(toggleContainer);
  // Render default (table)
  let currentView = "table";
  function render() {
    if (currentView === "table") {
      renderUnknownPgnsTable(data);
    } else {
      renderUnknownPgnsCards(data);
    }
  }
  render();
  tableBtn.addEventListener("click", () => {
    currentView = "table";
    render();
  });
  cardBtn.addEventListener("click", () => {
    currentView = "card";
    render();
  });
}

export function fetchUnknownPgns() {
  fetchData(`${apiBasePath}/unknown_pgns`, {
    successCallback: renderUnknownPgnsWithToggle,
    errorCallback: (error) => {
      if (unknownPgnsContent)
        unknownPgnsContent.textContent = `Error loading unknown PGNs: ${error.message}`;
      showToast("Failed to load unknown PGNs.", "error");
    },
    loadingElement:
      unknownPgnsContent?.querySelector("#unknown-pgns-loading-message") ||
      unknownPgnsContent,
  });
}
