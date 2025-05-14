/**
 * networkMapView.js - Displays a network map of observed CAN source addresses and basic info.
 *
 * - Fetches observed source addresses from the backend
 * - Renders a table or grid of all observed source addresses
 * - Optionally shows which address is 'self' (our node)
 * - Can be extended to show more info (device names, traffic counts, etc.)
 */
import { fetchData } from "../api.js";
import { showToast } from "../utils.js";
import { WebSocketManager } from "../wsManager.js";

let networkMapSocketManager = null;
let networkMapData = {};

// Track expanded rows for decoded/raw by address value and type
const expandedNetworkMapRows = new Set();

function prettyPrintJSON(obj) {
  if (!obj) return "";
  let jsonString = "";
  try {
    jsonString = JSON.stringify(obj, null, 2);
  } catch (e) {
    return String(obj);
  }
  return `<pre class="themed-json pretty-json">${escapeHTML(jsonString)}</pre>`;
}

function escapeHTML(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</ / g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function makeExpandButton(rowKey, type) {
  const btn = document.createElement("button");
  btn.className = "expand-json-btn themed-table-btn";
  btn.title = `Show full ${type} JSON`;
  btn.innerHTML = '<span class="mdi mdi-chevron-down"></span>';
  btn.setAttribute("aria-expanded", expandedNetworkMapRows.has(rowKey));
  btn.onclick = function (e) {
    e.stopPropagation();
    toggleExpandRow(rowKey, btn, type);
  };
  return btn;
}

function toggleExpandRow(rowKey, btn, type) {
  const tr = document.getElementById(rowKey);
  if (!tr) return;
  const expanded = expandedNetworkMapRows.has(rowKey);
  if (expanded) {
    const next = tr.nextSibling;
    if (next && next.classList.contains("expanded-json-row")) {
      next.remove();
    }
    expandedNetworkMapRows.delete(rowKey);
    btn.setAttribute("aria-expanded", false);
    btn.innerHTML = '<span class="mdi mdi-chevron-down"></span>';
  } else {
    const jsonData = tr.getAttribute(`data-${type}-json`);
    const colCount = tr.children.length;
    const expandedTr = document.createElement("tr");
    expandedTr.className = "expanded-json-row themed-table-expanded";
    const td = document.createElement("td");
    td.colSpan = colCount;
    td.innerHTML = jsonData;
    expandedTr.appendChild(td);
    tr.parentNode.insertBefore(expandedTr, tr.nextSibling);
    expandedNetworkMapRows.add(rowKey);
    btn.setAttribute("aria-expanded", true);
    btn.innerHTML = '<span class="mdi mdi-chevron-up"></span>';
  }
}

function connectNetworkMapSocket() {
  if (!networkMapSocketManager) {
    networkMapSocketManager = new WebSocketManager(
      "/api/ws/network-map",
      (eventData) => {
        const data = JSON.parse(eventData);
        updateNetworkMapTable(data);
      },
      {
        onOpen: () => {
          document
            .getElementById("network-map-loading")
            ?.classList.add("hidden");
        },
        onClose: () => {},
        onError: () => {},
        autoReconnect: true,
        reconnectInterval: 5000,
      }
    );
  }
}

function disconnectNetworkMapSocket() {
  if (networkMapSocketManager) {
    networkMapSocketManager.close();
    networkMapSocketManager = null;
  }
}

function updateNetworkMapTable(data) {
  const tbody = document.getElementById("network-map-table-body");
  if (!tbody) return;
  if (!Array.isArray(data) || data.length === 0) {
    tbody.innerHTML =
      '<tr><td colspan="10" class="text-center themed-table-muted">No addresses observed yet.</td></tr>';
    networkMapData = {};
    return;
  }
  tbody.innerHTML = "";
  networkMapData = {};
  data.forEach((addr) => {
    networkMapData[addr.value] = addr;
    const isSelf = addr.is_self;
    const rowKey = `networkmap_${addr.value}`;
    const tr = document.createElement("tr");
    if (isSelf) tr.className = "themed-table-note";
    tr.id = rowKey;
    // Store pretty JSON as attribute for expansion
    tr.setAttribute("data-decoded-json", prettyPrintJSON(addr.decoded));
    tr.setAttribute("data-raw-json", prettyPrintJSON(addr.raw));
    tr.innerHTML = `
      <td class="font-mono">${addr.value}</td>
      <td class="font-mono">0x${Number(addr.value)
        .toString(16)
        .toUpperCase()}</td>
      <td class="font-mono">${addr.dgn || ""}</td>
      <td class="font-mono">${addr.instance || ""}</td>
      <td>${addr.device_type || ""}</td>
      <td>${addr.friendly_name || ""}</td>
      <td>${addr.area || ""}</td>
      <td>${addr.notes || ""}</td>
      <td>${addr.decoded ? `<span class='json-summary'>{...}</span>` : ""}</td>
      <td>${addr.raw ? `<span class='json-summary'>{...}</span>` : ""}</td>
    `;
    // Add expand buttons if decoded/raw exist
    if (addr.decoded) {
      const btn = makeExpandButton(rowKey + "_decoded", "decoded");
      const td = tr.querySelector("td:nth-child(9)");
      td.insertBefore(btn, td.firstChild);
    }
    if (addr.raw) {
      const btn = makeExpandButton(rowKey + "_raw", "raw");
      const td = tr.querySelector("td:nth-child(10)");
      td.insertBefore(btn, td.firstChild);
    }
    tbody.appendChild(tr);
  });
}

export function renderNetworkMapView() {
  const view = document.getElementById("network-map-view");
  if (!view) return;
  view.innerHTML = `<h1 class="text-3xl font-bold mb-6">CAN Network Map</h1>
    <div class="mb-4 flex items-center gap-4">
      <p class="themed-table-muted flex-1">Observed CAN source addresses on the bus. Use this to avoid address conflicts and identify devices.</p>
      <button id="btn-canbus-scan" class="themed-table-btn bg-blue-600 hover:bg-blue-700 text-white font-semibold px-4 py-2 rounded shadow flex items-center gap-2">
        <i class="mdi mdi-radar" aria-hidden="true"></i>Scan CANbus
      </button>
    </div>
    <div id="network-map-loading" class="mb-4">Loading network map...</div>
    <table class="themed-table">
      <thead><tr><th>Source Address</th><th>Hex</th><th>DGN</th><th>Instance</th><th>Device Type</th><th>Friendly Name</th><th>Area</th><th>Notes</th><th>Decoded</th><th>Raw</th></tr></thead>
      <tbody id="network-map-table-body"></tbody>
    </table>`;
  // Fetch initial data via HTTP
  fetchData("/api/network-map", {
    successCallback: (data) => {
      updateNetworkMapTable(data);
      document.getElementById("network-map-loading")?.classList.add("hidden");
    },
    errorCallback: (err) => {
      updateNetworkMapTable([]);
      document.getElementById("network-map-loading").textContent =
        "Failed to load network map.";
    },
  });
  connectNetworkMapSocket();
  // Add CANbus Scan button handler
  const scanBtn = document.getElementById("btn-canbus-scan");
  if (scanBtn) {
    scanBtn.onclick = () => {
      fetchData("/api/canbus-scan", {
        method: "POST",
        successCallback: () =>
          showToast(
            "CANbus scan started. Results will appear below as devices respond."
          ),
        errorCallback: () => showToast("Failed to start CANbus scan.", "error"),
      });
    };
  }
  // Connect to the CANbus scan WebSocket for live scan results
  let scanResults = [];
  let ws;
  function mergeScanResult(result) {
    // If the result has a value (address), merge or add it
    if (!result || typeof result.value === "undefined") return;
    networkMapData[result.value] = Object.assign(
      {},
      networkMapData[result.value] || {},
      result
    );
    // Re-render the table with updated data
    updateNetworkMapTable(Object.values(networkMapData));
  }
  function connectScanWebSocket() {
    ws = new WebSocket(
      (window.location.protocol === "https:" ? "wss://" : "ws://") +
        window.location.host +
        "/api/ws/canbus-scan"
    );
    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        scanResults.push(data);
        mergeScanResult(data);
      } catch (e) {}
    };
    ws.onopen = () => {
      // Optionally show a toast or indicator
    };
    ws.onclose = () => {
      // Optionally reconnect or show a message
    };
    ws.onerror = () => {};
  }
  connectScanWebSocket();
}

export function cleanupNetworkMapView() {
  disconnectNetworkMapSocket();
  const view = document.getElementById("network-map-view");
  if (view) view.innerHTML = "";
}
