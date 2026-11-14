/*
 * NexusOS "Nexus" default desktop layout (Plasma 6 desktop scripting API).
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Staged into the look-and-feel package as contents/layouts/org.kde.plasma.desktop-layout.js.
 * Plasma runs it only when a user session starts without an existing layout
 * (new user, or after "Apply" with "Use desktop layout from theme").
 *
 * Layout:
 *   - Top system panel: NexusOS launcher, system monitor widgets, clock, tray.
 *   - Bottom floating dock: icon-only task manager with development,
 *     infrastructure and local-AI launchers.
 *
 * Only widgets shipped by Ubuntu 26.04 Plasma packages are used:
 *   org.kde.plasma.kickoff / pager / icontasks / showdesktop (plasma-desktop)
 *   org.kde.plasma.systemmonitor.* / digitalclock / systemtray / panelspacer (plasma-workspace)
 */

var wallpaperUrl = "file:///usr/share/wallpapers/NexusOS/";

/* ---------- Desktop wallpaper ---------- */
var desktopsArray = desktopsForActivity(currentActivity());
for (var j = 0; j < desktopsArray.length; j++) {
    var d = desktopsArray[j];
    d.wallpaperPlugin = "org.kde.image";
    d.currentConfigGroup = ["Wallpaper", "org.kde.image", "General"];
    d.writeConfig("Image", wallpaperUrl);
}

/* ---------- Top system panel ---------- */
var top = new Panel;
top.location = "top";
top.height = 2 * Math.ceil(gridUnit * 1.6 / 2);
top.floating = false;

var launcher = top.addWidget("org.kde.plasma.kickoff");
launcher.currentConfigGroup = ["General"];
launcher.writeConfig("icon", "nexusos");
launcher.writeConfig("favoritesPortedToKAstats", "true");

top.addWidget("org.kde.plasma.pager");
top.addWidget("org.kde.plasma.panelspacer");

/* System monitoring widgets use the default sensors of each preset. */
top.addWidget("org.kde.plasma.systemmonitor.cpu");
top.addWidget("org.kde.plasma.systemmonitor.memory");
top.addWidget("org.kde.plasma.systemmonitor.net");

top.addWidget("org.kde.plasma.panelspacer");
top.addWidget("org.kde.plasma.digitalclock");
top.addWidget("org.kde.plasma.panelspacer");
top.addWidget("org.kde.plasma.systemtray");
top.addWidget("org.kde.plasma.showdesktop");

/* ---------- Bottom application dock ---------- */
var dock = new Panel;
dock.location = "bottom";
dock.height = 2 * Math.ceil(gridUnit * 2.75 / 2);
dock.floating = true;
dock.alignment = "center";
dock.lengthMode = "fit";
dock.hiding = "dodgewindows";

var tasks = dock.addWidget("org.kde.plasma.icontasks");
tasks.currentConfigGroup = ["General"];
tasks.writeConfig("launchers", [
    /* Everyday */
    "applications:org.kde.dolphin.desktop",
    "preferred://browser",
    /* Development */
    "applications:org.kde.konsole.desktop",
    "applications:org.kde.kate.desktop",
    "applications:org.nexusos.dev.desktop",
    /* Infrastructure */
    "applications:org.nexusos.infra.desktop",
    "applications:org.kde.plasma-systemmonitor.desktop",
    /* Local AI */
    "applications:org.nexusos.ai.desktop",
    /* System */
    "applications:org.nexusos.CommandCenter.desktop",
    "applications:systemsettings.desktop"
]);
