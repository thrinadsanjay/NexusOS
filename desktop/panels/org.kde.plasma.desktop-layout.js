/*
 * NexusOS "Nexus" default desktop layout (Plasma 6 desktop scripting API).
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Staged into the look-and-feel package as contents/layouts/org.kde.plasma.desktop-layout.js.
 * Plasma runs it only when a user session starts without an existing layout
 * (new user, or after "Apply" with "Use desktop layout from theme").
 *
 * Two persistent elements, nothing else (no top bar, no taskbar, no system tray):
 *   - left:  floating vertical launcher rail
 *            [NexusOS logo, Show Desktop] [application menu (Kickoff)] [files, terminal,
 *             containers, VMs, cloud, AI, expand]   (optional tools only when installed)
 *   - right: floating vertical System Status rail (expands into the control panel) and the
 *            notification bell. The bell is Plasma's own notifications applet: Plasma shows
 *            notification pop-ups only while that applet exists, so it is kept, as the rail's
 *            notification indicator.
 * The centre is the wallpaper. Widgets: org.nexusos.launcher and org.nexusos.status (nexusos-theme),
 * org.kde.plasma.kickoff / notifications (plasma-desktop, plasma-workspace).
 */

var wallpaperUrl = "file:///usr/share/wallpapers/NexusOS/";

/* ---------- Desktop wallpaper, no desktop icons/widgets ---------- */
var desktopsArray = desktopsForActivity(currentActivity());
for (var j = 0; j < desktopsArray.length; j++) {
    var d = desktopsArray[j];
    d.wallpaperPlugin = "org.kde.image";
    d.currentConfigGroup = ["Wallpaper", "org.kde.image", "General"];
    d.writeConfig("Image", wallpaperUrl);
}

/* Remove panels a previous layout or the distribution default may have created. */
var existing = panels();
for (var p = 0; p < existing.length; p++) {
    existing[p].remove();
}

function railPanel(edge) {
    var panel = new Panel;
    panel.location = edge;
    panel.floating = true;
    panel.alignment = "center";
    panel.lengthMode = "fit";
    panel.hiding = "none";
    panel.height = 2 * Math.ceil(gridUnit * 3.1 / 2);   // thickness of a vertical panel
    return panel;
}

/* ---------- Left: launcher rail ---------- */
var left = railPanel("left");

var head = left.addWidget("org.nexusos.launcher");
head.currentConfigGroup = ["General"];
head.writeConfig("items", ["logo", "home"]);

var apps = left.addWidget("org.kde.plasma.kickoff");
apps.currentConfigGroup = ["General"];
apps.writeConfig("icon", "nexusos-apps-symbolic");
apps.writeConfig("favoritesPortedToKAstats", "true");

var tools = left.addWidget("org.nexusos.launcher");
tools.globalShortcut = "Meta+Alt+A";     /* expanded launcher (all shortcuts with names) */
tools.currentConfigGroup = ["General"];
tools.writeConfig("items", ["files", "terminal", "containers", "vms", "cloud", "ai", "more"]);

/* ---------- Right: System Status rail + notification bell ---------- */
var right = railPanel("right");

var status = right.addWidget("org.nexusos.status");
status.globalShortcut = "Meta+Alt+S";    /* open/close the System Status panel */
var bell = right.addWidget("org.kde.plasma.notifications");
bell.globalShortcut = "Meta+N";
status.currentConfigGroup = ["General"];
status.writeConfig("notificationsApplet", String(bell.id));
