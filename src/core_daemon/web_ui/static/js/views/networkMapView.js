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
      '<tr><td colspan="7" class="text-center themed-table-muted">No addresses observed yet.</td></tr>';
    return;
  }
  tbody.innerHTML = data
    .map((addr) => {
      const isSelf = addr.is_self;
      return `<tr${isSelf ? ' class="themed-table-note"' : ""}>
      <td class="font-mono">${addr.value}</td>
      <td class="font-mono">0x${Number(addr.value)
        .toString(16)
        .toUpperCase()}</td>
      <td class="font-mono">${addr.dgn || ""}</td>
      <td class="font-mono">${addr.instance || ""}</td>
      <td>${addr.device_type || ""}</td>
      <td>${addr.friendly_name || ""}</td>
      <td>${addr.area || ""}</td>
      <td>${
        isSelf ? '<span class="themed-table-note">This node</span>' : ""
      }</td>
    </tr>`;
    })
    .join("");
}

export function renderNetworkMapView() {
  const view = document.getElementById("network-map-view");
  if (!view) return;
  view.innerHTML = `<h1 class="text-3xl font-bold mb-6">CAN Network Map</h1>
    <p class="mb-4 themed-table-muted">Observed CAN source addresses on the bus. Use this to avoid address conflicts and identify devices.</p>
    <div id="network-map-loading" class="mb-4">Loading network map...</div>
    <table class="themed-table">
      <thead><tr><th>Source Address</th><th>Hex</th><th>DGN</th><th>Instance</th><th>Device Type</th><th>Friendly Name</th><th>Area</th><th>Notes</th></tr></thead>
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
}

export function cleanupNetworkMapView() {
  disconnectNetworkMapSocket();
  const view = document.getElementById("network-map-view");
  if (view) view.innerHTML = "";
}
