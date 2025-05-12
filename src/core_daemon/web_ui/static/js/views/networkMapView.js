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
    const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    networkMapSocketManager = new WebSocketManager(
      `${wsProtocol}//${window.location.host}/api/ws/network-map`,
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
      '<tr><td colspan="3" class="text-center text-gray-500">No addresses observed yet.</td></tr>';
    return;
  }
  tbody.innerHTML = data
    .map((addr) => {
      const isSelf = addr.is_self;
      return `<tr${isSelf ? ' class="bg-green-900/60"' : ""}>
      <td class="px-2 py-1 font-mono">${addr.value}</td>
      <td class="px-2 py-1 font-mono">0x${Number(addr.value)
        .toString(16)
        .toUpperCase()}</td>
      <td class="px-2 py-1">${
        isSelf ? '<span class="text-green-400">This node</span>' : ""
      }</td>
    </tr>`;
    })
    .join("");
}

export function renderNetworkMapView() {
  const view = document.getElementById("network-map-view");
  if (!view) return;
  view.innerHTML = `<h1 class="text-3xl font-bold mb-6">CAN Network Map</h1>
    <p class="mb-4 text-gray-400">Observed CAN source addresses on the bus. Use this to avoid address conflicts and identify devices.</p>
    <div id="network-map-loading" class="mb-4">Loading network map...</div>
    <table class="min-w-full bg-gray-800 text-gray-200 rounded shadow text-xs">
      <thead><tr><th class="px-2 py-1">Source Address</th><th class="px-2 py-1">Hex</th><th class="px-2 py-1">Notes</th></tr></thead>
      <tbody id="network-map-table-body"></tbody>
    </table>`;
  connectNetworkMapSocket();
}

export function cleanupNetworkMapView() {
  disconnectNetworkMapSocket();
  const view = document.getElementById("network-map-view");
  if (view) view.innerHTML = "";
}
