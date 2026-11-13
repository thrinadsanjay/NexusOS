import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Nexus.Design

Item {
    id: page
    property var controller
    property var confirm
    property string intent: ""
    readonly property var d: controller ? controller.data : ({})
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.s5
        spacing: Theme.s3
        NxPageHeader { title: "Network"; subtitle: "NetworkManager is the only network engine. Connectivity: " + (d.connectivity || "…")
            NxButton { text: "Refresh"; onClicked: controller.refresh() } }
        NxBanner { kind: "warning"; text: d.checkpoint ? "New settings applied. They roll back automatically in " + d.checkpoint.seconds + " s unless you keep them." : "" }
        NxButton { visible: !!d.checkpoint; text: "Keep changes"; variant: "primary"; onClicked: controller.keepChanges() }
        NxErrorState { message: controller ? controller.error : ""; onRetry: controller.refresh() }
        NxTabBar { id: tabs; Layout.fillWidth: true; tabs: ["Interfaces", "Connections", "Wi-Fi", "Routes & DNS", "Diagnostics", "Firewall"]
            onCurrentIndexChanged: { if (currentIndex === 2) controller.scanWifi(false); if (currentIndex === 5) controller.loadFirewall() } }
        StackLayout {
            currentIndex: tabs.currentIndex
            Layout.fillWidth: true
            Layout.fillHeight: true
            NxTable { rows: d.devices || []; columns: [{ title: "Device", role: "name", width: 0.15 }, { title: "Type", role: "type", width: 0.12 }, { title: "State", role: "state", width: 0.15 }, { title: "Connection", role: "connection", width: 0.2 }, { title: "Addresses", width: 0.25, format: r => r.addresses.join(", "), mono: true }, { title: "MAC", role: "mac", width: 0.13, mono: true }] }
            ColumnLayout {
                NxTable { id: connTable; Layout.fillWidth: true; Layout.fillHeight: true; rows: d.connections || []; columns: [{ title: "Name", role: "name", width: 0.35 }, { title: "Type", role: "type", width: 0.25 }, { title: "Device", role: "device", width: 0.2 }, { title: "Active", width: 0.2, format: r => r.active ? "yes" : "" }] }
                RowLayout {
                    enabled: !!connTable.currentRow
                    NxButton { text: "Connect"; onClicked: controller.connection(connTable.currentRow.name, "up") }
                    NxButton { text: "Disconnect"; variant: "danger"; onClicked: confirm.ask("Disconnect", "Bring '" + connTable.currentRow.name + "' down? Remote sessions over it will drop.", [], "Disconnect", true, () => controller.connection(connTable.currentRow.name, "down")) }
                }
                NxSectionTitle { text: "Static IPv4 (with automatic rollback)" }
                RowLayout {
                    NxTextField { id: sAddr; placeholderText: "192.168.1.20/24" }
                    NxTextField { id: sGw; placeholderText: "gateway" }
                    NxTextField { id: sDns; placeholderText: "DNS servers (space separated)"; Layout.fillWidth: true }
                    NxButton { text: "Apply to selected"; enabled: !!connTable.currentRow; onClicked: confirm.ask("Apply static IPv4", "NetworkManager creates a checkpoint first. If you do not press 'Keep changes' within 60 seconds, the previous configuration is restored automatically.", ["connection: " + connTable.currentRow.name, "address: " + sAddr.text, "gateway: " + sGw.text, "dns: " + sDns.text], "Apply", true, () => controller.applyStatic(connTable.currentRow.name, sAddr.text, sGw.text, sDns.text)) }
                }
                Text { text: "VPN and proxy profiles: open the KDE Network settings (System Settings › Network). IPv6 static editing: planned."; color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall }
            }
            ColumnLayout {
                NxButton { text: "Rescan"; onClicked: controller.scanWifi(true) }
                NxTable { Layout.fillWidth: true; Layout.fillHeight: true; rows: d.wifi || []; emptyText: "No Wi-Fi networks (or no Wi-Fi device)"; columns: [{ title: "SSID", role: "ssid", width: 0.4 }, { title: "Signal", width: 0.2, format: r => r.signal + " %" }, { title: "Security", role: "security", width: 0.25 }, { title: "In use", width: 0.15, format: r => r.in_use ? "yes" : "" }] }
                Text { text: "Join new Wi-Fi networks from the system tray network applet (passwords go to KDE Wallet)."; color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall }
            }
            ColumnLayout {
                NxTable { Layout.fillWidth: true; Layout.fillHeight: true; rows: d.routes || []; columns: [{ title: "Destination", role: "dst", width: 0.3, mono: true }, { title: "Gateway", width: 0.25, format: r => r.gateway || "", mono: true }, { title: "Device", role: "dev", width: 0.15 }, { title: "Protocol", role: "protocol", width: 0.15 }, { title: "Metric", width: 0.15, format: r => r.metric !== undefined ? r.metric : "" }] }
                Text { text: "DNS: " + Object.keys(d.dns || {}).map(k => k + ": " + d.dns[k].join(", ")).join("   "); color: Theme.c.text; font.family: Theme.monoFamily; font.pixelSize: Theme.fontSmall; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            }
            ColumnLayout {
                RowLayout { NxTextField { id: target; placeholderText: "host or IP"; Layout.fillWidth: true; onAccepted: controller.diagnose(text) } NxButton { text: "Run diagnostics"; variant: "primary"; onClicked: controller.diagnose(target.text) } }
                NxLoading { running: controller ? controller.busy : false; text: "Running DNS, ping, route and tracepath…" }
                NxLogView { Layout.fillWidth: true; Layout.fillHeight: true; text: (d.diagnostics || []).map(r => "== " + r.tool + (r.ok ? " (ok)" : " (failed)") + "\n" + r.output).join("\n\n") }
            }
            ColumnLayout {
                Text { text: d.firewall ? (d.firewall.installed ? "" : "ufw is not installed") : "Loading…"; color: Theme.c.textSecondary; font.family: Theme.fontFamily }
                NxLogView { Layout.fillWidth: true; Layout.fillHeight: true; text: d.firewall ? d.firewall.output : "" }
                Text { text: "Firewall rules are changed through the management agent (nexus CLI) or the KDE Firewall module."; color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall }
            }
        }
    }
}
