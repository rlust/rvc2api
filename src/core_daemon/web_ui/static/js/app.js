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

  // Define heights for the pinned logs drawer
  const PINNED_LOGS_COLLAPSED_HEIGHT_REM = "3rem"; // Matches Tailwind h-12
  const PINNED_LOGS_EXPANDED_HEIGHT_REM = "20rem"; // Default expanded height, can be overridden by resize
  const PINNED_LOGS_EXPANDED_ICON = "mdi mdi-chevron-down text-2xl";
  const PINNED_LOGS_COLLAPSED_ICON = "mdi mdi-chevron-up text-2xl";

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
  let isDesktopSidebarExpanded = true; // Track desktop sidebar state
  const currentLightStates = {}; // Store current states of all lights
  // Update: Use /api/ws for the entity WebSocket endpoint to match backend router prefix
  // const entitySocketUrl = `ws://${window.location.host}/api/ws`; // Original
  const entitySocketUrl = `${
    window.location.protocol === "https:" ? "wss:" : "ws:"
  }//${window.location.host}/api/ws`; // More robust scheme

  let canSnifferSocket = null;

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
    try {
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
    } catch (err) {
      console.error("Error in updateApiServerView:", err);
      if (apiStatusContent)
        apiStatusContent.textContent = "Error rendering API status.";
    }
  }

  /**
   * Updates the application health view.
   * Fetches from /api/status/application and displays key health metrics.
   * @param {object} data - Health data with keys as metric names and values as status/counts.
   */
  function updateApplicationHealthView(data) {
    try {
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
    } catch (err) {
      console.error("Error in updateApplicationHealthView:", err);
      if (appHealthContent)
        appHealthContent.textContent = "Error rendering application health.";
    }
  }

  /**
   * Updates the CAN status view.
   * Fetches from /api/can/status and displays CAN interface status.
   * @param {object} data - CAN status data, expected to have an 'interfaces' object.
   */
  function updateCanStatusView(data) {
    try {
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
    } catch (err) {
      console.error("Error in updateCanStatusView:", err);
      if (canStatusContent)
        canStatusContent.textContent = "Error rendering CAN status.";
    }
  }

  /**
   * Updates the lights view with fetched data.
   * @param {object} data - The response from the lights API. Expected to be an object where keys are entity IDs.
   */
  async function updateLightsView() {
    try {
      if (!lightsView.classList.contains("hidden")) {
        // Only fetch if view is active
        if (lightsLoadingMessage)
          lightsLoadingMessage.classList.remove("hidden");
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

          if (lightsLoadingMessage)
            lightsLoadingMessage.classList.add("hidden");
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
    } catch (err) {
      console.error("Error in updateLightsView:", err);
      if (lightsContent) lightsContent.textContent = "Error rendering lights.";
    }
  }

  /**
   * Updates the specification text view.
   * @param {string} textData - The RVC specification text (JSON string).
   */
  function updateSpecTextView(textData) {
    try {
      if (specContent) {
        specContent.textContent = textData;
      }
    } catch (err) {
      console.error("Error in updateSpecTextView:", err);
      if (specContent)
        specContent.textContent = "Error rendering spec content.";
    }
  }

  /**
   * Updates the specification metadata view.
   * @param {object} metadata - The RVC specification metadata.
   * @param {string} [metadata.version] - Specification version.
   * @param {string} [metadata.source] - Specification source/document URL.
   */
  function updateSpecMetadataView(metadata) {
    try {
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
    } catch (err) {
      console.error("Error in updateSpecMetadataView:", err);
      if (specMetadataDiv)
        specMetadataDiv.textContent = "Error rendering spec metadata.";
    }
  }

  /**
   * Renders unmapped CAN entries with YAML suggestion and copy-to-clipboard button.
   * @param {object} data - The unmapped entries data from the API.
   */
  function renderUnmappedEntries(data) {
    try {
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
              event.target.previousElementSibling.querySelector(
                "code"
              ).innerText;
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
    } catch (err) {
      console.error("Error in renderUnmappedEntries:", err);
      if (unmappedEntriesContent)
        unmappedEntriesContent.textContent =
          "Error rendering unmapped entries.";
    }
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
    return new Promise((resolve) => {
      fetchData(path, {
        method: "POST",
        body,
        successCallback: (responseData) => {
          showToast(`${entityId} ${command} command sent.`, "info", 2000);
          resolve(responseData);
        },
        errorCallback: (error) => {
          showToast(`Error: ${error.message || "Request failed"}`, "error");
          resolve(null);
        },
        showToastOnError: false,
      });
    });
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
    const entityState = (entity.state || "unknown").toLowerCase(); // Use local var for clarity and ensure lowercase
    const capabilities = entity.capabilities || [];
    // const rawAttrs = entity.raw_attributes || {}; // Old way
    const rawAttrs = entity.raw || {}; // Corrected: entity.raw is part of the WebSocket payload

    card.classList.toggle("light-on", entityState === "on");
    card.classList.toggle("light-off", entityState !== "on");

    let cardContent = `<h3 class="text-lg font-semibold">${friendlyName}</h3>`;
    // Removed State: on/off text as per user request
    // cardContent += `<p class="text-sm">State: <span class="font-medium state-text">${entityState}</span></p>`;

    const hasBrightness = capabilities.includes("brightness");

    if (hasBrightness) {
      let currentBrightnessPercent = 0;

      if (entityState === "on") {
        // Prefer value.operating_status (string "0"-"100") if available from WebSocket payload
        if (entity.value && typeof entity.value.operating_status === "string") {
          currentBrightnessPercent = parseInt(
            entity.value.operating_status,
            10
          );
        }
        // Fallback to raw.operating_status (number, CAN level e.g. 0-200 for lights)
        else if (
          entity.raw &&
          typeof entity.raw.operating_status === "number"
        ) {
          // Lights are typically 0-200 (0xC8) for 0-100% brightness.
          // Scale CAN value to percentage.
          currentBrightnessPercent = Math.round(
            (entity.raw.operating_status / 200.0) * 100
          );
        }
        // If state is "on" but no specific brightness value is found in value or raw,
        // default to 100% as a sensible fallback.
        else {
          currentBrightnessPercent = 100;
        }
      } else {
        // If state is "off", brightness is always 0
        currentBrightnessPercent = 0;
      }

      // Clamp brightness to be within 0-100 and ensure it's a valid number
      currentBrightnessPercent = Math.max(
        0,
        Math.min(100, Number(currentBrightnessPercent) || 0)
      );

      cardContent += `
        <div class="brightness-control space-y-1">
          <label for="brightness-${entity.entity_id}" class="block text-sm font-medium">Brightness: <span class="brightness-value">${currentBrightnessPercent}%</span></label>
          <input type="range" id="brightness-${entity.entity_id}" name="brightness"
                 min="0" max="100" value="${currentBrightnessPercent}"
                 class="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer brightness-slider">
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
        slider.addEventListener("change", async () => {
          const brightness = parseInt(slider.value, 10);
          const entityId = entity.entity_id; // entity is from renderLightCard\'s scope
          const lightFriendlyName = entity.friendly_name || entityId;

          // Get the most current state of the light from our central store
          const currentActualLight = currentLightStates[entityId];
          const isCurrentlyOn =
            currentActualLight && currentActualLight.state === "on";

          if (!isCurrentlyOn) {
            // Light is currently off, turn it on AND set brightness in one command
            showToast(
              `Turning on ${lightFriendlyName} and setting to ${brightness}%...`,
              "info",
              2000
            );
            const result = await callLightService(entityId, "set", {
              state: "on",
              brightness: brightness,
            });

            if (!result) {
              // callLightService resolves to null on error
              showToast(
                `Failed to turn on and set brightness for ${lightFriendlyName}.`,
                "error"
              );
              // The UI will eventually reflect the true state via WebSocket.
            }
            // No timeout or second command needed as it's a single combined command.
          } else {
            // Light is already on, just set brightness
            showToast(
              `Setting brightness for ${lightFriendlyName} to ${brightness}%...`,
              "info",
              1500
            );
            const result = await callLightService(entityId, "set", {
              brightness: brightness,
            });
            if (!result) {
              // callLightService resolves to null on error
              showToast(
                `Failed to set brightness for ${lightFriendlyName}.`,
                "error"
              );
              // The UI will eventually reflect the true state via WebSocket.
            }
          }
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
    if (!lightsContent) {
      return;
    }
    lightsContent.innerHTML = ""; // Clear previous content

    const selectedArea = areaFilter.value;
    localStorage.setItem("lightsAreaFilter", selectedArea); // Save filter choice

    const grouped = {};
    Object.values(currentLightStates).forEach((entity) => {
      if (entity.device_type !== "light") return;
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
   * Fetches light entities from the API.
   * Uses /api/entities?device_type=light for consistency.
   */
  function fetchLights() {
    fetchData(`${apiBasePath}/entities?device_type=light`, {
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

  // Add toggle and rendering for Unknown PGNs
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
          <th class="px-4 py-2 text-left">Last Seen</th>
        </tr>
      </thead>
      <tbody>
        ${Object.entries(data)
          .map(
            ([pgn, item]) => `
              <tr class="border-b border-gray-700 hover:bg-gray-700">
                <td class="px-4 py-2 font-mono text-blue-300">${pgn}</td>
                <td class="px-4 py-2 text-yellow-200 font-bold">${item.count.toLocaleString()}</td>
                <td class="px-4 py-2 text-gray-400">${new Date(
                  item.last_seen_timestamp * 1000
                ).toLocaleString()}</td>
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
      card.className =
        "bg-gray-800 rounded-lg shadow p-4 flex flex-col sm:flex-row sm:items-center sm:justify-between";
      card.innerHTML = `
        <div>
          <span class="font-mono text-blue-300 text-lg font-semibold">PGN: ${pgn}</span>
          <span class="ml-2 text-gray-400 text-xs">Last Seen: ${new Date(
            item.last_seen_timestamp * 1000
          ).toLocaleString()}</span>
        </div>
        <div class="mt-2 sm:mt-0">
          <span class="inline-block bg-yellow-700 text-yellow-200 text-xs font-bold px-2 py-1 rounded">Count: ${item.count.toLocaleString()}</span>
        </div>
      `;
      container.appendChild(card);
    });
    unknownPgnsContent.appendChild(container);
  }

  function renderUnknownPgnsWithToggle(data) {
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

  /**
   * Populates the area filter dropdown for lights.
   * @param {object} lights - Object mapping entity IDs to light entity objects.
   */
  function updateAreaFilterForLights(lights) {
    if (!areaFilter) return;

    const currentSelectedValue =
      localStorage.getItem("lightsAreaFilter") || "All";
    const areas = new Set(["All"]); // Always include "All"

    Object.values(lights).forEach((entity) => {
      // Changed here
      if (entity.device_type === "light" && entity.suggested_area) {
        areas.add(entity.suggested_area);
      }
    });

    areaFilter.innerHTML = ""; // Clear existing options

    Array.from(areas)
      .sort()
      .forEach((area) => {
        const option = document.createElement("option");
        option.value = area;
        option.textContent = area;
        areaFilter.appendChild(option);
      });

    // Restore selection if possible, otherwise default to "All"
    if (areas.has(currentSelectedValue)) {
      areaFilter.value = currentSelectedValue;
    } else {
      areaFilter.value = "All";
      localStorage.setItem("lightsAreaFilter", "All"); // Update localStorage if previous was invalid
    }
    // Disable filter if only "All" (or no lights which implies only "All")
    areaFilter.disabled = areas.size <= 1;
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
      console.log(
        "[LOG DRAWER] Closing previous WebSocket before opening new one."
      );
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
    console.log(
      "[LOG DRAWER] disconnectLogSocket called. logSocket:",
      logSocket
    );
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
      console.log("[ENTITY_WS] WebSocket already connected and open.");
      return;
    }
    if (entitySocket && entitySocket.readyState === WebSocket.CONNECTING) {
      console.log(
        "[ENTITY_WS] WebSocket is currently connecting. Will not attempt to reconnect yet."
      );
      return;
    }

    console.log(`[ENTITY_WS] Attempting to connect to: ${entitySocketUrl}`);
    entitySocket = new WebSocket(entitySocketUrl);

    entitySocket.onopen = () => {
      console.log("[ENTITY_WS] WebSocket connection established successfully.");
      showToast("Real-time updates connected.", "info", 2000);
      // Potentially request full state if needed, or rely on initial HTTP load
    };

    entitySocket.onmessage = (event) => {
      console.log("[ENTITY_WS] Message received:", event.data);
      try {
        const updatedEntity = JSON.parse(event.data);

        if (
          updatedEntity &&
          updatedEntity.entity_id &&
          typeof updatedEntity.state === "string"
        ) {
          const entityId = updatedEntity.entity_id;

          // const oldState = currentLightStates[entityId] ? currentLightStates[entityId].state : "N/A";
          // const oldValue = currentLightStates[entityId] ? currentLightStates[entityId].value : "N/A";
          // console.log(`[ENTITY_WS] Updating entity ${entityId}. Old state: ${oldState}, Old value: ${JSON.stringify(oldValue)}. New data: ${JSON.stringify(updatedEntity)}`);

          currentLightStates[entityId] = {
            ...(currentLightStates[entityId] || {}),
            ...updatedEntity,
          };

          if (currentView === "lights") {
            // More targeted update instead of full re-render if possible,
            // but for now, re-rendering the lights view is acceptable.
            console.log(
              "[ENTITY_WS] Lights view is active, re-rendering grouped lights."
            );
            renderGroupedLights();
          } else {
            console.log(
              `[ENTITY_WS] Entity update for ${entityId} received, but current view is '${currentView}', not 'lights'. State updated in background.`
            );
          }
        } else {
          console.warn(
            "[ENTITY_WS] Received WebSocket message that is not a valid entity update (missing entity_id or state string):",
            updatedEntity
          );
        }
      } catch (error) {
        console.error(
          "[ENTITY_WS] Error processing entity WebSocket message:",
          error,
          "Raw data:",
          event.data
        );
      }
    };

    entitySocket.onerror = (error) => {
      console.error("[ENTITY_WS] WebSocket error:", error);
      // Attempt to get more details from the error event if possible
      if (error instanceof Event) {
        console.error(
          "[ENTITY_WS] WebSocket error event details:",
          JSON.stringify(error, Object.getOwnPropertyNames(error))
        );
      }
      showToast("Real-time updates connection error.", "error");
    };

    entitySocket.onclose = (event) => {
      console.log(
        `[ENTITY_WS] WebSocket disconnected. Code: ${event.code}, Reason: '${event.reason}', Was Clean: ${event.wasClean}`
      );
      showToast("Real-time updates disconnected.", "warning");
      // Optional: implement reconnection logic if desired
      // if (!event.wasClean) {
      //   console.log("[ENTITY_WS] Unclean disconnection. Attempting to reconnect in 5 seconds...");
      //   setTimeout(connectEntitySocket, 5000);
      // }
    };
  }

  function disconnectEntitySocket() {
    if (entitySocket) {
      entitySocket.close();
      entitySocket = null;
      console.log("Entity WebSocket intentionally disconnected.");
    }
  }

  function connectCanSnifferSocket() {
    if (canSnifferSocket && canSnifferSocket.readyState === WebSocket.OPEN) {
      return;
    }
    if (canSnifferSocket && canSnifferSocket.readyState === WebSocket.CONNECTING) {
      return;
    }
    const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    canSnifferSocket = new WebSocket(`${wsProtocol}//${window.location.host}/api/ws/can-sniffer`);

    canSnifferSocket.onopen = () => {
      console.log("[CAN SNIFFER] WebSocket connected.");
      clearCanSnifferTable();
      const canSnifferLoading = document.getElementById("can-sniffer-loading-message");
      if (canSnifferLoading) canSnifferLoading.classList.add("hidden");
    };

    canSnifferSocket.onmessage = (event) => {
      const group = JSON.parse(event.data);
      addCanSnifferGroupRow(group);
    };

    canSnifferSocket.onerror = (error) => {
      console.error("[CAN SNIFFER] WebSocket error:", error);
    };

    canSnifferSocket.onclose = () => {
      console.log("[CAN SNIFFER] WebSocket disconnected.");
      // Optionally implement reconnect logic here
    };
  }

  function disconnectCanSnifferSocket() {
    if (canSnifferSocket) {
      canSnifferSocket.close();
      canSnifferSocket = null;
    }
  }

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
    const { command, response, confidence, reason } = group;
    let rowClass = "";
    let icon = "";
    if (confidence === "high") {
      rowClass = "bg-green-900/60 hover:bg-green-800/80";
      icon = '<span title="Mapped grouping" class="mdi mdi-link-variant text-green-400 mr-1"></span>';
    } else if (confidence === "low") {
      rowClass = "bg-yellow-900/60 hover:bg-yellow-800/80";
      icon = '<span title="Heuristic grouping" class="mdi mdi-help-circle-outline text-yellow-400 mr-1"></span>';
    }
    // Command row
    const trCmd = document.createElement("tr");
    trCmd.className = rowClass;
    trCmd.innerHTML = `
      <td class="px-2 py-1 font-mono">${new Date(command.timestamp * 1000).toLocaleTimeString()}</td>
      <td class="px-2 py-1">TX</td>
      <td class="px-2 py-1 font-mono">${command.pgn || ""}</td>
      <td class="px-2 py-1 font-mono">${command.dgn_hex || ""}</td>
      <td class="px-2 py-1">${icon}${command.name || ""}</td>
      <td class="px-2 py-1 font-mono">${command.arbitration_id ? "0x" + command.arbitration_id.toString(16).toUpperCase() : ""}</td>
      <td class="px-2 py-1 font-mono">${command.data || ""}</td>
      <td class="px-2 py-1 font-mono">${command.decoded ? JSON.stringify(command.decoded) : ""}</td>
    `;
    tbody.appendChild(trCmd);
    // Response row
    const trResp = document.createElement("tr");
    trResp.className = rowClass;
    trResp.innerHTML = `
      <td class="px-2 py-1 font-mono">${new Date(response.timestamp * 1000).toLocaleTimeString()}</td>
      <td class="px-2 py-1">RX</td>
      <td class="px-2 py-1 font-mono">${response.pgn || ""}</td>
      <td class="px-2 py-1 font-mono">${response.dgn_hex || ""}</td>
      <td class="px-2 py-1">${icon}${response.name || ""}</td>
      <td class="px-2 py-1 font-mono">${response.arbitration_id ? "0x" + response.arbitration_id.toString(16).toUpperCase() : ""}</td>
      <td class="px-2 py-1 font-mono">${response.data || ""}</td>
      <td class="px-2 py-1 font-mono">${response.decoded ? JSON.stringify(response.decoded) : ""}</td>
    `;
    tbody.appendChild(trResp);
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
      // Accessibility: focus the first <h1> in the new view
      const mainHeading = targetView.querySelector("h1");
      if (mainHeading) {
        mainHeading.setAttribute("tabindex", "-1");
        mainHeading.focus();
      }
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
      case "can-sniffer":
        clearCanSnifferTable();
        connectCanSnifferSocket();
        break;
      default:
        disconnectCanSnifferSocket();
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
   * Utility to toggle open/collapsed state for a panel (sidebar or drawer).
   * @param {Object} opts
   * @param {HTMLElement} opts.panel - The panel element (sidebar or drawer)
   * @param {HTMLElement} opts.content - The content element to show/hide (optional)
   * @param {HTMLElement} opts.mainContent - The main content element (for margin adjustment, optional)
   * @param {HTMLElement} opts.toggleButton - The button to update icon/text (optional)
   * @param {boolean} opts.expanded - True to expand, false to collapse
   * @param {Object} opts.styles - { expanded: {width, marginLeft, height, paddingBottom}, collapsed: {...} }
   * @param {Function} [opts.onExpand] - Callback after expand
   * @param {Function} [opts.onCollapse] - Callback after collapse
   * @param {HTMLElement} [opts.pinnedLogsContainer] - The pinned logs container element (optional)
   * @param {Object} [opts.pinnedLogsStyles] - Styles for pinned logs container (optional)
   */
  function setPanelExpanded({
    panel,
    content,
    mainContent,
    toggleButton,
    expanded,
    styles,
    onExpand,
    onCollapse,
    // New: Pinned logs container and its related elements
    pinnedLogsContainer,
    pinnedLogsStyles,
  }) {
    if (!panel) return;

    // Clear existing inline transition before applying new one or changing properties directly
    panel.style.transition = "";
    if (mainContent) mainContent.style.transition = "";
    if (pinnedLogsContainer) pinnedLogsContainer.style.transition = ""; // Clear for pinned logs

    // Apply new transition if specified
    if (styles.transition) {
      // Force reflow to ensure transition applies correctly after clearing
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      const _ = panel.offsetHeight;
      panel.style.transition = styles.transition;
      if (mainContent) {
        // eslint-disable-next-line @typescript-eslint/no-unused-vars
        const __ = mainContent.offsetHeight;
        mainContent.style.transition = styles.transition; // Use the same transition as sidebar for margin-left
      }
      if (
        pinnedLogsContainer &&
        pinnedLogsStyles &&
        pinnedLogsStyles.transition
      ) {
        // eslint-disable-next-line @typescript-eslint/no-unused-vars
        const ___ = pinnedLogsContainer.offsetHeight;
        pinnedLogsContainer.style.transition = pinnedLogsStyles.transition; // Use specific transition for pinned logs (e.g., for 'left')
      }
    }

    if (expanded) {
      if (styles.expanded.width) {
        panel.style.setProperty("width", styles.expanded.width, "important");
      }
      if (mainContent && styles.expanded.marginLeft) {
        mainContent.style.setProperty(
          "margin-left",
          styles.expanded.marginLeft,
          "important"
        );
      }
      // Pinned logs adjustment when sidebar expands
      if (
        pinnedLogsContainer &&
        pinnedLogsStyles &&
        pinnedLogsStyles.expanded &&
        pinnedLogsStyles.expanded.left
      ) {
        pinnedLogsContainer.style.left = pinnedLogsStyles.expanded.left;
      }
      if (panel && styles.expanded.height) {
        panel.style.height = styles.expanded.height;
      }
      if (mainContent && styles.expanded.paddingBottom) {
        mainContent.style.paddingBottom = styles.expanded.paddingBottom;
      }
      if (content) content.classList.remove(CLASS_HIDDEN);
      if (toggleButton && toggleButton.querySelector("i")) {
        toggleButton.querySelector("i").className =
          styles.expanded.iconClass || "";
      }
      if (toggleButton && toggleButton.querySelector("span")) {
        toggleButton.querySelector("span").textContent =
          styles.expanded.label || "";
      }
      if (toggleButton) toggleButton.setAttribute("aria-expanded", "true");
      if (onExpand) onExpand();
    } else {
      if (styles.collapsed.width) {
        panel.style.setProperty("width", styles.collapsed.width, "important");
      }
      if (mainContent && styles.collapsed.marginLeft) {
        mainContent.style.setProperty(
          "margin-left",
          styles.collapsed.marginLeft,
          "important"
        );
      }
      // Pinned logs adjustment when sidebar collapses
      if (
        pinnedLogsContainer &&
        pinnedLogsStyles &&
        pinnedLogsStyles.collapsed &&
        pinnedLogsStyles.collapsed.left
      ) {
        pinnedLogsContainer.style.left = pinnedLogsStyles.collapsed.left;
      }
      if (panel && styles.collapsed.height) {
        panel.style.height = styles.collapsed.height;
      }
      if (mainContent && styles.collapsed.paddingBottom) {
        mainContent.style.paddingBottom = styles.collapsed.paddingBottom;
      }
      if (content) content.classList.add(CLASS_HIDDEN);
      if (toggleButton && toggleButton.querySelector("i")) {
        toggleButton.querySelector("i").className =
          styles.collapsed.iconClass || "";
      }
      if (toggleButton && toggleButton.querySelector("span")) {
        toggleButton.querySelector("span").textContent =
          styles.collapsed.label || "";
      }
      if (toggleButton) toggleButton.setAttribute("aria-expanded", "false");
      if (onCollapse) onCollapse();
    }
  }

  /**
   * Sets the visibility and state of the desktop sidebar.
   * Also adjusts the pinned logs container's left margin to align with the sidebar.
   * @param {boolean} expanded - True to expand the sidebar, false to collapse.
   */
  function setDesktopSidebarVisible(expanded) {
    console.log(
      "[DEBUG] setDesktopSidebarVisible called with:",
      expanded,
      "Current isDesktopSidebarExpanded before change:",
      isDesktopSidebarExpanded
    );
    isDesktopSidebarExpanded = expanded;
    localStorage.setItem(DESKTOP_SIDEBAR_EXPANDED_KEY, expanded);

    if (
      !sidebar ||
      !mainContent ||
      !toggleSidebarDesktopButton ||
      !sidebarNavContent ||
      !pinnedLogsContainer
    ) {
      console.warn(
        "[SIDEBAR/LOGS] Missing one or more critical elements for setDesktopSidebarVisible or adjustPinnedLogsLayout"
      );
      return;
    }

    sidebar.setAttribute("aria-expanded", expanded.toString());
    toggleSidebarDesktopButton.setAttribute(
      "aria-expanded",
      expanded.toString()
    );

    // Define styles for sidebar and main content
    const sidebarStyles = {
      transition:
        "width 0.3s cubic-bezier(0.4,0,0.2,1), margin-left 0.3s cubic-bezier(0.4,0,0.2,1)",
      expanded: {
        width: "16rem", // Tailwind w-64
        marginLeft: "16rem", // mainContent margin for DESKTOP
        iconClass: "mdi mdi-chevron-left text-xl",
        label: "Collapse",
      },
      collapsed: {
        width: "4rem", // Tailwind w-16
        marginLeft: "4rem", // mainContent margin for DESKTOP
        iconClass: "mdi mdi-chevron-right text-xl",
        label: "",
      },
    };

    // Adjust mainContent marginLeft for mobile
    let finalMainContentMarginLeftExpanded = sidebarStyles.expanded.marginLeft;
    let finalMainContentMarginLeftCollapsed =
      sidebarStyles.collapsed.marginLeft;

    if (window.innerWidth < MD_BREAKPOINT_PX) {
      finalMainContentMarginLeftExpanded = "0px";
      finalMainContentMarginLeftCollapsed = "0px";
    }

    const effectivePanelStyles = {
      transition: sidebarStyles.transition,
      expanded: {
        ...sidebarStyles.expanded,
        marginLeft: finalMainContentMarginLeftExpanded,
      },
      collapsed: {
        ...sidebarStyles.collapsed,
        marginLeft: finalMainContentMarginLeftCollapsed,
      },
    };

    // Define styles for pinned logs container (specifically its 'left' property)
    const pinnedLogsStylesDef = {
      transition: "left 0.3s cubic-bezier(0.4,0,0.2,1)", // Match sidebar transition timing
      expanded: {
        left: "16rem", // Align with expanded sidebar
      },
      collapsed: {
        left: "4rem", // Align with collapsed sidebar
      },
    };

    setPanelExpanded({
      panel: sidebar,
      content: sidebarNavContent,
      mainContent,
      toggleButton: toggleSidebarDesktopButton,
      expanded,
      styles: effectivePanelStyles, // Use the modified styles for mainContent margin
      pinnedLogsContainer,
      pinnedLogsStyles: pinnedLogsStylesDef,
      onExpand: () => {
        // Removed "relative top-0.5" from the label span
        toggleSidebarDesktopButton.innerHTML = `<span class="mdi ${sidebarStyles.expanded.iconClass} mr-0"></span><span class="ml-2">${sidebarStyles.expanded.label}</span>`;
        sidebar.classList.remove("sidebar-collapsed-hoverable");
        sidebarNavContent.classList.remove(CLASS_HIDDEN);
        sidebar
          .querySelectorAll(".nav-link span")
          .forEach((span) => span.classList.remove(CLASS_HIDDEN));
        sidebar
          .querySelectorAll(".nav-link i")
          .forEach((icon) => icon.classList.add("mr-2"));
        // Ensure pinned logs are correctly positioned after sidebar animation completes
        // This might be redundant if setPanelExpanded handles it, but good for explicit control
        adjustPinnedLogsLayout();
      },
      onCollapse: () => {
        // Removed "relative top-0.5" from the collapsed label span as well for consistency.
        toggleSidebarDesktopButton.innerHTML = `<span class="mdi ${sidebarStyles.collapsed.iconClass}"></span><span class="ml-2">${sidebarStyles.collapsed.label}</span>`;
        sidebar.classList.add("sidebar-collapsed-hoverable");
        sidebarNavContent.classList.add(CLASS_HIDDEN);
        sidebar
          .querySelectorAll(".nav-link span")
          .forEach((span) => span.classList.add(CLASS_HIDDEN));
        sidebar
          .querySelectorAll(".nav-link i")
          .forEach((icon) => icon.classList.remove("mr-2"));
        // Ensure pinned logs are correctly positioned after sidebar animation completes
        adjustPinnedLogsLayout();
      },
    });
    // Initial call to adjust layout, especially if logs are already expanded/collapsed
    // setPanelExpanded will handle the left adjustment, this handles height/padding
    adjustPinnedLogsLayout();
  }

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
    ) {
      console.warn(
        "[SIDEBAR_SETUP] Missing critical elements for setupSidebarCollapseExpand. Listeners not attached."
      );
      return;
    }

    // Prevent horizontal scrollbar during animation
    sidebar.style.overflowX = "hidden";

    // Listener for clicking the sidebar background itself to expand it when collapsed (desktop only)
    sidebar.addEventListener("click", (e) => {
      console.log(
        "[SIDEBAR_SETUP] Sidebar area clicked. isDesktopSidebarExpanded:",
        isDesktopSidebarExpanded,
        "e.target:",
        e.target,
        "sidebar element:",
        sidebar
      );
      // Expand only if on desktop, sidebar is currently collapsed, and the click target is the sidebar element itself (not a child element like a nav link or button)
      if (
        window.innerWidth >= MD_BREAKPOINT_PX &&
        !isDesktopSidebarExpanded &&
        e.target === sidebar // Ensure the click is on the sidebar itself, not its children
      ) {
        console.log("[SIDEBAR_SETUP] Expanding sidebar via area click.");
        setDesktopSidebarVisible(true);
      } else {
        console.log(
          "[SIDEBAR_SETUP] Sidebar area click - conditions for expansion NOT MET or click was on a child. Conditions:",
          {
            isDesktop: window.innerWidth >= MD_BREAKPOINT_PX,
            isCollapsed: !isDesktopSidebarExpanded,
            targetIsSidebarItself: e.target === sidebar,
          }
        );
      }
    });

    // Listener for the dedicated desktop sidebar collapse/expand toggle button
    toggleSidebarDesktopButton.addEventListener("click", (e) => {
      console.log(
        "[SIDEBAR_SETUP] Toggle button clicked. Current isDesktopSidebarExpanded:",
        isDesktopSidebarExpanded,
        "e.target:",
        e.target
      );
      e.stopPropagation(); // Crucial: Prevents the sidebar's own click listener (above) from also firing if this button is considered a child of the sidebar.
      setDesktopSidebarVisible(!isDesktopSidebarExpanded);
    });

    // Listener for the mobile sidebar close button
    if (closeSidebarButton) {
      closeSidebarButton.addEventListener("click", (e) => {
        if (sidebar) {
          console.log("[SIDEBAR_SETUP] Mobile close button clicked.");
          e.stopPropagation(); // Good practice, though less critical if it's the only listener on this specific button
          sidebar.classList.add("-translate-x-full");
          sidebar.setAttribute(ARIA_HIDDEN, "true");
          // On mobile, closing the sidebar effectively means it's not "expanded" in the desktop sense.
          // If isDesktopSidebarExpanded is used for mobile state, it should be set to false here.
          // However, mobile sidebar often has its own visibility state managed by classes like '-translate-x-full'.
          // For now, we assume setDesktopSidebarVisible(false) is not what we want for a mobile-specific close action
          // unless the state variable `isDesktopSidebarExpanded` is also meant to track mobile visibility.
        }
      });
    }
    // ARIA attributes for sidebar and toggleSidebarDesktopButton are managed by setDesktopSidebarVisible.
    // Initial ARIA attributes are set when setDesktopSidebarVisible is first called in initializeApp.
  }

  /**
   * Adjusts the pinned logs drawer position so it does not cover the sidebar.
   * Sets the left offset to match the sidebar width (expanded/collapsed) on desktop.
   * On mobile, sets left to 0.
   * Should be called on sidebar expand/collapse, window resize, and after toggling logs.
   */
  function adjustPinnedLogsLayout() {
    if (!pinnedLogsContainer || !sidebar || !mainContent) {
      console.warn(
        "[LOGS] Missing elements for adjustPinnedLogsLayout. Cannot adjust layout."
      );
      return;
    }

    const logsHeaderHeight = pinnedLogsHeader
      ? pinnedLogsHeader.offsetHeight
      : 0;
    // Get the current actual height of the logs container.
    // This height is primarily managed by setPinnedLogsState (within setupPinnedLogsResizablePanel)
    // and reflects user interactions (toggle, resize) or initial load state.
    const currentPinnedLogsHeight = pinnedLogsContainer.offsetHeight;

    if (window.innerWidth < MD_BREAKPOINT_PX) {
      // Mobile: logs bar spans full width, sidebar is an overlay or hidden.
      // `left` and `right` are set to 0 to span the viewport.
      pinnedLogsContainer.style.left = "0px";
      pinnedLogsContainer.style.right = "0px";
      // Adjust main content padding to prevent overlap with the logs container.
      mainContent.style.paddingBottom = `${currentPinnedLogsHeight}px`;
    } else {
      // Desktop:
      // The 'left' position of pinnedLogsContainer is dynamically set by 'setDesktopSidebarVisible'
      // (via 'setPanelExpanded') using 'rem' units to align with the sidebar's width
      // and to ensure smooth transitions. This function should not override that.
      // 'right' is set to 0 to make the logs container span the rest of the main content area.
      pinnedLogsContainer.style.right = "0px";
      // Adjust main content padding.
      mainContent.style.paddingBottom = `${currentPinnedLogsHeight}px`;
    }

    // Adjust the height of the scrollable content area within the pinned logs container,
    // accounting for the header height.
    if (pinnedLogsContent) {
      pinnedLogsContent.style.height = `calc(100% - ${logsHeaderHeight}px)`;
    }
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
          let lights = null;
          await new Promise((resolve) => {
            fetchData(`${apiBasePath}/entities?device_type=light`, {
              successCallback: (resp) => {
                lights = resp;
                resolve();
              },
              errorCallback: (err) => {
                showToast("Failed to fetch lights", "error");
                resolve();
              },
              showToastOnError: false,
            });
          });
          if (!lights) return;
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
            const res = await callLightService(
              entity.entity_id,
              control.command.command,
              control.command
            );
            if (res) successCount++;
            else errorCount++;
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
      localStorage.setItem("pinnedLogsOpen", isOpen);
      if (isOpen && height) {
        localStorage.setItem("pinnedLogsHeight", height);
        currentExpandedLogsHeight = height;
      }
      setPanelExpanded({
        panel: pinnedLogsContainer,
        content: pinnedLogsContent,
        mainContent,
        toggleButton: togglePinnedLogsButton,
        expanded: isOpen,
        styles: {
          transition:
            "height 0.3s cubic-bezier(0.4,0,0.2,1), padding-bottom 0.3s cubic-bezier(0.4,0,0.2,1)",
          expanded: {
            height: currentExpandedLogsHeight,
            paddingBottom: currentExpandedLogsHeight,
            iconClass: "mdi mdi-chevron-down text-2xl",
            label: "",
          },
          collapsed: {
            height: "3rem",
            paddingBottom: "3rem",
            iconClass: "mdi mdi-chevron-up text-2xl",
            label: "",
          },
        },
        onExpand: () => {
          connectLogSocket();
        },
        onCollapse: () => {
          disconnectLogSocket();
        },
      });
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
    // Only show/hide the waiting message overlay inside the logStream area, not over the controls
    const logsWaitingMessage = document.getElementById("logs-waiting-message");
    if (!logsWaitingMessage) return;
    if (show) {
      logsWaitingMessage.classList.remove(CLASS_HIDDEN);
      // Ensure log controls are always enabled
      if (logLevelSelect) logLevelSelect.disabled = false;
      if (logSearchInput) logSearchInput.disabled = false;
      if (logPauseButton) logPauseButton.disabled = false;
      if (logClearButton) logClearButton.disabled = false;
    } else {
      logsWaitingMessage.classList.add(CLASS_HIDDEN);
      // Controls remain enabled
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
   * Fetches and displays CAN sniffer log data.
   */
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
          if (tbody)
            tbody.innerHTML =
              '<tr><td colspan="8" class="text-center text-gray-400 py-4">No CAN command/control groupings observed yet.</td></tr>';
          return;
        }
        data
          .slice()
          .reverse()
          .forEach((group) => {
            const { command, response, confidence, reason } = group;
            // Pick color class based on confidence
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
            // Render command row
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
            // Render response row
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
          });
      },
      errorCallback: (error) => {
        if (canSnifferLoading) {
          canSnifferLoading.textContent = `Error loading CAN sniffer data: ${error.message}`;
          canSnifferLoading.classList.remove("hidden");
        }
        if (tbody) tbody.innerHTML = "";
      },
      loadingElement: canSnifferLoading,
    });
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

    // Initialize sidebar state for desktop - This sets the initial state based on localStorage
    const savedSidebarState = localStorage.getItem(
      DESKTOP_SIDEBAR_EXPANDED_KEY
    );
    // Set initial state. setDesktopSidebarVisible handles ARIA attributes and localStorage update.
    setDesktopSidebarVisible(
      savedSidebarState === null ? true : savedSidebarState === "true"
    );

    // Event listeners for mobile sidebar controls
    if (mobileMenuButton && sidebar) {
      // Removed closeSidebarButton from condition as its listener is in setupSidebarCollapseExpand
      mobileMenuButton.addEventListener("click", () => {
        sidebar.classList.remove("-translate-x-full");
        sidebar.setAttribute(ARIA_HIDDEN, "false"); // Ensure ARIA state is updated
      });
    }

    // Setup navigation links
    navLinks.forEach((link) => {
      link.addEventListener("click", (e) => {
        e.preventDefault();
        const viewName = link.getAttribute(ATTR_DATA_VIEW);
        if (viewName) {
          navigateToView(viewName);
        }
      });
    });

    // Initial view loading and data fetching
    let initialView = "home"; // Default view
    // TODO: Could add logic to parse window.location.hash for initial view
    navigateToView(initialView, true);

    // Connect Entity WebSocket globally for background updates
    connectEntitySocket();

    // Log controls setup (pause/resume)
    if (logPauseButton) {
      logPauseButton.addEventListener("click", () => {
        isLogPaused = true;
        logPauseButton.disabled = true;
        if (logResumeButton) logResumeButton.disabled = false; // Enable resume button
        showToast("Log stream paused.", "info", 1500);
      });
    }
    if (logResumeButton) {
      logResumeButton.disabled = true; // Initially disabled if logs are not paused
      logResumeButton.addEventListener("click", () => {
        isLogPaused = false;
        if (logPauseButton) logPauseButton.disabled = false; // Enable pause button
        logResumeButton.disabled = true; // Disable resume button
        if (logStream) logStream.scrollTop = logStream.scrollHeight; // Scroll to bottom
        showToast("Log stream resumed.", "info", 1500);
      });
    }
    // Note: Listeners for logClearButton, logLevelSelect, logSearchInput are already global (patched outside this function).

    // Call setup functions that manage their own event listeners
    setupBulkLightControlButtons();
    setupPinnedLogsResizablePanel(); // Manages pinned logs listeners
    setupSidebarCollapseExpand(); // Handles all sidebar button listeners (desktop toggle, mobile close, background click)

    // Add a global resize listener to re-evaluate sidebar and main content layout
    window.addEventListener("resize", () => {
      if (typeof isDesktopSidebarExpanded === "boolean") {
        // Ensure state is initialized
        // This will re-apply mainContent margins considering the current window size
        // and also call adjustPinnedLogsLayout internally.
        setDesktopSidebarVisible(isDesktopSidebarExpanded);
      }
      // Note: adjustPinnedLogsLayout also has its own resize listener for height clamping.
      // Calling setDesktopSidebarVisible ensures its internal call to adjustPinnedLogsLayout
      // also considers sidebar width changes affecting pinned logs' left position.
    });

    console.log(`rvc2api UI Initialized. Version: ${APP_VERSION}`);
  }

  // Initialize the app when the DOM is fully loaded
  document.addEventListener("DOMContentLoaded", () => {
    initializeApp();
    if (areaFilter) {
      areaFilter.addEventListener("change", renderGroupedLights);
    }
  });
})(); // Ensure this IIFE is properly closed
