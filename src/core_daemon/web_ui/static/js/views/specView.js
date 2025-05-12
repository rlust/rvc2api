/**
 * specView.js - Handles the RVC Specification view logic for the rvc2api Web UI
 *
 * Responsibilities:
 * - Fetching and rendering the RVC specification text and metadata
 * - UI feedback (toasts, error messages)
 *
 * Author: Ryan Holt
 * Last updated: 2025-05-12
 */

import { fetchData } from "../api.js";
import { showToast } from "../utils.js";
import { apiBasePath } from "../config.js";

const specContent = document.getElementById("spec-content");
const specMetadataDiv = document.getElementById("spec-metadata");

function updateSpecTextView(textData) {
  try {
    if (specContent) {
      // Try to pretty-print JSON if possible, else show as plain text
      let pretty = null;
      try {
        const parsed = JSON.parse(textData);
        pretty = JSON.stringify(parsed, null, 2);
      } catch {
        // Not JSON, show as-is
      }
      specContent.textContent = pretty || textData;
      // Add toggle button for raw/pretty view if JSON
      if (pretty) {
        let toggleBtn = document.getElementById("spec-toggle-btn");
        if (!toggleBtn) {
          toggleBtn = document.createElement("button");
          toggleBtn.id = "spec-toggle-btn";
          toggleBtn.className = "mt-2 mb-2 bg-blue-600 hover:bg-blue-500 text-white py-1 px-3 rounded text-xs";
          toggleBtn.textContent = "Show Raw";
          specContent.parentElement.insertBefore(toggleBtn, specContent);
        }
        let showingPretty = true;
        toggleBtn.onclick = () => {
          showingPretty = !showingPretty;
          specContent.textContent = showingPretty ? pretty : textData;
          toggleBtn.textContent = showingPretty ? "Show Raw" : "Show Pretty";
        };
      } else {
        // Remove toggle if not JSON
        const oldBtn = document.getElementById("spec-toggle-btn");
        if (oldBtn) oldBtn.remove();
      }
    }
  } catch (err) {
    console.error("Error in updateSpecTextView:", err);
    if (specContent) specContent.textContent = "Error rendering spec content.";
  }
}

function updateSpecMetadataView(metadata) {
  try {
    if (specMetadataDiv) {
      if (
        metadata &&
        (metadata.version || metadata.source || metadata.spec_document)
      ) {
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

export function fetchSpecView() {
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
    loadingElement: specContent,
  });

  // Fetch Spec Metadata (JSON)
  fetchData(`${apiBasePath}/config/rvc_spec_metadata`, {
    responseType: "json",
    successCallback: updateSpecMetadataView,
    errorCallback: (error) => {
      console.error("Failed to fetch spec metadata:", error);
      if (specMetadataDiv)
        specMetadataDiv.textContent = "Error loading RVC spec metadata.";
    },
  });
}
