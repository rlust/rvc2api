/**
 * @file canSnifferView.js
 * @module canSnifferView
 * @description
 *   Modularized CAN Sniffer view logic for the rvc2api Web UI frontend.
 *   Handles all UI, WebSocket, and rendering logic for the CAN Sniffer view.
 *   - Connects to the /api/ws/can-sniffer WebSocket endpoint for real-time updates
 *   - Renders command/response groupings in the CAN sniffer table
 *   - Provides cleanup and initialization for navigation
 *   - Exports renderCanSnifferView and cleanupCanSnifferView for use by app.js
 *
 *   This file should not contain any global app state or navigation logic.
 *   All DOM queries are scoped to the CAN Sniffer view elements.
 *
 *   Usage:
 *     import { renderCanSnifferView, cleanupCanSnifferView } from './views/canSnifferView.js';
 *     // Call renderCanSnifferView() when entering the view, cleanupCanSnifferView() when leaving.
 */

// canSnifferView.js - Modularized CAN Sniffer view logic for rvc2api Web UI
// Handles WebSocket connection, table rendering, and cleanup for CAN Sniffer

import { WebSocketManager } from "../wsManager.js";
import { showToast } from "../utils.js";

let canSnifferSocketManager = null;

function clearCanSnifferTable() {
  const canSnifferTable = document.getElementById("can-sniffer-table");
  if (canSnifferTable) {
    const tbody = canSnifferTable.querySelector("tbody");
    if (tbody) tbody.innerHTML = "";
  }
}

function addCanSnifferGroupRow(group) {
  const canSnifferTable = document.getElementById("can-sniffer-table");
  if (!canSnifferTable) return;
  const tbody = canSnifferTable.querySelector("tbody");
  if (!tbody) return;
  const { command, response, confidence } = group;
  let rowClass = "";
  let icon = "";
  if (confidence === "high") {
    rowClass = "bg-green-900/60 hover:bg-green-800/80";
    icon =
      '<span title="Mapped grouping" class="mdi mdi-link-variant text-green-400 mr-1"></span>';
  } else if (confidence === "low") {
    rowClass = "bg-yellow-900/60 hover:bg-yellow-800/80";
    icon =
      '<span title="Heuristic grouping" class="mdi mdi-help-circle-outline text-yellow-400 mr-1"></span>';
  }
  // Command row
  const trCmd = document.createElement("tr");
  trCmd.className = rowClass;
  trCmd.innerHTML = `
    <td class="px-2 py-1 font-mono">${new Date(
      command.timestamp * 1000
    ).toLocaleTimeString()}</td>
    <td class="px-2 py-1">TX</td>
    <td class="px-2 py-1 font-mono">${command.pgn || ""}</td>
    <td class="px-2 py-1 font-mono">${command.dgn_hex || ""}</td>
    <td class="px-2 py-1">${icon}${command.name || ""}</td>
    <td class="px-2 py-1 font-mono">${
      command.arbitration_id
        ? "0x" + command.arbitration_id.toString(16).toUpperCase()
        : ""
    }</td>
    <td class="px-2 py-1 font-mono">${command.data || ""}</td>
    <td class="px-2 py-1 font-mono">${
      command.decoded ? JSON.stringify(command.decoded) : ""
    }</td>
  `;
  tbody.appendChild(trCmd);
  // Response row
  const trResp = document.createElement("tr");
  trResp.className = rowClass;
  trResp.innerHTML = `
    <td class="px-2 py-1 font-mono">${new Date(
      response.timestamp * 1000
    ).toLocaleTimeString()}</td>
    <td class="px-2 py-1">RX</td>
    <td class="px-2 py-1 font-mono">${response.pgn || ""}</td>
    <td class="px-2 py-1 font-mono">${response.dgn_hex || ""}</td>
    <td class="px-2 py-1">${icon}${response.name || ""}</td>
    <td class="px-2 py-1 font-mono">${
      response.arbitration_id
        ? "0x" + response.arbitration_id.toString(16).toUpperCase()
        : ""
    }</td>
    <td class="px-2 py-1 font-mono">${response.data || ""}</td>
    <td class="px-2 py-1 font-mono">${
      response.decoded ? JSON.stringify(response.decoded) : ""
    }</td>
  `;
  tbody.appendChild(trResp);
}

function connectCanSnifferSocket() {
  if (!canSnifferSocketManager) {
    canSnifferSocketManager = new WebSocketManager(
      "/api/ws/can-sniffer",
      (eventData) => {
        const group = JSON.parse(eventData);
        addCanSnifferGroupRow(group);
      },
      {
        onOpen: () => {
          clearCanSnifferTable();
          const canSnifferLoading = document.getElementById(
            "can-sniffer-loading-message"
          );
          if (canSnifferLoading) canSnifferLoading.classList.add("hidden");
        },
        onClose: () => {},
        onError: () => {},
        autoReconnect: true,
        reconnectInterval: 5000,
      }
    );
  }
}

function disconnectCanSnifferSocket() {
  if (canSnifferSocketManager) {
    canSnifferSocketManager.close();
    canSnifferSocketManager = null;
  }
}

function fetchCanSnifferLog() {
  const canSnifferLoading = document.getElementById(
    "can-sniffer-loading-message"
  );
  const canSnifferTable = document.getElementById("can-sniffer-table");
  if (!canSnifferTable) return;
  const tbody = canSnifferTable.querySelector("tbody");
  if (tbody) tbody.innerHTML = "";
  fetchData("/api/can-sniffer", {
    successCallback: (data) => {
      if (canSnifferLoading) canSnifferLoading.classList.add("hidden");
      if (!Array.isArray(data) || data.length === 0) {
        if (tbody) tbody.innerHTML = "";
        return;
      }
      data
        .slice()
        .reverse()
        .forEach((group) => {
          addCanSnifferGroupRow(group);
        });
    },
    errorCallback: (error) => {
      if (canSnifferLoading) canSnifferLoading.classList.add("hidden");
      showToast("Failed to load CAN sniffer log.", "error");
    },
    loadingElement: canSnifferLoading,
  });
}

export function renderCanSnifferView() {
  clearCanSnifferTable();
  connectCanSnifferSocket();
}

export function cleanupCanSnifferView() {
  disconnectCanSnifferSocket();
  clearCanSnifferTable();
}

export {
  connectCanSnifferSocket,
  disconnectCanSnifferSocket,
  clearCanSnifferTable,
  addCanSnifferGroupRow,
  fetchCanSnifferLog,
};
