/**
 * app.js - Main JavaScript for the rvc2api Web UI
 *
 * Handles:
 * - Theme management and sidebar state
 * - Fetching and rendering API status, health, CAN status, and entity data
 * - WebSocket connections for logs and entity updates
 * - UI event handling for navigation, controls, and user feedback
 * - Utility functions for DOM manipulation and notifications
 *
 * Author: Ryan Holt
 * Last updated: 2025-05-10
 */

(function () {
  // =====================
  // CONSTANTS & SETTINGS
  // =====================
  /**
   * @type {string | null} The application version, read from a data attribute on the body.
   */
  let APP_VERSION = null; // Will be read from body data attribute

  const VALID_THEMES = [
    "default",
    "dark",
    "light",
    "catppuccin-mocha",
    "catppuccin-latte",
    "nord-dark",
    "nord-light",
    "gruvbox-dark",
    "gruvbox-light",
  ];
  const DEFAULT_THEME = "catppuccin-mocha";
  const SELECTED_THEME_KEY = "selectedTheme"; // Standardized localStorage key
  const DESKTOP_SIDEBAR_EXPANDED_KEY = "desktopSidebarExpanded"; // Standardized localStorage key

  const LOG_WEBSOCKET_RECONNECT_INTERVAL = 5000;
  const CAN_STATUS_REFRESH_INTERVAL = 10000;
  const API_STATUS_REFRESH_INTERVAL = 30000;
  const APP_HEALTH_REFRESH_INTERVAL = 30000;

  const MD_BREAKPOINT_PX = 768; // Tailwind's 'md' breakpoint
  const CLASS_HIDDEN = "hidden";
  const CLASS_ACTIVE_NAV = "active-nav";
  const CLASS_LIGHT_ON = "light-on";
  const CLASS_LIGHT_OFF = "light-off";
  const THEME_CLASSES = VALID_THEMES.map((t) => `theme-${t}`);
  const ATTR_DATA_VIEW = "data-view";
  const ARIA_HIDDEN = "aria-hidden";

  const SIDEBAR_EXPANDED_WIDTH_DESKTOP = "md:w-64"; // 16rem
  const SIDEBAR_COLLAPSED_WIDTH_DESKTOP = "md:w-16"; // 4rem
  const MAIN_CONTENT_MARGIN_EXPANDED_DESKTOP = "md:ml-64";
  const MAIN_CONTENT_MARGIN_COLLAPSED_DESKTOP = "md:ml-16";

  const LOG_LEVELS = {
    DEBUG: 0,
    INFO: 1,
    WARNING: 2,
    ERROR: 3,
    CRITICAL: 4,
  };
  const LOG_LEVEL_NAMES = Object.keys(LOG_LEVELS);
  // ... existing constants ...
  const ICON_COPY = `<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor" class="w-4 h-4 inline-block mr-1"><path stroke-linecap="round" stroke-linejoin="round" d="M15.75 17.25v3.375c0 .621-.504 1.125-1.125 1.125h-9.75a1.125 1.125 0 01-1.125-1.125V7.875c0-.621.504-1.125 1.125-1.125H6.75a9.06 9.06 0 011.5.124m7.5 10.376h3.375c.621 0 1.125-.504 1.125-1.125V11.25c0-4.46-3.243-8.161-7.5-8.876a9.06 9.06 0 00-1.5-.124H9.375c-.621 0-1.125.504-1.125 1.125v3.5m7.5 4.625a3.375 3.375 0 11-6.75 0 3.375 3.375 0 016.75 0z" /></svg>`;
  const ICON_LOADING_SPINNER = `<svg class="animate-spin -ml-1 mr-2 h-4 w-4 text-white inline-block" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" aria-hidden="true"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg>`;
  const CLASS_TEXT_GREEN_400 = "text-green-400";
  const CLASS_TEXT_RED_400 = "text-red-400";
  const CLASS_TEXT_YELLOW_400 = "text-yellow-400";

  const apiBasePath = "/api";

  // =====================
  // DOM ELEMENT CACHE
  // =====================
  // ... existing cached elements ...
  const appHeader = document.getElementById("appHeader"); // For app version display
  const appVersionDisplay = document.getElementById("appVersionDisplay"); // Span to show APP_VERSION

  const mainContent = document.getElementById("mainContent");
  const sidebar = document.getElementById("sidebar");
  const sidebarNavContent = document.getElementById("sidebarNavContent");
  const toggleSidebarDesktopButton = document.getElementById(
    "toggleSidebarDesktop"
  );
  const mobileMenuButton = document.getElementById("mobileMenuButton");
  const navLinks = document.querySelectorAll(".nav-link");
  const views = document.querySelectorAll(".view-section");
  const homeView = document.getElementById("home-view");
  const lightsView = document.getElementById("lights-view");
  const lightsContent = document.getElementById("lightsContent"); // Updated from light-grid
  const lightsLoadingMessage = document.getElementById(
    "lights-loading-message"
  );
  const areaFilter = document.getElementById("area-filter");
  const mappingView = document.getElementById("mapping-view");
  const mappingContent = document.getElementById("mapping-content");
  const specView = document.getElementById("spec-view");
  const specContent = document.getElementById("spec-content");
  const specMetadataDiv = document.getElementById("spec-metadata");
  const unmappedEntriesView = document.getElementById("unmapped-view");
  const unmappedEntriesContent = document.getElementById(
    "unmapped-entries-container"
  );
  const unknownPgnsView = document.getElementById("unknown-pgns-view");
  const unknownPgnsContent = document.getElementById("unknown-pgns-container");
  const apiStatusContent = document.getElementById("api-status-container");
  const appHealthContent = document.getElementById("app-health-container");
  const canStatusContent = document.getElementById("can-status-container");
  const logStream = document.getElementById("log-stream");
  const logLevelSelect = document.getElementById("log-level");
  const logSearchInput = document.getElementById("log-search");
  const logPauseButton = document.getElementById("log-pause");
  const logResumeButton = document.getElementById("log-resume");
  const logClearButton = document.getElementById("log-clear");
  const themeSwitcher = document.getElementById("themeSwitcher");
  const pinnedLogsContainer = document.getElementById("pinnedLogsContainer");
  const pinnedLogsContent = document.getElementById("pinnedLogsContent");
  const pinnedLogsHeader = document.getElementById("pinnedLogsHeader");
  const pinnedLogsResizeHandle = document.getElementById(
    "pinnedLogsResizeHandle"
  );
  const togglePinnedLogsButton = document.getElementById("togglePinnedLogsBtn");
  const toastContainer = document.getElementById("toast-container");
  const closeSidebarButton = document.getElementById("closeSidebarButton");

  let logSocket;
  let currentView = "home"; // Default view
  let currentTheme = DEFAULT_THEME;
  let pinnedLogMessages = []; // Not currently used, consider for re-filtering if needed
  let isPinnedLogsVisible = false; // Consider if this state is needed or derived from DOM
  let isResizingPinnedLogs = false; // Already used for resize handle
  let originalContainerTransition; // For resize handle
  let currentLogLevel = LOG_LEVELS.INFO; // Default log level
  let isLogPaused = false;
  let entitySocket; // For real-time entity updates (e.g., lights)
  let lightStates = {}; // To store the state of lights for optimistic UI and updates
  let isDesktopSidebarExpanded = true; // Track desktop sidebar state
  const currentLightStates = {}; // Store current states of all lights
  // Update: Use /api/ws for the entity WebSocket endpoint to match backend router prefix
  const entitySocketUrl = `ws://${window.location.host}/api/ws`;

  // =====================
  // UTILITY FUNCTIONS
  // =====================

  /**
   * Creates a DOM element with specified options.
   * @param {string} tag - The HTML tag for the element.
   * @param {object} [options={}] - Options for creating the element.
   * @param {string} [options.className] - CSS class name(s).
   * @param {string} [options.id] - Element ID.
   * @param {string} [options.textContent] - Text content.
   * @param {string} [options.innerHTML] - Inner HTML.
   * @param {object} [options.dataset] - Data attributes.
   * @param {object} [options.attributes] - Other HTML attributes.
   * @param {HTMLElement[]} [options.children] - Child elements to append.
   * @returns {HTMLElement} The created DOM element.
   */
  function createDomElement(tag, options = {}) {
    const el = document.createElement(tag);
    if (options.className) el.className = options.className;
    if (options.id) el.id = options.id;
    if (options.textContent) el.textContent = options.textContent;
    if (options.innerHTML) el.innerHTML = options.innerHTML;
    if (options.dataset) {
      for (const [k, v] of Object.entries(options.dataset)) {
        el.dataset[k] = v;
      }
    }
    if (options.attributes) {
      for (const [k, v] of Object.entries(options.attributes)) {
        el.setAttribute(k, v);
      }
    }
    if (options.children) {
      options.children.forEach((child) => el.appendChild(child));
    }
    return el;
  }

  /**
   * Universal fetch utility for API calls with flexible options and error handling.
   *
   * @param {string} url - The endpoint URL to fetch.
   * @param {object} [options={}] - Options for the fetch request.
   * @param {'GET'|'POST'|'PUT'|'DELETE'} [options.method='GET'] - HTTP method.
   * @param {object} [options.headers] - Request headers (default: JSON for POST/PUT, none for GET).
   * @param {object|string|null} [options.body=null] - Request body (object will be JSON.stringified).
   * @param {'json'|'text'} [options.responseType='json'] - Expected response type.
   * @param {function} [options.successCallback] - Called with response data on success.
   * @param {function} [options.errorCallback] - Called with error object on failure.
   * @param {HTMLElement|null} [options.loadingElement=null] - Element to show loading/error message.
   * @param {boolean} [options.showToastOnError=true] - Show toast on error.
   */
  function fetchData(url, options = {}) {
    const {
      method = "GET",
      headers = method === "GET" ? {} : { "Content-Type": "application/json" },
      body = null,
      responseType = "json",
      successCallback = () => {},
      errorCallback = null,
      loadingElement = null,
      showToastOnError = true,
    } = options;

    if (loadingElement) {
      loadingElement.textContent = "Loading...";
      loadingElement.classList.remove("text-red-500");
      loadingElement.classList.add("text-gray-400");
    }

    fetch(url, {
      method,
      headers,
      body:
        body && method !== "GET"
          ? typeof body === "string"
            ? body
            : JSON.stringify(body)
          : undefined,
    })
      .then((response) => {
        if (!response.ok) {
          // Try to parse error JSON, fallback to status text
          return response[responseType]()
            .then((err) => {
              throw {
                message: err.message || response.statusText,
                status: response.status,
              };
            })
            .catch(() => {
              throw { message: response.statusText, status: response.status };
            });
        }
        return responseType === "text" ? response.text() : response.json();
      })
      .then((data) => {
        if (loadingElement) loadingElement.textContent = "";
        successCallback(data);
      })
      .catch((error) => {
        if (loadingElement) {
          loadingElement.textContent = `Error: ${error.message || error}`;
          loadingElement.classList.remove("text-gray-400");
          loadingElement.classList.add("text-red-500");
        }
        if (showToastOnError)
          showToast(`Error: ${error.message || error}`, "error");
        if (typeof errorCallback === "function") errorCallback(error);
      });
  }

  /**
   * Shows a toast notification.
   * @param {string} message - The message to display.
   * @param {'info'|'success'|'warning'|'error'} [type='info'] - The type of toast.
   * @param {number} [duration=5000] - Duration in milliseconds to show the toast.
   */
  function showToast(message, type = "info", duration = 3000) {
    if (!toastContainer) return;

    const toast = createDomElement("div", {
      className: `toast toast-${type}`,
      textContent: message,
      attributes: { role: "alert" },
    });

    toastContainer.appendChild(toast);

    // Animate in
    setTimeout(() => {
      toast.classList.add("show");
    }, 10); // Small delay for CSS transition

    // Auto remove
    setTimeout(() => {
      toast.classList.remove("show");
      setTimeout(() => {
        toast.remove();
      }, 300); // Allow fade out animation
    }, duration);
  }

  // =====================
  // API FETCH & RENDERING
  // =====================
  /**
   * Updates the API server status view.
   * Fetches from /api/status/server and displays status, message, and version.
   * @param {object} data - Data from the API.
   * @param {string} data.status - Server status (e.g., 'ok', 'error').
   * @param {string} [data.message] - Optional status message.
   * @param {string} [data.version] - Server version.
   */
  function updateApiServerView(data) {
    if (!apiStatusContent) return;
    apiStatusContent.innerHTML = "";
    const status = data.status || "unknown";
    const message = data.message || "";
    const version = data.version || APP_VERSION || "";
    const statusColor =
      status === "ok"
        ? CLASS_TEXT_GREEN_400
        : status === "error"
        ? CLASS_TEXT_RED_400
        : CLASS_TEXT_YELLOW_400;
    apiStatusContent.innerHTML = `
      <div class="flex items-center space-x-2">
        <span class="font-semibold">Status:</span>
        <span class="${statusColor}">${status}</span>
        <span class="ml-4 font-semibold">Version:</span>
        <span>${version}</span>
      </div>
      <div class="mt-2 text-sm text-gray-400">${message}</div>
    `;
  }

  /**
   * Updates the application health view.
   * Fetches from /api/status/application and displays key health metrics.
   * @param {object} data - Health data with keys as metric names and values as status/counts.
   */
  function updateApplicationHealthView(data) {
    if (!appHealthContent) return;
    appHealthContent.innerHTML = "";
    if (!data || typeof data !== "object") {
      appHealthContent.textContent = "No health data available.";
      return;
    }
    const entries = Object.entries(data).map(([key, value]) => {
      return `<div><span class="font-semibold">${key}:</span> <span>${value}</span></div>`;
    });
    appHealthContent.innerHTML = entries.join("");
  }

  /**
   * Updates the CAN status view.
   * Fetches from /api/can/status and displays CAN interface status.
   * @param {object} data - CAN status data, expected to have an 'interfaces' object.
   */
  function updateCanStatusView(data) {
    if (!canStatusContent) return;
    canStatusContent.innerHTML = "";
    if (
      !data ||
      !data.interfaces ||
      Object.keys(data.interfaces).length === 0
    ) {
      canStatusContent.textContent = "No CAN interfaces found.";
      return;
    }
    const interfaces = data.interfaces;
    Object.entries(interfaces).forEach(([iface, stats]) => {
      const ifaceDiv = document.createElement("div");
      ifaceDiv.className = "mb-2";
      ifaceDiv.innerHTML = `<span class="font-semibold">${iface}:</span> <span>${
        stats.state || "unknown"
      }</span> <span class="ml-2 text-xs text-gray-400">RX: ${
        stats.rx_packets || 0
      } / TX: ${stats.tx_packets || 0}</span>`;
      canStatusContent.appendChild(ifaceDiv);
    });
  }

  /**
   * Calls a service for an entity, typically for control commands.
   * @param {string} entityId - The ID of the entity.
   * @param {string} command - The command to execute (e.g., 'turn_on', 'turn_off', 'set_brightness').
   * @param {object} [data={}] - Additional data for the command (e.g., { brightness: 128 }).
   */
  async function callLightService(entityId, command, data = {}) {
    const path = `${apiBasePath}/entities/${entityId}/control`;
    const body = { command, ...data };

    try {
      const response = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!response.ok) {
        const errorData = await response
          .json()
          .catch(() => ({ message: "Request failed, unable to parse error." }));
        console.error(
          `Error calling service for ${entityId}:`,
          response.status,
          errorData
        );
        showToast(
          `Error: ${errorData.message || response.statusText}`,
          "error"
        );
        return null;
      }
      const responseData = await response.json();
      // console.log(`Service call successful for ${entityId}:`, responseData);
      // Optimistic update handled by WebSocket, or could be done here if no WS
      showToast(`${entityId} ${command} command sent.`, "info", 2000);
      return responseData;
    } catch (error) {
      console.error(`Network error calling service for ${entityId}:`, error);
      showToast(`Network error: ${error.message}`, "error");
      return null;
    }
  }

  /**
   * Fetches and updates the API server status.
   */
  function fetchApiStatus() {
    fetchData(`${apiBasePath}/status/server`, {
      successCallback: updateApiServerView,
      errorCallback: (error) => {
        console.error("Failed to fetch API server status:", error);
        if (apiStatusContent)
          apiStatusContent.textContent = `Error loading API status: ${error.message}`;
      },
      loadingElement:
        apiStatusContent?.querySelector("#api-status-loading-message") ||
        apiStatusContent,
      showToastOnError: false, // Background poll
    });
  }

  /**
   * Fetches and updates the application health status.
   */
  function fetchAppHealth() {
    fetchData(`${apiBasePath}/status/application`, {
      successCallback: updateApplicationHealthView,
      errorCallback: (error) => {
        console.error("Failed to fetch application health:", error);
        if (appHealthContent)
          appHealthContent.textContent = `Error loading app health: ${error.message}`;
      },
      loadingElement:
        appHealthContent?.querySelector("#app-health-loading-message") ||
        appHealthContent,
      showToastOnError: false, // Background poll
    });
  }

  /**
   * Fetches and updates the CAN interface status.
   */
  function fetchCanStatus() {
    fetchData(`${apiBasePath}/can/status`, {
      successCallback: updateCanStatusView,
      errorCallback: (error) => {
        console.error("Failed to fetch CAN status:", error);
        if (canStatusContent)
          canStatusContent.textContent = `Error loading CAN status: ${error.message}`;
      },
      loadingElement:
        canStatusContent?.querySelector("#can-status-loading-message") ||
        canStatusContent,
      showToastOnError: false, // Background polling
    });
  }

  /**
   * Renders a single light card.
   * @param {object} entity - The light entity object.
   * @returns {HTMLElement} The created card element.
   */
  function renderLightCard(entity) {
    const card = document.createElement("div");
    card.className = "entity-card p-4 rounded-lg shadow-md space-y-3"; // Base classes from main.css
    card.dataset.entityId = entity.entity_id;

    const friendlyName = entity.friendly_name || entity.entity_id;
    const state = entity.state || "unknown";
    const capabilities = entity.capabilities || [];
    const rawAttrs = entity.raw_attributes || {};

    card.classList.toggle("light-on", state.toLowerCase() === "on");
    card.classList.toggle("light-off", state.toLowerCase() !== "on");

    let cardContent = `<h3 class="text-lg font-semibold">${friendlyName}</h3>`;
    cardContent += `<p class="text-sm">State: <span class="font-medium state-text">${state}</span></p>`;

    const hasBrightness = capabilities.includes("brightness");

    if (hasBrightness) {
      let currentBrightnessPercent = 0;
      if (
        state.toLowerCase() === "on" &&
        typeof rawAttrs.brightness === "number"
      ) {
        // Assuming brightness in raw_attributes is 0-255, convert to 0-100 for slider
        currentBrightnessPercent = Math.round(
          (rawAttrs.brightness / 255) * 100
        );
      } else if (
        state.toLowerCase() === "on" &&
        typeof entity.brightness === "number"
      ) {
        // Fallback if brightness is directly on entity (0-100)
        currentBrightnessPercent = entity.brightness;
      }

      cardContent += `
        <div class="brightness-control space-y-1">
          <label for="brightness-${
            entity.entity_id
          }" class="block text-sm font-medium">Brightness: <span class="brightness-value">${currentBrightnessPercent}%</span></label>
          <input type="range" id="brightness-${
            entity.entity_id
          }" name="brightness"
                 min="0" max="100" value="${currentBrightnessPercent}"
                 class="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer brightness-slider"
                 ${state.toLowerCase() !== "on" ? "disabled" : ""}>
        </div>
      `;
    }

    card.innerHTML = cardContent;

    // Event listener for the whole card (toggle on/off)
    card.addEventListener("click", (e) => {
      if (e.target.closest(".brightness-control")) {
        return; // Don't toggle if click is on brightness slider
      }
      callLightService(entity.entity_id, "toggle");
    });

    if (hasBrightness) {
      const slider = card.querySelector(".brightness-slider");
      const brightnessValueDisplay = card.querySelector(".brightness-value");
      if (slider && brightnessValueDisplay) {
        slider.addEventListener("input", () => {
          brightnessValueDisplay.textContent = slider.value + "%";
        });
        slider.addEventListener("change", () => {
          const brightness = parseInt(slider.value, 10);
          callLightService(entity.entity_id, "set", { brightness: brightness });
        });
      }
    }
    return card;
  }

  /**
   * Renders grouped lights by area or as a flat list.
   * @param {object} areas - Object mapping area keys to area details (currently unused, API may not provide).
   * @param {object[]} entities - Array of light entity objects.
   */
  function renderGroupedLights() {
    if (!lightsContent) return;
    lightsContent.innerHTML = ""; // Clear previous content

    const selectedArea = areaFilter.value;
    localStorage.setItem("lightsAreaFilter", selectedArea); // Save filter choice

    const grouped = {};
    Object.values(currentLightStates).forEach((entity) => {
      if (entity.device_type !== "light") return; // Ensure it's a light
      const area = entity.suggested_area || "Unknown Area";
      if (selectedArea !== "All" && selectedArea !== area) return;

      if (!grouped[area]) grouped[area] = [];
      grouped[area].push(entity);
    });

    if (Object.keys(grouped).length === 0 && selectedArea === "All") {
      lightsContent.innerHTML = '<p class="text-gray-400">No lights found.</p>';
      return;
    } else if (Object.keys(grouped).length === 0) {
      lightsContent.innerHTML = `<p class="text-gray-400">No lights found in area: ${selectedArea}.</p>`;
      return;
    }

    Object.keys(grouped)
      .sort()
      .forEach((area) => {
        const section = document.createElement("div");
        section.className = "mb-8"; // Spacing between area groups

        const header = document.createElement("h2");
        header.className = "text-2xl font-semibold mb-4 pb-2";
        // Use CSS variable for border color for theme compatibility
        header.style.borderBottom = `2px solid var(--color-border-primary)`;
        header.textContent = area;
        section.appendChild(header);

        const grid = document.createElement("div");
        grid.className = "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6";
        section.appendChild(grid);

        grouped[area]
          .sort((a, b) =>
            (a.friendly_name || a.entity_id).localeCompare(
              b.friendly_name || b.entity_id
            )
          )
          .forEach((entity) => {
            grid.appendChild(renderLightCard(entity));
          });
        lightsContent.appendChild(section);
      });
  }

  /**
   * Updates the lights view with fetched data.
   * @param {object} data - The response from the lights API. Expected to be an object where keys are entity IDs.
   */
  async function updateLightsView() {
    if (!lightsView.classList.contains("hidden")) {
      // Only fetch if view is active
      if (lightsLoadingMessage) lightsLoadingMessage.classList.remove("hidden");
      if (lightsContent) lightsContent.innerHTML = ""; // Clear previous

      try {
        const response = await fetch(
          `${apiBasePath}/entities?device_type=light`
        );
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`);
        }
        const lightsData = await response.json();

        Object.keys(currentLightStates).forEach(
          (key) => delete currentLightStates[key]
        ); // Clear old states
        Object.values(lightsData).forEach((light) => {
          currentLightStates[light.entity_id] = light;
        });

        if (lightsLoadingMessage) lightsLoadingMessage.classList.add("hidden");
        updateAreaFilterForLights(currentLightStates);
        renderGroupedLights();
      } catch (error) {
        console.error("Failed to fetch lights:", error);
        if (lightsLoadingMessage) {
          lightsLoadingMessage.textContent =
            "Error loading lights. Please check console.";
          lightsLoadingMessage.classList.remove("hidden");
        }
        if (lightsContent)
          lightsContent.innerHTML =
            '<p class="text-red-500">Error loading lights data.</p>';
      }
    }
  }

  /**
   * Fetches light entities from the API.
   * Uses /api/entities?type=light as per user's note.
   */
  function fetchLights() {
    fetchData(`${apiBasePath}/entities?type=light`, {
      successCallback: updateLightsView,
      errorCallback: (error) => {
        console.error("Failed to fetch lights:", error);
        if (lightsContent)
          lightsContent.textContent = `Error loading lights: ${error.message}`;
        showToast("Failed to load lights.", "error"); // User-facing action, so toast is okay
      },
      loadingElement:
        lightsContent?.querySelector("#lights-loading-message") ||
        lightsContent,
    });
  }

  /**
   * Fetches and displays the device_mapping.yml content.
   * Uses /api/config/mapping and expects text, displaying it directly.
   */
  function fetchMappingContent() {
    fetchData(`${apiBasePath}/config/mapping`, {
      // Changed to /api/config/mapping
      responseType: "text", // Expect text
      successCallback: (textData) => {
        if (mappingContent) {
          mappingContent.textContent = textData; // Display raw text
        }
      },
      errorCallback: (error) => {
        console.error("Failed to fetch mapping content:", error);
        if (mappingContent)
          mappingContent.textContent = `Error loading mapping: ${error.message}`;
        showToast("Failed to load device mapping.", "error");
      },
      loadingElement: mappingContent,
    });
  }

  /**
   * Updates the specification text view.
   * @param {string} textData - The RVC specification text (JSON string).
   */
  function updateSpecTextView(textData) {
    if (specContent) {
      specContent.textContent = textData;
    }
  }

  /**
   * Updates the specification metadata view.
   * @param {object} metadata - The RVC specification metadata.
   * @param {string} [metadata.version] - Specification version.
   * @param {string} [metadata.source] - Specification source/document URL.
   */
  function updateSpecMetadataView(metadata) {
    if (specMetadataDiv) {
      if (
        metadata &&
        (metadata.version || metadata.source || metadata.spec_document)
      ) {
        // Check spec_document too
        specMetadataDiv.innerHTML = `
          Version: ${metadata.version || "N/A"}<br>
          Source: ${metadata.spec_document || metadata.source || "N/A"}
        `;
      } else {
        specMetadataDiv.textContent = "Specification metadata not available.";
      }
    }
  }

  /**
   * Fetches and displays the rvc.json specification content and metadata.
   * Fetches content from /api/config/rvc_spec (text)
   * Fetches metadata from /api/config/rvc_spec_metadata (JSON)
   */
  function fetchSpecContent() {
    // Fetch Spec Content (Text)
    fetchData(`${apiBasePath}/config/rvc_spec`, {
      responseType: "text",
      successCallback: updateSpecTextView,
      errorCallback: (error) => {
        console.error("Failed to fetch spec content:", error);
        if (specContent)
          specContent.textContent = `Error loading RVC spec content: ${error.message}`;
        showToast("Failed to load RVC specification content.", "error");
      },
      loadingElement: specContent, // Use specContent for its loading message
    });

    // Fetch Spec Metadata (JSON)
    fetchData(`${apiBasePath}/config/rvc_spec_metadata`, {
      responseType: "json",
      successCallback: updateSpecMetadataView,
      errorCallback: (error) => {
        console.error("Failed to fetch spec metadata:", error);
        if (specMetadataDiv)
          specMetadataDiv.textContent = "Error loading RVC spec metadata.";
        // Do not show a toast for metadata if the primary content toast is already shown
        // showToast("Failed to load RVC specification metadata.", "error");
      },
      // No separate loading element for metadata, or use specMetadataDiv if it has one
    });
  }

  /**
   * Renders unmapped CAN entries with YAML suggestion and copy-to-clipboard button.
   * @param {object} data - The unmapped entries data from the API.
   */
  function renderUnmappedEntries(data) {
    if (!unmappedEntriesContent) return;
    unmappedEntriesContent.innerHTML = "";
    if (Object.keys(data).length === 0) {
      unmappedEntriesContent.innerHTML =
        '<p class="text-gray-500">No unmapped entries found. Good job!</p>';
      return;
    }
    for (const [key, entry] of Object.entries(data)) {
      const entryDiv = document.createElement("div");
      entryDiv.className = "bg-gray-800 p-4 rounded-lg shadow mb-4";
      // YAML suggestion (reuse original logic or a simplified version)
      const yamlSuggestion = generateYamlSuggestion(entry);
      entryDiv.innerHTML = `
        <h3 class="text-xl font-semibold text-yellow-400 mb-2">Unmapped Key: ${key}</h3>
        <div class="mb-3">
          <p class="font-semibold mb-1">Suggested device_mapping.yml entry:</p>
          <pre class="bg-gray-900 text-green-300 p-3 rounded overflow-auto text-xs whitespace-pre-wrap"><code class="language-yaml">${yamlSuggestion}</code></pre>
          <button class="mt-2 bg-blue-600 hover:bg-blue-500 text-white py-1 px-3 rounded text-xs copy-yaml-btn">Copy YAML</button>
        </div>
      `;
      unmappedEntriesContent.appendChild(entryDiv);
    }
    // Add event listeners to copy buttons
    unmappedEntriesContent
      .querySelectorAll(".copy-yaml-btn")
      .forEach((button) => {
        button.addEventListener("click", (event) => {
          const yamlText =
            event.target.previousElementSibling.querySelector("code").innerText;
          navigator.clipboard
            .writeText(yamlText)
            .then(() => {
              event.target.textContent = "Copied!";
              showToast("YAML copied to clipboard!", "success");
              setTimeout(() => {
                event.target.textContent = "Copy YAML";
              }, 2000);
            })
            .catch((err) => {
              showToast("Failed to copy YAML.", "error");
              event.target.textContent = "Failed to copy";
              setTimeout(() => {
                event.target.textContent = "Copy YAML";
              }, 2000);
            });
        });
      });
  }

  /**
   * Generates a YAML suggestion for an unmapped CAN entry.
   * @param {object} entry - The unmapped entry object.
   * @returns {string} YAML suggestion string.
   */
  function generateYamlSuggestion(entry) {
    const dgnKey = entry.dgn_hex;
    const instanceKey = String(entry.instance);
    const dgnForId = dgnKey.toLowerCase();
    const instanceForId = instanceKey.replace(/[^a-z0-9_]/g, "");
    let suggestedEntityId = `unmapped_${dgnForId}_inst${instanceForId}`;
    let yaml = `# Suggested entry for DGN: ${dgnKey}${
      entry.dgn_name ? " (" + entry.dgn_name + ")" : ""
    }, Instance: ${instanceKey}\n`;
    if (entry.pgn_hex && entry.pgn_hex !== entry.dgn_hex) {
      yaml += `# Original PGN from Arbitration ID: ${entry.pgn_hex}${
        entry.pgn_name ? " (" + entry.pgn_name + ")" : ""
      }\n`;
    }
    yaml += `# First seen: ${new Date(
      entry.first_seen_timestamp * 1000
    ).toLocaleString()}\n`;
    yaml += `# Last seen: ${new Date(
      entry.last_seen_timestamp * 1000
    ).toLocaleString()}\n`;
    yaml += `# Count: ${entry.count}\n`;
    yaml += `# Last Data: ${entry.last_data_hex}\n`;
    if (
      entry.decoded_signals &&
      Object.keys(entry.decoded_signals).length > 0
    ) {
      yaml += `# Decoded Signals (from PGN ${entry.pgn_hex}):\n`;
      for (const [key, value] of Object.entries(entry.decoded_signals)) {
        yaml += `#   ${key}: ${value}\n`;
      }
    }
    if (entry.spec_entry && entry.spec_entry.name) {
      yaml += `# Matched Spec Entry Name (for DGN): ${entry.spec_entry.name}\n`;
    }
    yaml += `\n`;
    yaml += `${dgnKey}:\n`;
    yaml += `  ${instanceKey}:\n`;
    yaml += `    - entity_id: "${suggestedEntityId}" # TODO: MUST be unique. Change to a descriptive name (e.g., 'living_room_thermostat')\n`;
    yaml += `      friendly_name: "Unmapped ${
      entry.dgn_name || dgnKey
    } Inst ${instanceKey}" # TODO: Set a user-friendly name (e.g., 'Living Room Thermostat')\n`;
    yaml += `      suggested_area: "Unknown Area" # TODO: Assign an area (e.g., 'Living Room', 'Bedroom')\n`;
    yaml += `      device_type: "unknown" # TODO: Specify type (e.g., light, sensor, hvac, lock, switch, tank)\n`;
    yaml += `      capabilities: [] # TODO: Define capabilities (e.g., [on_off], [on_off, brightness], [lock_unlock], [temperature])\n`;
    yaml += `      # --- Optional fields based on device_type and system needs ---\n`;
    yaml += `      # interface: canX # TODO: Specify CAN interface if known (e.g., can0, can1)\n`;
    yaml += `      # status_dgn: '${dgnKey}' # Status DGN is typically this DGN key\n`;
    yaml += `      # command_pgn: 'YYYYY' # TODO: If controllable and different from status DGN, specify command PGN\n`;
    yaml += `      # group_mask: '0xXX' # TODO: If part of a command/status group\n`;
    yaml += `      # --- Example for using a YAML template (if defined in your mapping file) ---\n`;
    yaml += `      # <<: *switchable_light  # For on/off lights, if &switchable_light template exists\n`;
    yaml += `      # <<: *dimmable_light   # For dimmable lights, if &dimmable_light template exists\n`;
    return yaml;
  }

  // Patch fetchUnmappedEntries to use the new renderer
  function fetchUnmappedEntries() {
    fetchData(`${apiBasePath}/unmapped_entries`, {
      successCallback: renderUnmappedEntries,
      errorCallback: (error) => {
        if (unmappedEntriesContent)
          unmappedEntriesContent.textContent = `Error loading unmapped entries: ${error.message}`;
        showToast("Failed to load unmapped entries.", "error");
      },
      loadingElement:
        unmappedEntriesContent?.querySelector("#unmapped-loading-message") ||
        unmappedEntriesContent,
    });
  }

  /**
   * Fetches and displays unknown PGNs.
   * Uses /api/unknown_pgns as per user's note.
   */
  function fetchUnknownPgns() {
    fetchData(`${apiBasePath}/unknown_pgns`, {
      // New endpoint (corrected)
      successCallback: (data) => {
        if (!unknownPgnsContent) return;
        unknownPgnsContent.innerHTML = ""; // Clear previous
        if (Object.keys(data).length === 0) {
          unknownPgnsContent.innerHTML = "<p>No unknown PGNs found.</p>";
          return;
        }
        // ... (Render unknown PGNs - similar to unmapped or simpler list) ...
        const ul = createDomElement("ul");
        for (const pgn in data) {
          const item = data[pgn];
          ul.appendChild(
            createDomElement("li", {
              textContent: `PGN: ${pgn}, Count: ${
                item.count
              }, Last Seen: ${new Date(
                item.last_seen_timestamp * 1000
              ).toLocaleString()}`,
            })
          );
        }
        unknownPgnsContent.appendChild(ul);
      },
      errorCallback: (error) => {
        console.error("Failed to fetch unknown PGNs:", error);
        if (unknownPgnsContent)
          unknownPgnsContent.textContent = `Error loading unknown PGNs: ${error.message}`;
        showToast("Failed to load unknown PGNs.", "error");
      },
      loadingElement:
        unknownPgnsContent?.querySelector("#unknown-pgns-loading-message") ||
        unknownPgnsContent,
    });
  }

  // =====================
  // WEBSOCKET HANDLERS
  // =====================
  /**
   * Appends a log message to the log stream.
   * @param {string} message - The raw log message string.
   */
  function appendLogMessage(message) {
    if (!logStream || isLogPaused) return;

    const currentFilterLevel = logLevelSelect.value.toUpperCase();
    const searchTerm = logSearchInput.value.toLowerCase();

    // Updated regex for log format: 2025-05-10 23:49:28,569 DEBUG core_daemon.can_processing: ...
    const parts = message.match(
      /^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3}) (\w+) ([^:]+): (.*)/
    );
    let timestamp = "",
      level = "UNKNOWN",
      msgContent = message;

    if (parts) {
      timestamp = parts[1];
      level = parts[2].toUpperCase();
      msgContent = parts[4];
    }

    if (LOG_LEVELS[level] < LOG_LEVELS[currentFilterLevel]) {
      return;
    }
    if (searchTerm && !message.toLowerCase().includes(searchTerm)) {
      return;
    }

    const lineDiv = createDomElement("div", { className: "log-line" });
    const timeSpan = createDomElement("span", {
      className: "log-timestamp",
      textContent: timestamp,
    });
    const levelSpan = createDomElement("span", {
      className: `log-level-tag log-level-${level.toLowerCase()}`,
      textContent: level,
    });
    const msgSpan = createDomElement("span", {
      className: "log-message",
      textContent: msgContent,
    });

    // Add copy icon/button for the message
    const copyButton = createDomElement("button", {
      className: "log-copy-btn ml-2 text-gray-500 hover:text-gray-300",
      innerHTML: ICON_COPY + "Copy",
      attributes: { title: "Copy log message" },
    });
    copyButton.addEventListener("click", () => {
      navigator.clipboard
        .writeText(message)
        .then(() => showToast("Log message copied!", "success", 1500))
        .catch((err) => {
          console.error("Failed to copy log message:", err);
          showToast("Failed to copy log message.", "error", 1500);
        });
    });

    lineDiv.appendChild(timeSpan);
    lineDiv.appendChild(levelSpan);
    lineDiv.appendChild(msgSpan);
    lineDiv.appendChild(copyButton);
    logStream.appendChild(lineDiv);

    // Auto-scroll if near the bottom
    if (
      logStream.scrollHeight - logStream.scrollTop - logStream.clientHeight <
      100
    ) {
      logStream.scrollTop = logStream.scrollHeight;
    }

    setLogsWaitingMessage(false); // Hide waiting message on new log
  }

  /**
   * Connects to the log WebSocket.
   */
  function connectLogSocket() {
    console.log("[LOG DRAWER] connectLogSocket called. logSocket:", logSocket);
    if (logSocket && logSocket.readyState === WebSocket.OPEN) {
      console.log("[LOG DRAWER] WebSocket already open.");
      return;
    }
    if (
      logSocket &&
      (logSocket.readyState === WebSocket.CONNECTING ||
        logSocket.readyState === WebSocket.CLOSING)
    ) {
      console.log("[LOG DRAWER] Closing previous WebSocket before opening new one.");
      logSocket.close();
    }

    // FIX: Use /api/ws/logs to match backend router prefix
    logSocket = new WebSocket(`ws://${location.host}/api/ws/logs`);
    console.log("[LOG DRAWER] WebSocket created:", logSocket);

    logSocket.onopen = () => {
      console.log("[LOG DRAWER] Log WebSocket connected.");
      showToast("Log stream connected.", "info", 2000);
      if (
        logStream &&
        logStream.children.length === 0 &&
        pinnedLogsContent &&
        !pinnedLogsContent.classList.contains(CLASS_HIDDEN)
      ) {
        setLogsWaitingMessage(true);
      }
    };

    logSocket.onmessage = (event) => {
      appendLogMessage(event.data);
    };

    logSocket.onerror = (error) => {
      console.error("[LOG DRAWER] Log WebSocket error:", error);
      showToast("Log stream error.", "error");
    };

    logSocket.onclose = (event) => {
      console.log(
        "[LOG DRAWER] Log WebSocket disconnected. Code:",
        event.code,
        "Reason:",
        event.reason
      );
      showToast("Log stream disconnected.", "warning");
      // Optional: implement reconnect logic
      // setTimeout(connectLogSocket, LOG_WEBSOCKET_RECONNECT_INTERVAL);
    };
  }

  /**
   * Disconnects the log WebSocket.
   */
  function disconnectLogSocket() {
    console.log("[LOG DRAWER] disconnectLogSocket called. logSocket:", logSocket);
    if (logSocket) {
      logSocket.close();
      logSocket = null;
      console.log("[LOG DRAWER] Log WebSocket intentionally disconnected.");
    }
  }

  /**
   * Connects to the entity WebSocket for real-time updates.
   */
  function connectEntitySocket() {
    if (entitySocket && entitySocket.readyState === WebSocket.OPEN) {
      // console.log("Entity WebSocket already connected.");
      return;
    }
    entitySocket = new WebSocket(entitySocketUrl);

    entitySocket.onopen = () => {
      console.log("Entity WebSocket connected.");
      // Potentially request full state if needed, or rely on initial HTTP load
    };

    entitySocket.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);
        // console.log("Entity WS message received:", message);

        if (message.event_type === "state_changed" && message.data) {
          const entity = message.data;
          if (
            entity.device_type === "light" ||
            currentLightStates.hasOwnProperty(entity.entity_id)
          ) {
            // Update local state
            currentLightStates[entity.entity_id] = {
              ...currentLightStates[entity.entity_id],
              ...entity,
            };

            // If lights view is active, update the specific card
            if (
              currentView === "lights" &&
              !lightsView.classList.contains("hidden")
            ) {
              const card = lightsContent.querySelector(
                `[data-entity-id="${entity.entity_id}"]`
              );
              if (card) {
                const newCard = renderLightCard(
                  currentLightStates[entity.entity_id]
                );
                card.replaceWith(newCard);
              } else {
                // If card doesn't exist (e.g. new light or filter changed), re-render all
                renderGroupedLights();
              }
            }
          }
        } else if (message.event_type === "entity_registered" && message.data) {
          const entity = message.data;
          if (entity.device_type === "light") {
            currentLightStates[entity.entity_id] = entity;
            if (
              currentView === "lights" &&
              !lightsView.classList.contains("hidden")
            ) {
              updateAreaFilterForLights(currentLightStates); // Update filter if new area appears
              renderGroupedLights(); // Re-render to include the new light
            }
          }
        } else if (message.event_type === "entity_removed") {
          const entityId = message.entity_id;
          if (currentLightStates.hasOwnProperty(entityId)) {
            delete currentLightStates[entityId];
            if (
              currentView === "lights" &&
              !lightsView.classList.contains("hidden")
            ) {
              updateAreaFilterForLights(currentLightStates); // Update filter if area disappears
              renderGroupedLights(); // Re-render to remove the light
            }
          }
        }
      } catch (error) {
        console.error("Error processing entity WebSocket message:", error);
      }
    };

    entitySocket.onerror = (error) => {
      console.error("Entity WebSocket error:", error);
      showToast("Entity connection error.", "error");
    };

    entitySocket.onclose = (event) => {
      console.log("Entity WebSocket disconnected.", event.reason);
      // Optional: implement reconnection logic if desired
      // showToast("Entity connection closed.", "warning");
    };
  }

  function disconnectEntitySocket() {
    if (entitySocket) {
      entitySocket.close();
      entitySocket = null;
      console.log("Entity WebSocket intentionally disconnected.");
    }
  }

  // =====================
  // UI EVENT HANDLERS & INIT
  // =====================
  /**
   * Navigates to the specified view.
   * @param {string} viewName - The name of the view to navigate to (e.g., "home", "lights").
   * @param {boolean} [isInitial=false] - True if this is the initial page load.
   */
  function navigateToView(viewName, isInitial = false) {
    views.forEach((v) => v.classList.add(CLASS_HIDDEN));
    const targetView = document.getElementById(`${viewName}-view`);

    if (targetView) {
      targetView.classList.remove(CLASS_HIDDEN);
      currentView = viewName;
    } else {
      console.warn(`View "${viewName}" not found, defaulting to home.`);
      homeView?.classList.remove(CLASS_HIDDEN);
      currentView = "home"; // Fallback
    }

    navLinks.forEach((link) => {
      if (link.getAttribute(ATTR_DATA_VIEW) === currentView) {
        link.classList.add(CLASS_ACTIVE_NAV);
        link.setAttribute("aria-current", "page");
      } else {
        link.classList.remove(CLASS_ACTIVE_NAV);
        link.removeAttribute("aria-current");
      }
    });

    // Fetch data for the current view
    console.log(`Navigating to view: ${currentView}, initial: ${isInitial}`);
    switch (currentView) {
      case "home":
        fetchApiStatus();
        fetchAppHealth();
        fetchCanStatus(); // Already exists, ensure it's called
        // Any other home-specific fetches
        break;
      case "lights":
        updateLightsView();
        connectEntitySocket(); // Connect when lights view is active
        break;
      case "mapping":
        fetchMappingContent();
        break;
      case "spec":
        fetchSpecContent();
        // fetchSpecMetadata(); // Combined into fetchSpecContent if API supports
        break;
      case "unmapped":
        fetchUnmappedEntries();
        break;
      case "unknown-pgns":
        fetchUnknownPgns();
        break;
    }
    // Close mobile sidebar if open
    if (
      window.innerWidth < MD_BREAKPOINT_PX &&
      sidebar &&
      !sidebar.classList.contains("-translate-x-full")
    ) {
      sidebar.classList.add("-translate-x-full");
    }
  }

  /**
   * Sets the visibility and state of the desktop sidebar.
   * @param {boolean} expanded - True to expand the sidebar, false to collapse.
   */
  function setDesktopSidebarVisible(expanded) {
    isDesktopSidebarExpanded = expanded;
    localStorage.setItem(DESKTOP_SIDEBAR_EXPANDED_KEY, expanded);

    if (
      !sidebar ||
      !mainContent ||
      !toggleSidebarDesktopButton ||
      !sidebarNavContent
    )
      return;

    const icon = toggleSidebarDesktopButton.querySelector("i");
    const span = toggleSidebarDesktopButton.querySelector("span");

    if (expanded) {
      sidebar.classList.remove(SIDEBAR_COLLAPSED_WIDTH_DESKTOP);
      sidebar.classList.add(SIDEBAR_EXPANDED_WIDTH_DESKTOP);
      mainContent.classList.remove(MAIN_CONTENT_MARGIN_COLLAPSED_DESKTOP);
      mainContent.classList.add(MAIN_CONTENT_MARGIN_EXPANDED_DESKTOP);
      if (icon) icon.className = "mdi mdi-chevron-left text-xl";
      if (span) span.textContent = "Collapse";
      sidebarNavContent.classList.remove(CLASS_HIDDEN);
      sidebar.classList.remove("sidebar-collapsed-hoverable");
    } else {
      sidebar.classList.remove(SIDEBAR_EXPANDED_WIDTH_DESKTOP);
      sidebar.classList.add(SIDEBAR_COLLAPSED_WIDTH_DESKTOP);
      mainContent.classList.remove(MAIN_CONTENT_MARGIN_EXPANDED_DESKTOP);
      mainContent.classList.add(MAIN_CONTENT_MARGIN_COLLAPSED_DESKTOP);
      if (icon) icon.className = "mdi mdi-chevron-right text-xl";
      if (span) span.textContent = ""; // Or hide span
      sidebarNavContent.classList.add(CLASS_HIDDEN); // Hide nav text when collapsed
      sidebar.classList.add("sidebar-collapsed-hoverable");
    }
    adjustPinnedLogsLayout(); // Adjust pinned logs layout if it's visible
  }

  /**
   * Applies the selected theme to the body.
   * @param {string} themeName - The name of the theme to apply.
   */
  function applyTheme(themeName) {
    if (!VALID_THEMES.includes(themeName)) {
      console.warn(
        `Invalid theme: ${themeName}. Defaulting to ${DEFAULT_THEME}.`
      );
      themeName = DEFAULT_THEME;
    }
    document.body.className = document.body.className.replace(/theme-\S+/g, ""); // Remove old theme
    document.body.classList.add(`theme-${themeName}`);
    localStorage.setItem(SELECTED_THEME_KEY, themeName);
    currentTheme = themeName;
    if (themeSwitcher) themeSwitcher.value = themeName;
    console.log(`Theme applied: ${themeName}`);
  }

  /**
   * Sets up event listeners for bulk light control buttons (All/Interior/Exterior On/Off).
   * Each button fetches all lights, filters by group/area, and sends control commands to each.
   */
  function setupBulkLightControlButtons() {
    const controls = [
      {
        id: "btn-all-on",
        name: "All Lights On",
        filter: () => true,
        command: { command: "set", state: "on" },
      },
      {
        id: "btn-all-off",
        name: "All Lights Off",
        filter: () => true,
        command: { command: "set", state: "off" },
      },
      {
        id: "btn-interior-on",
        name: "Interior Lights On",
        filter: (entity) => (entity.groups || []).includes("interior"),
        command: { command: "set", state: "on" },
      },
      {
        id: "btn-interior-off",
        name: "Interior Lights Off",
        filter: (entity) => (entity.groups || []).includes("interior"),
        command: { command: "set", state: "off" },
      },
      {
        id: "btn-exterior-on",
        name: "Exterior Lights On",
        filter: (entity) => (entity.groups || []).includes("exterior"),
        command: { command: "set", state: "on" },
      },
      {
        id: "btn-exterior-off",
        name: "Exterior Lights Off",
        filter: (entity) => (entity.groups || []).includes("exterior"),
        command: { command: "set", state: "off" },
      },
    ];
    controls.forEach((control) => {
      const button = document.getElementById(control.id);
      if (!button) return;
      button.addEventListener("click", async () => {
        const originalHTML = button.innerHTML;
        button.disabled = true;
        button.innerHTML =
          '<i class="mdi mdi-loading mdi-spin mr-2"></i>Processing...';
        try {
          // Fetch all lights
          const resp = await fetch(`${apiBasePath}/entities?type=light`);
          if (!resp.ok) throw new Error("Failed to fetch lights");
          const lights = await resp.json();
          // Filter lights for this control
          const entities = Object.values(lights).filter(
            (entity) => entity.device_type === "light" && control.filter(entity)
          );
          if (entities.length === 0) {
            showToast(`No lights found for ${control.name}.`, "warning");
            return;
          }
          // Send control command to each entity
          let successCount = 0;
          let errorCount = 0;
          for (const entity of entities) {
            try {
              const res = await fetch(
                `${apiBasePath}/entities/${entity.entity_id}/control`,
                {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify(control.command),
                }
              );
              if (!res.ok) throw new Error(await res.text());
              successCount++;
            } catch (err) {
              errorCount++;
              console.error(`Failed to control ${entity.entity_id}:`, err);
            }
          }
          if (errorCount > 0) {
            showToast(
              `${control.name}: ${successCount} succeeded, ${errorCount} failed.`,
              errorCount === entities.length ? "error" : "warning"
            );
          } else {
            showToast(
              `${control.name}: ${successCount} lights commanded.`,
              "success"
            );
          }
        } catch (error) {
          showToast(
            `Failed to execute ${control.name}. Error: ${error.message}`,
            "error"
          );
          console.error(`Command ${control.name} failed:`, error);
        } finally {
          button.disabled = false;
          button.innerHTML = originalHTML;
        }
      });
    });
  }

  /**
   * Enables drag-to-resize for the pinned logs panel, with persistent height in localStorage.
   * Restores height and open/closed state on load, and clamps to min/max values.
   * Adds comprehensive comments and JSDoc.
   */
  function setupPinnedLogsResizablePanel() {
    const PINNED_LOGS_OPEN_KEY = "pinnedLogsOpen";
    const PINNED_LOGS_HEIGHT_KEY = "pinnedLogsHeight";
    const COLLAPSED_LOGS_HEIGHT = "3rem";
    const DEFAULT_EXPANDED_LOGS_HEIGHT_VH = 30;
    const MIN_LOGS_PANEL_HEIGHT_PX = 80;
    const MAX_LOGS_PANEL_HEIGHT_VH_PERCENT = 80;
    let currentExpandedLogsHeight = `${DEFAULT_EXPANDED_LOGS_HEIGHT_VH}vh`;
    let isResizingLogs = false;
    let resizeRafId = null;
    let pendingResizeHeightPx = 0;
    let originalContainerTransition = "";

    if (
      !pinnedLogsContainer ||
      !pinnedLogsResizeHandle ||
      !pinnedLogsContent ||
      !mainContent
    )
      return;

    // Restore state from localStorage (only once on page load)
    const savedIsOpen = localStorage.getItem(PINNED_LOGS_OPEN_KEY) === "true";
    const savedHeight = localStorage.getItem(PINNED_LOGS_HEIGHT_KEY);
    if (savedHeight) {
      let heightNum = parseFloat(savedHeight);
      const unit = savedHeight.replace(/[\d.-]/g, "");
      if (unit === "px") {
        heightNum = Math.max(
          MIN_LOGS_PANEL_HEIGHT_PX,
          Math.min(
            heightNum,
            window.innerHeight * (MAX_LOGS_PANEL_HEIGHT_VH_PERCENT / 100)
          )
        );
        currentExpandedLogsHeight = `${heightNum}px`;
      } else if (unit === "vh") {
        heightNum = Math.max(
          (MIN_LOGS_PANEL_HEIGHT_PX / window.innerHeight) * 100,
          Math.min(heightNum, MAX_LOGS_PANEL_HEIGHT_VH_PERCENT)
        );
        currentExpandedLogsHeight = `${heightNum}vh`;
      } else {
        currentExpandedLogsHeight = `${DEFAULT_EXPANDED_LOGS_HEIGHT_VH}vh`;
      }
    }

    // Set initial state ONCE, do not call setPinnedLogsState again unless user toggles
    const originalTransition = pinnedLogsContainer.style.transition;
    pinnedLogsContainer.style.transition = "none";
    setPinnedLogsState(savedIsOpen, currentExpandedLogsHeight);
    setTimeout(() => {
      pinnedLogsContainer.style.transition =
        originalTransition || "height 0.3s ease-in-out";
    }, 50);

    function setPinnedLogsState(isOpen, height) {
      console.log(`[LOG DRAWER] setPinnedLogsState called. isOpen: ${isOpen}, height: ${height}`);
      localStorage.setItem(PINNED_LOGS_OPEN_KEY, isOpen);
      if (isOpen && height) {
        localStorage.setItem(PINNED_LOGS_HEIGHT_KEY, height);
        currentExpandedLogsHeight = height;
      }
      if (isOpen) {
        pinnedLogsContent.classList.remove(CLASS_HIDDEN);
        pinnedLogsContainer.style.height = currentExpandedLogsHeight;
        pinnedLogsContent.style.height = `calc(${currentExpandedLogsHeight} - ${COLLAPSED_LOGS_HEIGHT})`;
        mainContent.style.paddingBottom = currentExpandedLogsHeight;
        const chevron = togglePinnedLogsButton.querySelector("i");
        if (chevron) {
          chevron.className = "mdi mdi-chevron-down text-2xl";
        }
        console.log("[LOG DRAWER] Opening drawer, calling connectLogSocket()");
        connectLogSocket();
      } else {
        pinnedLogsContent.classList.add(CLASS_HIDDEN);
        pinnedLogsContainer.style.height = COLLAPSED_LOGS_HEIGHT;
        mainContent.style.paddingBottom = COLLAPSED_LOGS_HEIGHT;
        const chevron = togglePinnedLogsButton.querySelector("i");
        if (chevron) {
          chevron.className = "mdi mdi-chevron-up text-2xl";
        }
        console.log("[LOG DRAWER] Closing drawer, calling disconnectLogSocket()");
        disconnectLogSocket();
      }
      adjustPinnedLogsLayout();
    }

    // Drag-to-resize logic
    pinnedLogsResizeHandle.addEventListener("mousedown", (e) => {
      if (pinnedLogsContent.classList.contains(CLASS_HIDDEN)) return;
      e.preventDefault();
      isResizingLogs = true;
      const startY = e.clientY;
      const startHeight = pinnedLogsContainer.offsetHeight;
      originalContainerTransition = pinnedLogsContainer.style.transition;
      pinnedLogsContainer.style.transition = "none";
      document.body.style.userSelect = "none";
      document.body.style.cursor = "ns-resize";
      const onMouseMove = (moveEvent) => {
        if (!isResizingLogs) return;
        const dy = startY - moveEvent.clientY;
        let newHeightPx = startHeight + dy;
        const maxHeightPx =
          window.innerHeight * (MAX_LOGS_PANEL_HEIGHT_VH_PERCENT / 100);
        newHeightPx = Math.max(
          MIN_LOGS_PANEL_HEIGHT_PX,
          Math.min(newHeightPx, maxHeightPx)
        );
        pendingResizeHeightPx = newHeightPx;
        if (resizeRafId === null) {
          resizeRafId = requestAnimationFrame(() => {
            currentExpandedLogsHeight = `${pendingResizeHeightPx}px`;
            pinnedLogsContainer.style.height = currentExpandedLogsHeight;
            pinnedLogsContent.style.height = `calc(${currentExpandedLogsHeight} - ${COLLAPSED_LOGS_HEIGHT})`;
            mainContent.style.paddingBottom = currentExpandedLogsHeight;
            resizeRafId = null;
          });
        }
      };
      const onMouseUp = () => {
        if (isResizingLogs) {
          isResizingLogs = false;
          document.removeEventListener("mousemove", onMouseMove);
          document.removeEventListener("mouseup", onMouseUp);
          if (resizeRafId !== null) {
            cancelAnimationFrame(resizeRafId);
            resizeRafId = null;
          }
          currentExpandedLogsHeight = `${pendingResizeHeightPx}px`;
          pinnedLogsContainer.style.height = currentExpandedLogsHeight;
          pinnedLogsContent.style.height = `calc(${currentExpandedLogsHeight} - ${COLLAPSED_LOGS_HEIGHT})`;
          mainContent.style.paddingBottom = currentExpandedLogsHeight;
          localStorage.setItem(
            PINNED_LOGS_HEIGHT_KEY,
            currentExpandedLogsHeight
          );
          document.body.style.userSelect = "";
          document.body.style.cursor = "";
          pinnedLogsContainer.style.transition =
            originalContainerTransition || "height 0.3s ease-in-out";
        }
      };
      document.addEventListener("mousemove", onMouseMove);
      document.addEventListener("mouseup", onMouseUp);
    });

    // --- Toggle logic: only call setPinnedLogsState in response to user actions ---
    if (togglePinnedLogsButton && pinnedLogsHeader) {
      togglePinnedLogsButton.addEventListener("click", () => {
        const isOpen = !pinnedLogsContent.classList.contains(CLASS_HIDDEN);
        // Only toggle state in response to user click
        setPinnedLogsState(!isOpen, currentExpandedLogsHeight);
      });
      pinnedLogsHeader.addEventListener("click", (e) => {
        if (
          e.target === pinnedLogsHeader ||
          (pinnedLogsHeader.contains(e.target) && e.target.tagName !== "BUTTON")
        ) {
          const isOpen = !pinnedLogsContent.classList.contains(CLASS_HIDDEN);
          setPinnedLogsState(!isOpen, currentExpandedLogsHeight);
        }
      });
    }

    // Responsive: clamp height on window resize
    window.addEventListener("resize", () => {
      const maxHeightPx =
        window.innerHeight * (MAX_LOGS_PANEL_HEIGHT_VH_PERCENT / 100);
      let heightNum = parseFloat(currentExpandedLogsHeight);
      if (currentExpandedLogsHeight.endsWith("px")) {
        heightNum = Math.max(
          MIN_LOGS_PANEL_HEIGHT_PX,
          Math.min(heightNum, maxHeightPx)
        );
        currentExpandedLogsHeight = `${heightNum}px`;
      } else if (currentExpandedLogsHeight.endsWith("vh")) {
        heightNum = Math.max(
          (MIN_LOGS_PANEL_HEIGHT_PX / window.innerHeight) * 100,
          Math.min(heightNum, MAX_LOGS_PANEL_HEIGHT_VH_PERCENT)
        );
        currentExpandedLogsHeight = `${heightNum}vh`;
      }
      if (!pinnedLogsContent.classList.contains(CLASS_HIDDEN)) {
        pinnedLogsContainer.style.height = currentExpandedLogsHeight;
        pinnedLogsContent.style.height = `calc(${currentExpandedLogsHeight} - ${COLLAPSED_LOGS_HEIGHT})`;
        mainContent.style.paddingBottom = currentExpandedLogsHeight;
      }
      adjustPinnedLogsLayout();
    });
  }

  /**
   * Shows or hides the "Waiting for logs..." message in the pinned logs panel.
   * @param {boolean} show - Whether to show the waiting message.
   */
  function setLogsWaitingMessage(show) {
    const logsWaitingMessage = document.getElementById("logs-waiting-message");
    if (!logsWaitingMessage) return;
    if (show) {
      logsWaitingMessage.classList.remove(CLASS_HIDDEN);
    } else {
      logsWaitingMessage.classList.add(CLASS_HIDDEN);
    }
  }

  // Patch log controls to show/hide waiting message on clear/filter/search
  if (logClearButton)
    logClearButton.addEventListener("click", () => {
      if (logStream) logStream.innerHTML = "";
      if (
        logSocket &&
        logSocket.readyState === WebSocket.OPEN &&
        pinnedLogsContent &&
        !pinnedLogsContent.classList.contains(CLASS_HIDDEN)
      ) {
        setLogsWaitingMessage(true);
      }
    });
  if (logLevelSelect)
    logLevelSelect.addEventListener("change", () => {
      if (logStream) logStream.innerHTML = "";
      if (
        logSocket &&
        logSocket.readyState === WebSocket.OPEN &&
        pinnedLogsContent &&
        !pinnedLogsContent.classList.contains(CLASS_HIDDEN)
      ) {
        setLogsWaitingMessage(true);
      }
    });
  if (logSearchInput)
    logSearchInput.addEventListener("input", () => {
      if (logStream) logStream.innerHTML = "";
      if (
        logSocket &&
        logSocket.readyState === WebSocket.OPEN &&
        pinnedLogsContent &&
        !pinnedLogsContent.classList.contains(CLASS_HIDDEN)
      ) {
        setLogsWaitingMessage(true);
      }
    });

  /**
   * Enhances sidebar collapse/expand/hover behavior.
   * - Click-to-expand on collapsed sidebar (desktop)
   * - Robust state save/restore in localStorage
   * - Maintains ARIA and accessibility
   */
  function setupSidebarCollapseExpand() {
    if (
      !sidebar ||
      !mainContent ||
      !toggleSidebarDesktopButton ||
      !sidebarNavContent
    )
      return;
    // Click-to-expand on collapsed sidebar (desktop only)
    sidebar.addEventListener("click", (e) => {
      const isCollapsedDesktop =
        window.innerWidth >= MD_BREAKPOINT_PX &&
        sidebar.classList.contains(SIDEBAR_COLLAPSED_WIDTH_DESKTOP);
      if (isCollapsedDesktop) {
        setDesktopSidebarVisible(true);
      }
    });
    // Collapse/expand button
    toggleSidebarDesktopButton.addEventListener("click", (e) => {
      e.stopPropagation(); // Prevent bubbling to sidebar
      console.log("Sidebar collapse button clicked");
      setDesktopSidebarVisible(!isDesktopSidebarExpanded);
    });
    // Add ARIA attributes for accessibility
    sidebar.setAttribute(
      "aria-expanded",
      isDesktopSidebarExpanded ? "true" : "false"
    );
    toggleSidebarDesktopButton.setAttribute(
      "aria-expanded",
      isDesktopSidebarExpanded ? "true" : "false"
    );
  }

  /**
   * Updates the area filter dropdown for lights based on the current light entities.
   * Ensures all unique areas are present as options, sorted alphabetically.
   * @param {object} lightEntities - Object of light entities keyed by entity_id.
   */
  function updateAreaFilterForLights(lightEntities) {
    if (!areaFilter) return;
    const currentValue = areaFilter.value;
    const areas = new Set(["All"]);
    Object.values(lightEntities).forEach((e) => {
      if (e.device_type === "light") {
        areas.add(e.suggested_area || "Unknown Area");
      }
    });
    // Remove all options
    while (areaFilter.firstChild) areaFilter.removeChild(areaFilter.firstChild);
    // Add sorted options
    Array.from(areas)
      .sort((a, b) => a.localeCompare(b))
      .forEach((area) => {
        const opt = document.createElement("option");
        opt.value = area;
        opt.textContent = area;
        areaFilter.appendChild(opt);
      });
    // Restore previous selection if possible
    if ([...areas].includes(currentValue)) {
      areaFilter.value = currentValue;
    } else {
      areaFilter.value = "All";
    }
  }

  /**
   * Adjusts the pinned logs drawer position so it does not cover the sidebar.
   * Sets the left offset to match the sidebar width (expanded/collapsed) on desktop.
   * On mobile, sets left to 0.
   * Should be called on sidebar expand/collapse, window resize, and after toggling logs.
   */
  function adjustPinnedLogsLayout() {
    if (!pinnedLogsContainer || !sidebar) return;
    if (window.innerWidth < MD_BREAKPOINT_PX) {
      // Mobile: logs bar spans full width
      pinnedLogsContainer.style.left = "0px";
    } else {
      // Desktop: align with sidebar
      const isSidebarCollapsedDesktop = sidebar.classList.contains(
        SIDEBAR_COLLAPSED_WIDTH_DESKTOP
      );
      if (isSidebarCollapsedDesktop) {
        pinnedLogsContainer.style.left = "4rem"; // Collapsed width
      } else {
        pinnedLogsContainer.style.left = "16rem"; // Expanded width
      }
    }
  }

  // =====================
  // APP INITIALIZATION
  // =====================
  /**
   * Initializes the application.
   * Sets up event listeners, loads initial state, and fetches data for the default view.
   */
  function initializeApp() {
    // Read APP_VERSION from body data attribute
    APP_VERSION = document.body.dataset.appVersion || "N/A";
    if (appVersionDisplay) {
      appVersionDisplay.textContent = `v${APP_VERSION}`;
    } else if (appHeader && APP_VERSION !== "N/A") {
      // Fallback to adding it to header
      const versionSpan = createDomElement("span", {
        className: "text-xs text-gray-500 ml-2",
        textContent: `v${APP_VERSION}`,
      });
      appHeader.appendChild(versionSpan);
    }

    // Load and apply theme
    const savedTheme = localStorage.getItem(SELECTED_THEME_KEY);
    applyTheme(savedTheme || DEFAULT_THEME);
    if (themeSwitcher) {
      themeSwitcher.addEventListener("change", (e) =>
        applyTheme(e.target.value)
      );
    }

    // Initialize sidebar state for desktop
    const savedSidebarState = localStorage.getItem(
      DESKTOP_SIDEBAR_EXPANDED_KEY
    );
    setDesktopSidebarVisible(
      savedSidebarState === null ? true : savedSidebarState === "true"
    );

    if (toggleSidebarDesktopButton) {
      toggleSidebarDesktopButton.addEventListener("click", () => {
        setDesktopSidebarVisible(!isDesktopSidebarExpanded);
        // Update ARIA attributes for accessibility
        sidebar.setAttribute(
          "aria-expanded",
          isDesktopSidebarExpanded ? "true" : "false"
        );
        toggleSidebarDesktopButton.setAttribute(
          "aria-expanded",
          isDesktopSidebarExpanded ? "true" : "false"
        );
      });
    }
    if (mobileMenuButton && sidebar && closeSidebarButton) {
      mobileMenuButton.addEventListener("click", () =>
        sidebar.classList.remove("-translate-x-full")
      );
      closeSidebarButton.addEventListener("click", () =>
        sidebar.classList.add("-translate-x-full")
      );
    }

    // Setup navigation
    navLinks.forEach((link) => {
      link.addEventListener("click", (e) => {
        e.preventDefault();
        const viewName = link.getAttribute(ATTR_DATA_VIEW);
        if (viewName) navigateToView(viewName);
      });
    });

    // Initial view loading and data fetching
    // Determine initial view (e.g. from URL hash or default to "home")
    let initialView = "home";
    // TODO: Could add logic to parse window.location.hash for initial view
    navigateToView(initialView, true);

    // Connect Entity WebSocket globally for background updates
    connectEntitySocket();

    // Log controls
    if (logPauseButton)
      logPauseButton.addEventListener("click", () => {
        isLogPaused = true;
        logPauseButton.disabled = true;
        logResumeButton.disabled = false;
      });
    if (logResumeButton)
      logResumeButton.addEventListener("click", () => {
        isLogPaused = false;
        logPauseButton.disabled = false;
        logResumeButton.disabled = true;
        if (logStream) logStream.scrollTop = logStream.scrollHeight;
      });
    if (logClearButton)
      logClearButton.addEventListener("click", () => {
        if (logStream) logStream.innerHTML = "";
        if (
          logSocket &&
          logSocket.readyState === WebSocket.OPEN &&
          pinnedLogsContent &&
          !pinnedLogsContent.classList.contains(CLASS_HIDDEN)
        ) {
          setLogsWaitingMessage(true);
        }
      });
    if (logLevelSelect)
      logLevelSelect.addEventListener("change", () => {
        if (logStream) logStream.innerHTML = "";
        if (
          logSocket &&
          logSocket.readyState === WebSocket.OPEN &&
          pinnedLogsContent &&
          !pinnedLogsContent.classList.contains(CLASS_HIDDEN)
        ) {
          setLogsWaitingMessage(true);
        }
      });
    if (logSearchInput)
      logSearchInput.addEventListener("input", () => {
        if (logStream) logStream.innerHTML = "";
        if (
          logSocket &&
          logSocket.readyState === WebSocket.OPEN &&
          pinnedLogsContent &&
          !pinnedLogsContent.classList.contains(CLASS_HIDDEN)
        ) {
          setLogsWaitingMessage(true);
        }
      });

    // Pinned logs toggle and initial state
    // --- Removed duplicate toggleLogs logic and event listeners from initializeApp ---
    // The log drawer's open/close state and event listeners are now managed only by setupPinnedLogsResizablePanel.

    // Setup periodic data fetching for dashboard items if on home view
    // This will be managed by navigateToView now, but intervals can be set here if needed globally
    // setInterval(fetchCanStatus, CAN_STATUS_REFRESH_INTERVAL); // Example, if always needed
    // setInterval(fetchApiStatus, API_STATUS_REFRESH_INTERVAL);
    // setInterval(fetchAppHealth, APP_HEALTH_REFRESH_INTERVAL);

    setupBulkLightControlButtons();
    setupPinnedLogsResizablePanel();
    setupSidebarCollapseExpand();

    console.log(`rvc2api UI Initialized. Version: ${APP_VERSION}`);
  }

  // Initialize the app when the DOM is fully loaded
  document.addEventListener("DOMContentLoaded", () => {
    initializeApp();
    if (areaFilter) {
      areaFilter.addEventListener("change", renderGroupedLights);
    }
  });
})();
