/**
 * unmappedView.js - Handles the Unmapped Entries view logic for the rvc2api Web UI
 *
 * Responsibilities:
 * - Fetching and rendering unmapped CAN entries
 * - Providing YAML suggestions and copy-to-clipboard functionality
 * - UI feedback (toasts, error messages)
 *
 * Author: Ryan Holt
 * Last updated: 2025-05-12
 */
import { fetchData } from '../api.js';
import { showToast } from '../utils.js';
import { apiBasePath } from '../config.js';

const unmappedEntriesView = document.getElementById('unmapped-view');
const unmappedEntriesContent = document.getElementById('unmapped-entries-container');

function generateYamlSuggestion(entry) {
  const { id, name, description, type, length, factor, offset, unit } = entry;
  return `- id: ${id}
  name: ${name}
  description: ${description}
  type: ${type}
  length: ${length}
  factor: ${factor}
  offset: ${offset}
  unit: ${unit}`;
}

export function renderUnmappedEntries(data) {
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
    // Event delegation for copy buttons
    if (!unmappedEntriesContent.hasAttribute('data-copy-bound')) {
      unmappedEntriesContent.setAttribute('data-copy-bound','');
      unmappedEntriesContent.addEventListener('click', (event) => {
        const btn = event.target.closest('.copy-yaml-btn');
        if (!btn) return;
        const code = btn.previousElementSibling.querySelector('code');
        if (!code) return;
        const yamlText = code.innerText;
        navigator.clipboard.writeText(yamlText)
          .then(() => {
            btn.textContent = "Copied!";
            showToast("YAML copied to clipboard!", "success");
            setTimeout(() => { btn.textContent = "Copy YAML"; }, 2000);
          })
          .catch((err) => {
            showToast("Failed to copy YAML.", "error");
            btn.textContent = "Failed to copy";
            setTimeout(() => { btn.textContent = "Copy YAML"; }, 2000);
          });
      });
    }
  } catch (err) {
    console.error("Error in renderUnmappedEntries:", err);
    if (unmappedEntriesContent)
      unmappedEntriesContent.textContent = "Error rendering unmapped entries.";
  }
}

export function fetchUnmappedEntries() {
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
