const { app, BrowserWindow, Menu, ipcMain } = require("electron");
const path = require("path");
const fs = require("fs");

// The desktop client is a thin shell: it connects to a Bemas Muhasebe backend
// (usually running on one shared "server" computer on the office network) and
// opens its admin-panel UI in a native window.
//
// Which server to connect to is resolved in this order:
//   1. BEMAS_SERVER_URL env var (developer override)
//   2. config.json saved in this app's userData folder (set once via the
//      in-app "Sunucu Adresi" screen below, persists across restarts/reinstalls
//      of the app itself since userData is separate from the install folder)
//   3. http://localhost:8000 (same-machine backend)
const ADMIN_PATH = "/adminpanel/";
const CONFIG_PATH = path.join(app.getPath("userData"), "config.json");

function readConfiguredServerUrl() {
  try {
    // Strip a possible leading BOM - Notepad's "UTF-8" save option writes one,
    // and a bare U+FEFF makes JSON.parse throw on an otherwise-valid file.
    const raw = fs.readFileSync(CONFIG_PATH, "utf-8").replace(/^﻿/, "");
    const parsed = JSON.parse(raw);
    if (parsed.serverUrl) return parsed.serverUrl;
  } catch (_) { /* no config yet, or unreadable - fall through to default */ }
  return null;
}

function writeConfiguredServerUrl(url) {
  fs.writeFileSync(CONFIG_PATH, JSON.stringify({ serverUrl: url }, null, 2), "utf-8");
}

function currentServerUrl() {
  return process.env.BEMAS_SERVER_URL || readConfiguredServerUrl() || "http://localhost:8000";
}

async function canReach(serverUrl) {
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 3000);
    const res = await fetch(`${serverUrl}/api/health`, { signal: controller.signal });
    clearTimeout(timeout);
    return res.ok;
  } catch (_) {
    return false;
  }
}

let mainWindow = null;

function addReloadShortcut(win) {
  // Menu.setApplicationMenu(null) also removes the default Ctrl+R/F5 reload
  // accelerator (it lived on the View menu item), so re-add it manually -
  // otherwise the only way to pick up a frontend update is restarting the app.
  win.webContents.on("before-input-event", (event, input) => {
    const isF5 = input.key === "F5";
    const isCtrlR = (input.control || input.meta) && input.key.toLowerCase() === "r";
    if (isF5 || isCtrlR) {
      win.webContents.reload();
    }
  });
}

async function loadAppOrSetup(win) {
  const serverUrl = currentServerUrl();
  if (await canReach(serverUrl)) {
    win.loadURL(`${serverUrl}${ADMIN_PATH}`);
  } else {
    // No blank white screen when the server isn't reachable (wrong network,
    // server not started yet, first run on a new computer, etc.) - ask for
    // the right address instead, once, and remember it from then on.
    win.loadFile(path.join(__dirname, "setup.html"), { query: { url: serverUrl } });
  }
}

function createWindow() {
  const win = new BrowserWindow({
    width: 1280,
    height: 820,
    minWidth: 900,
    minHeight: 600,
    title: "Bemas Treyler - Cari Hesap Takip",
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow = win;
  Menu.setApplicationMenu(null);
  addReloadShortcut(win);
  loadAppOrSetup(win);
}

// Called from setup.html (via preload.js) when the user enters a server
// address: verify it actually works before saving/using it, so a typo just
// shows an error on the same screen instead of trading one blank page for
// another.
ipcMain.handle("bemas:test-and-save-server-url", async (_event, url) => {
  const cleanUrl = url.trim().replace(/\/+$/, "");
  if (!/^https?:\/\/.+/i.test(cleanUrl)) {
    return { ok: false, error: "Adres http:// veya https:// ile başlamalı." };
  }
  const reachable = await canReach(cleanUrl);
  if (!reachable) {
    return { ok: false, error: "Bu adrese ulaşılamadı. Adresi ve ağ bağlantısını kontrol edin." };
  }
  writeConfiguredServerUrl(cleanUrl);
  if (mainWindow) mainWindow.loadURL(`${cleanUrl}${ADMIN_PATH}`);
  return { ok: true };
});

app.whenReady().then(() => {
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
