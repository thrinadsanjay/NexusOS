/*
 * NexusOS launcher rail (Plasma 6 applet).
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Icon-only shortcuts in a vertical panel: hover for the name, click to start (or bring the
 * running window forward), a dot marks running applications (TaskManager model). Optional
 * tools appear only when installed: an entry is shown when one of its .desktop files exists
 * and its TryExec program is present (checked at start-up and every few minutes).
 * The "more" entry opens the expanded launcher: every shortcut with its name and description.
 */
import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.plasma5support as P5Support
import org.kde.taskmanager as TaskManager
import org.kde.kirigami as Kirigami

PlasmoidItem {
    id: root

    readonly property var cfg: Plasmoid.configuration
    preferredRepresentation: compactRepresentation
    compactRepresentation: Rail {}
    fullRepresentation: Expanded {}
    Plasmoid.icon: "nexusos"
    Plasmoid.backgroundHints: PlasmaCore.Types.NoBackground

    // ------------------------------------------------------------------ catalogue
    // desktop: candidate .desktop ids (first installed wins); action: built-in behaviour.
    readonly property var catalogue: ({
        logo: { title: i18n("Nexus Command Center"), description: i18n("System administration and status"), icon: "nexusos", logo: true, desktop: ["org.nexusos.CommandCenter"] },
        home: { title: i18n("Show Desktop"), description: i18n("Minimise all windows (press again to restore)"), icon: "home", action: "desktop" },
        files: { title: i18n("Files"), description: i18n("File manager"), icon: "files", desktop: ["org.kde.dolphin"] },
        terminal: { title: i18n("Terminal"), description: i18n("Konsole"), icon: "terminal", desktop: ["org.kde.konsole"] },
        containers: { title: i18n("Containers"), description: i18n("Docker and Podman in the Command Center"), icon: "containers", desktop: ["org.nexusos.containers"] },
        vms: { title: i18n("Virtual Machines"), description: i18n("Virtual Machine Manager"), icon: "vms", desktop: ["virt-manager", "org.virt_manager.virt-manager", "org.gnome.Boxes"] },
        cloud: { title: i18n("Cloud Platform"), description: i18n("Nexus applications and gateway"), icon: "cloud", desktop: ["org.nexusos.cloud"] },
        ai: { title: i18n("AI Assistant"), description: i18n("Local models with Ollama"), icon: "ai", desktop: ["org.nexusos.ai-assistant"] },
        browser: { title: i18n("Web Browser"), description: i18n("Default browser"), icon: "browser", desktop: ["firefox", "org.mozilla.firefox", "chromium", "org.kde.falkon"] },
        editor: { title: i18n("Text Editor"), description: i18n("Kate"), icon: "editor", desktop: ["org.kde.kate"] },
        monitor: { title: i18n("System Monitor"), description: i18n("Processes and resources"), icon: "monitor", desktop: ["org.kde.plasma-systemmonitor"] },
        settings: { title: i18n("System Settings"), description: i18n("KDE System Settings"), icon: "settings", desktop: ["systemsettings"] },
        more: { title: i18n("All shortcuts"), description: i18n("Show every shortcut with its name"), icon: "more", action: "expand" }
    })
    readonly property var allIds: Object.keys(catalogue)
    property var installed: ({})   // id -> resolved desktop id ("" = not installed)
    readonly property var visibleItems: (cfg.items || []).filter(id => catalogue[id] && (cfg.hiddenItems || []).indexOf(id) < 0 && isAvailable(id))
    function isAvailable(id) {
        const e = catalogue[id]
        return !!e && (!!e.action || !!installed[id])
    }
    function iconSource(id) {
        const e = catalogue[id]
        return e.logo ? e.icon : Qt.resolvedUrl("../icons/" + e.icon + ".svg")
    }

    // ------------------------------------------------------------------ availability (desktop file + TryExec)
    Component.onCompleted: refreshInstalled()
    Timer { interval: 5 * 60 * 1000; running: true; repeat: true; onTriggered: root.refreshInstalled() }
    function refreshInstalled() {
        const pairs = []
        for (const id of allIds) for (const d of (catalogue[id].desktop || [])) pairs.push(id + ":" + d)
        // Shell reads only .desktop files from the XDG data dirs; ids come from the catalogue above.
        const script = 'for p in ' + pairs.join(" ") + '; do id=${p%%:*}; d=${p#*:}; '
            + 'for dir in "${XDG_DATA_HOME:-$HOME/.local/share}" $(echo "${XDG_DATA_DIRS:-/usr/local/share:/usr/share}" | tr : " "); do '
            + 'f="$dir/applications/$d.desktop"; [ -f "$f" ] || continue; '
            + 't=$(sed -n "s/^TryExec=//p" "$f" | head -1); '
            + 'if [ -z "$t" ] || command -v "$t" >/dev/null 2>&1; then echo "$id=$d"; fi; break; done; done'
        run("installed", script)
    }

    // ------------------------------------------------------------------ running applications
    TaskManager.TasksModel {
        id: tasks
        groupMode: TaskManager.TasksModel.GroupApplications
        filterByVirtualDesktop: false
        filterByScreen: false
        filterByActivity: false
        filterNotMinimized: false
        onCountChanged: root.refreshRunning()
        onDataChanged: root.refreshRunning()
    }
    property var running: ({})   // desktop id -> { row, active }
    function refreshRunning() {
        const out = {}
        for (let i = 0; i < tasks.count; i++) {
            const idx = tasks.makeModelIndex(i)
            if (tasks.data(idx, TaskManager.AbstractTasksModel.IsLauncher)) continue
            const appId = String(tasks.data(idx, TaskManager.AbstractTasksModel.AppId) || "").replace(/\.desktop$/, "")
            if (appId) out[appId] = { row: i, active: !!tasks.data(idx, TaskManager.AbstractTasksModel.IsActive) }
        }
        running = out
    }
    function runningOf(id) { return installed[id] ? running[installed[id]] : undefined }

    // ------------------------------------------------------------------ actions
    function activate(id) {
        const e = catalogue[id]
        if (e.action === "desktop") { run("launch", "qdbus6 org.kde.kglobalaccel /component/kwin org.kde.kglobalaccel.Component.invokeShortcut 'Show Desktop'"); return }
        if (e.action === "expand") { root.expanded = !root.expanded; return }
        const r = runningOf(id)
        if (r) { tasks.requestActivate(tasks.makeModelIndex(r.row)); root.expanded = false; return }
        launch(id)
    }
    function launch(id) {
        const d = installed[id]
        if (!d) return
        run("launch", "(kstart --application " + d + ".desktop || gtk-launch " + d + ") >/dev/null 2>&1 &")
        root.expanded = false
    }

    P5Support.DataSource {
        id: exec
        engine: "executable"
        connectedSources: []
        property var tags: ({})
        onNewData: (source, data) => {
            const tag = tags[source]
            delete tags[source]
            disconnectSource(source)
            if (tag === "installed") {
                const map = {}
                for (const line of (data["stdout"] || "").split("\n")) {
                    const eq = line.indexOf("=")
                    if (eq > 0 && !map[line.slice(0, eq)]) map[line.slice(0, eq)] = line.slice(eq + 1)
                }
                root.installed = map
                root.refreshRunning()
            }
        }
    }
    // Commands are built from the fixed catalogue above; nothing typed by the user is executed.
    function run(tag, cmd) {
        const unique = cmd + " #" + Date.now() + Math.random()
        exec.tags[unique] = tag
        exec.connectSource(unique)
    }
}
