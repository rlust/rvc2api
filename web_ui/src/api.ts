// src/api.ts
// API utility for rvc2api React frontend

export async function fetchAppHealth() {
  const res = await fetch("/api/health");
  if (!res.ok) throw new Error("Failed to fetch app health");
  return res.json();
}

export async function fetchCanStatus() {
  const res = await fetch("/api/can/status");
  if (!res.ok) throw new Error("Failed to fetch CAN status");
  return res.json();
}

export async function fetchLights() {
  const res = await fetch("/api/entities/lights");
  if (!res.ok) throw new Error("Failed to fetch lights");
  return res.json();
}

export async function fetchDeviceMapping() {
  const res = await fetch("/api/config/device-mapping");
  if (!res.ok) throw new Error("Failed to fetch device mapping");
  return res.json();
}

export async function fetchRvcSpec() {
  const res = await fetch("/api/config/rvc-spec");
  if (!res.ok) throw new Error("Failed to fetch RVC spec");
  return res.json();
}

// Add more API helpers as needed
