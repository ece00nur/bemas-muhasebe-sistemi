const { app, BrowserWindow, Menu, ipcMain } = require("electron");
const path = require("path");
const fs = require("fs");
const { spawn } = require("child_process");

// The desktop client is a thin shell around a Bemas Muhasebe backend. By
// default (no config override) it is fully self-contained: it bundles the
// backend as a PyInstaller-frozen exe and spawns it on 127.0.0.1 itself, so
// someone on a completely different computer/network - e.g. a relative with
// no technical setup ability - can just run the installer and have a working
// app with zero network/IP/Python configuration.
//
// Which server to connect to is resolved in this order:
//   1. BEMAS_SERVER_URL env var (developer override)
//   2. config.json saved in this app's userData folder (set once via the
//      in-app "Sunucu Adresi" screen below, persists across restarts/reinstalls
//      of the app itself since userData is separate from the install folder) -
//      this is the "connect to a shared/remote server instead" escape hatch
//   3. http://localhost:8000, auto-starting the bundled backend if nothing is
//      already listening there
const ADMIN_PATH = "/adminpanel/";
const CONFIG_PATH = path.join(app.getPath("userData"), "config.json");
const LOCAL_BACKEND_URL = "http://127.0.0.1:8000";

// Where the bundled backend exe lives once packaged (see package.json's
// electron-builder "extraResources": dist_pyinstaller/bemas-backend copied to
// resources/backend). Not present in dev mode - dev runs the backend manually.
const BUNDLED_BACKEND_EXE = path.join(
  process.resourcesPath || "",
  "backend",
  "bemas-backend.exe"
);

let backendProcess = null;

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

// True only when the user has explicitly pointed this install at some other
// server (dev env var, or the one-time "Sunucu Adresi" setup screen). In
// that case we never touch the bundled backend - the whole point of that
// escape hatch is to talk to a server running somewhere else.
function hasExplicitServerOverride() {
  return Boolean(process.env.BEMAS_SERVER_URL || readConfiguredServerUrl());
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// Starts the bundled backend exe (packaged builds only) and waits for it to
// answer /api/health, so a relative on a totally different computer/network
// never has to install Python or type in a server address - it just works
// the moment the installer finishes.
async function startBundledBackend() {
  if (backendProcess) return true; // already starting/started this run
  if (!app.isPackaged) return false; // dev mode: run the backend manually
  if (!fs.existsSync(BUNDLED_BACKEND_EXE)) return false;

  try {
    backendProcess = spawn(BUNDLED_BACKEND_EXE, [], {
      cwd: path.dirname(BUNDLED_BACKEND_EXE),
      windowsHide: true,
      stdio: "ignore",
    });
    backendProcess.on("exit", () => {
      backendProcess = null;
    });
  } catch (_) {
    backendProcess = null;
    return false;
  }

  // Poll rather than wait a fixed delay - a cold machine's first launch
  // (antivirus scanning the exe, disk still warming up, etc.) can take a
  // few seconds longer than a typical one.
  for (let attempt = 0; attempt < 40; attempt++) {
    if (await canReach(LOCAL_BACKEND_URL)) return true;
    await sleep(500);
  }
  return false;
}

function stopBundledBackend() {
  if (backendProcess) {
    backendProcess.kill();
    backendProcess = null;
  }
}

async function loadAppOrSetup(win) {
  if (!hasExplicitServerOverride()) {
    // Fully self-contained mode: try the local backend, starting it
    // ourselves if nothing is listening yet, and never prompt for an
    // address unless that genuinely fails.
    if (!(await canReach(LOCAL_BACKEND_URL))) {
      await startBundledBackend();
    }
    if (await canReach(LOCAL_BACKEND_URL)) {
      win.loadURL(`${LOCAL_BACKEND_URL}${ADMIN_PATH}`);
      return;
    }
  }

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

app.on("before-quit", () => {
  stopBundledBackend();
});
