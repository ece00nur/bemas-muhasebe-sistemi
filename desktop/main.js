const { app, BrowserWindow, Menu } = require("electron");
const path = require("path");

// The desktop client is a thin shell: it starts (or connects to) the local
// FastAPI backend and opens its admin-panel UI in a native window. Everything
// runs on this machine - no public website, no domain, no hosting involved.
const SERVER_URL = process.env.BEMAS_SERVER_URL || "http://localhost:8000";
const ADMIN_PATH = "/adminpanel/";

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

  Menu.setApplicationMenu(null);
  win.loadURL(`${SERVER_URL}${ADMIN_PATH}`);

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

app.whenReady().then(() => {
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
