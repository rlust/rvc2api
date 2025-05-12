/**
 * utils.js - Shared utility functions for rvc2api Web UI
 *
 * Author: Ryan Holt
 * Last updated: 2025-05-12
 */

/**
 * Shows a toast notification.
 * @param {string} message - The message to display.
 * @param {'info'|'success'|'warning'|'error'} [type='info'] - The type of toast.
 * @param {number} [duration=5000] - Duration in milliseconds to show the toast.
 */
export function showToast(message, type = "info", duration = 3000) {
  const toastContainer = document.getElementById("toast-container");
  if (!toastContainer) return;
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  toast.setAttribute("role", "alert");
  toastContainer.appendChild(toast);
  setTimeout(() => {
    toast.classList.add("show");
  }, 10);
  setTimeout(() => {
    toast.classList.remove("show");
    setTimeout(() => {
      toast.remove();
    }, 300);
  }, duration);
}
