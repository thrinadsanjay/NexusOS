/*
 * NexusOS System Status (Plasma 6 applet).
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Compact representation: the narrow rail on the right edge (clock, date, network, Bluetooth,
 * VPN, battery, CPU, memory, disk, expand). Full representation: the floating System Status
 * panel (opens on click; closes on Escape or a click outside unless pinned).
 *
 * Data comes from native KDE/Linux services, event-driven where they offer it:
 *   KSystemStats sensors (CPU, memory, GPU, disk), NetworkManager (plasma-nm), BlueZ (BluezQt),
 *   UPower via PowerDevil (plasma5support "powermanagement"), the notification server
 *   (notificationmanager). Health, alerts, storage and services come from
 *   `nexus system desktop-status --json` (cached; every few minutes and when the panel opens).
 * Nothing here needs root; switches use the session's own NetworkManager/BlueZ permissions.
 */
import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.plasma.plasma5support as P5Support
import org.kde.ksysguard.sensors as Sensors
import org.kde.plasma.networkmanagement as PlasmaNM
import org.kde.bluezqt as BluezQt
import org.kde.notificationmanager as NotificationManager
import org.kde.kirigami as Kirigami

PlasmoidItem {
    id: root

    readonly property var cfg: Plasmoid.configuration
    readonly property alias tk: tokens

    // ------------------------------------------------------------------ popup behaviour
    switchWidth: Kirigami.Units.gridUnit * 10
    switchHeight: Kirigami.Units.gridUnit * 10
    preferredRepresentation: compactRepresentation
    hideOnWindowDeactivate: !cfg.pinned
    compactRepresentation: Rail {}
    fullRepresentation: StatusPanel {}
    toolTipMainText: Qt.formatTime(now, cfg.use24h ? "HH:mm" : "h:mm AP")
    toolTipSubText: Qt.formatDate(now, Qt.locale().dateFormat(Locale.LongFormat))
    Plasmoid.icon: "nexusos"
    Plasmoid.backgroundHints: PlasmaCore.Types.NoBackground

    onExpandedChanged: {
        cfg.wasExpanded = expanded
        if (expanded) refreshStatus()
    }
    Component.onCompleted: {
        refreshNetwork()
        refreshStatus()
        if (cfg.pinned && cfg.wasExpanded) Qt.callLater(() => root.expanded = true)  // restore pinned panel
    }

    Tokens { id: tokens }

    // ------------------------------------------------------------------ clock
    property date now: new Date()
    Timer {   // aligned to the minute: one wake-up per minute
        interval: (60 - new Date().getSeconds()) * 1000 + 50
        running: true
        repeat: true
        onTriggered: { root.now = new Date(); interval = 60000 }
    }

    // ------------------------------------------------------------------ load (KSystemStats)
    Sensors.Sensor { id: cpuSensor; sensorId: "cpu/all/usage"; updateRateLimit: 2000 }
    Sensors.Sensor { id: memSensor; sensorId: "memory/physical/usedPercent"; updateRateLimit: 2000 }
    Sensors.Sensor { id: diskSensor; sensorId: "disk/all/usedPercent"; updateRateLimit: 10000 }
    Sensors.Sensor { id: gpuSensor; sensorId: "gpu/all/usage"; updateRateLimit: 2000 }
    function pct(sensor) {
        return sensor.status === Sensors.Sensor.Ready && sensor.value !== undefined && !isNaN(sensor.value) ? Math.round(sensor.value) : -1
    }
    readonly property int cpu: pct(cpuSensor)
    readonly property int memory: pct(memSensor)
    readonly property int disk: status.root ? Math.round(status.root.percent) : pct(diskSensor)
    readonly property int gpu: pct(gpuSensor)

    // ------------------------------------------------------------------ network (NetworkManager)
    PlasmaNM.NetworkStatus {
        id: networkStatus
        onActiveConnectionsChanged: root.refreshNetwork()   // event-driven: re-read names on change
    }
    PlasmaNM.EnabledConnections { id: enabledConnections }
    PlasmaNM.Handler { id: nmHandler }
    property var net: ({ kind: "none", name: "", signal: -1, vpn: [], wifiDevice: false })
    readonly property bool online: net.kind !== "none"
    readonly property bool wifiEnabled: enabledConnections.wirelessEnabled
    readonly property bool wifiAvailable: enabledConnections.wirelessHwEnabled || net.wifiDevice
    function setWifi(on) { nmHandler.enableWireless(on); Qt.callLater(refreshNetwork) }
    function refreshNetwork() {
        run("nexus-net", "LC_ALL=C nmcli -t -f TYPE,NAME,DEVICE connection show --active; echo '--'; "
            + "LC_ALL=C nmcli -t -f IN-USE,SIGNAL device wifi list --rescan no 2>/dev/null | grep '^\\*'; echo '--'; "
            + "LC_ALL=C nmcli -t -f TYPE device 2>/dev/null")
    }
    function parseNetwork(out) {
        const parts = out.split("--\n")
        const active = (parts[0] || "").split("\n").filter(l => l).map(l => l.split(":"))
        const wifi = active.find(c => c[0] === "802-11-wireless")
        const wired = active.find(c => c[0] === "802-3-ethernet")
        const vpn = active.filter(c => c[0] === "vpn" || c[0] === "wireguard").map(c => c[1])
        const sig = ((parts[1] || "").split(":")[1] || "").trim()
        net = {
            kind: wifi ? "wifi" : wired ? "ethernet" : active.some(c => c[0] !== "loopback" && c[0] !== "bridge") ? "other" : "none",
            name: wifi ? wifi[1] : wired ? wired[1] : "",
            signal: sig ? parseInt(sig) : -1,
            vpn: vpn,
            wifiDevice: (parts[2] || "").split("\n").indexOf("wifi") >= 0
        }
    }

    // ------------------------------------------------------------------ Bluetooth (BlueZ)
    readonly property bool btAvailable: BluezQt.Manager.operational && BluezQt.Manager.adapters.length > 0
    readonly property bool btOn: btAvailable && BluezQt.Manager.bluetoothOperational && !BluezQt.Manager.bluetoothBlocked
    readonly property int btConnected: BluezQt.Manager.devices.filter(d => d.connected).length
    function setBluetooth(on) { BluezQt.Manager.bluetoothBlocked = !on }

    // ------------------------------------------------------------------ battery (UPower via PowerDevil)
    P5Support.DataSource {
        id: pm
        engine: "powermanagement"
        connectedSources: ["Battery", "AC Adapter"]
        interval: 0
        onSourceAdded: source => { if (source.startsWith("Battery") && source !== "Battery") connectSource(source) }
    }
    readonly property var batteryData: pm.data["Battery"] || ({})
    readonly property bool hasBattery: !!batteryData["Has Battery"] && batteryData["Has Cumulative"] !== false
    readonly property int batteryPercent: batteryData["Percent"] !== undefined ? batteryData["Percent"] : -1
    readonly property string batteryState: batteryData["State"] || ""   // Charging | Discharging | FullyCharged | NoCharge
    readonly property bool pluggedIn: !!(pm.data["AC Adapter"] || {})["Plugged in"]
    readonly property real batteryRemainingMs: batteryData["Remaining msec"] || 0
    readonly property int batteryHealth: {
        for (const s of pm.connectedSources) {
            const d = pm.data[s] || {}
            if (s !== "Battery" && s.startsWith("Battery") && d["Capacity"] !== undefined && d["Is Power Supply"]) return d["Capacity"]
        }
        return -1
    }

    // ------------------------------------------------------------------ notifications / focus mode
    NotificationManager.Notifications {
        id: notifications
        showExpired: true
        showDismissed: false
        showJobs: false
    }
    NotificationManager.Settings { id: notificationSettings }
    readonly property int unread: notifications.unreadNotificationsCount
    readonly property bool focusMode: notificationSettings.notificationsInhibitedUntil > now
    function setFocusMode(on) {
        const until = new Date()
        if (on) until.setFullYear(until.getFullYear() + 1)   // until switched off
        notificationSettings.notificationsInhibitedUntil = on ? until : new Date(0)
        notificationSettings.save()
        now = new Date()
    }

    // ------------------------------------------------------------------ health, alerts, storage, services
    property var status: ({ loaded: false })
    Timer { interval: Math.max(60, cfg.statusInterval) * 1000; running: true; repeat: true; onTriggered: root.refreshStatus() }
    function refreshStatus() { run("nexus-status", "nexus system desktop-status --json 2>/dev/null") }
    readonly property int alertCritical: status.counts ? status.counts.critical : 0
    readonly property int alertWarning: status.counts ? status.counts.warning : 0

    // ------------------------------------------------------------------ commands (executable engine)
    P5Support.DataSource {
        id: exec
        engine: "executable"
        connectedSources: []
        property var tags: ({})
        onNewData: (source, data) => {
            const tag = tags[source]
            delete tags[source]
            disconnectSource(source)
            const out = data["stdout"] || ""
            if (tag === "nexus-net") root.parseNetwork(out)
            else if (tag === "nexus-status") {
                try { const s = JSON.parse(out); s.loaded = true; root.status = s } catch (e) { root.status = { loaded: true, error: true } }
            }
        }
    }
    // Commands are fixed strings in this file; nothing typed by the user is ever executed.
    function run(tag, cmd) {
        const unique = cmd + " #" + Date.now() + Math.random()
        exec.tags[unique] = tag
        exec.connectSource(unique)
    }
    function launch(cmd) { run("launch", cmd + " >/dev/null 2>&1 &") }
    function openCenter(page) { launch("nexus-center --page " + (page || "overview")); root.expanded = false }
    function openNotifications() {
        root.expanded = false
        if (cfg.notificationsApplet) {
            launch("qdbus6 org.kde.kglobalaccel /component/plasmashell org.kde.kglobalaccel.Component.invokeShortcut 'activate widget "
                   + cfg.notificationsApplet + "'")
        }
    }
    function lockScreen() { root.expanded = false; launch("loginctl lock-session") }
    function powerMenu() { root.expanded = false; launch("qdbus6 org.kde.LogoutPrompt /LogoutPrompt org.kde.LogoutPrompt.promptAll") }
    function systemSettings(module) { root.expanded = false; launch(module ? "systemsettings " + module : "systemsettings") }

    // ------------------------------------------------------------------ formatting
    function duration(ms) {
        const m = Math.round(ms / 60000)
        return m >= 60 ? Math.floor(m / 60) + " h " + (m % 60) + " min" : m + " min"
    }
    function bytes(n) {
        if (n === undefined || n === null) return "–"
        if (n >= 1e12) return (n / 1e12).toFixed(1) + " TB"
        if (n >= 1e9) return (n / 1e9).toFixed(n >= 1e11 ? 0 : 1) + " GB"
        return Math.round(n / 1e6) + " MB"
    }
    function levelColor(p) { return p >= 95 ? tk.critical : p >= 85 ? tk.warning : tk.accent }
    function batteryIcon() {
        const level = batteryPercent < 0 ? "missing" : batteryPercent >= 90 ? "100" : batteryPercent >= 70 ? "080"
                    : batteryPercent >= 50 ? "060" : batteryPercent >= 30 ? "040" : batteryPercent >= 10 ? "020" : "000"
        return "battery-" + level + (batteryState === "Charging" ? "-charging" : "")
    }
    function networkIcon() {
        if (net.kind === "wifi") {
            const s = net.signal
            return "network-wireless-connected-" + (s >= 80 ? "100" : s >= 55 ? "75" : s >= 30 ? "50" : s >= 0 ? "25" : "100")
        }
        if (net.kind === "ethernet" || net.kind === "other") return "network-wired-activated"
        return wifiAvailable && !wifiEnabled ? "network-wireless-disconnected" : "network-offline"
    }
}
