/*
 * Minimized System Status rail: icon-first indicators with small status dots and short values,
 * concise tooltips on hover. A click anywhere (or Enter/Space) opens the panel; hovering never does.
 */
import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.kirigami as Kirigami

Item {
    id: rail
    readonly property var tk: root.tk
    readonly property bool vertical: Plasmoid.formFactor === PlasmaCore.Types.Vertical
    readonly property int railWidth: Kirigami.Units.gridUnit * 3
    Layout.minimumWidth: vertical ? -1 : column.implicitWidth
    Layout.preferredWidth: railWidth
    Layout.minimumHeight: column.implicitHeight
    Layout.preferredHeight: column.implicitHeight
    Layout.maximumHeight: column.implicitHeight

    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: i18n("System status. %1. Press to open the panel.", Qt.formatTime(root.now))
    Keys.onPressed: event => {
        if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) {
            root.expanded = !root.expanded
            event.accepted = true
        }
    }

    MouseArea {
        anchors.fill: parent
        hoverEnabled: false
        onClicked: root.expanded = !root.expanded
    }

    // One indicator: icon (with an optional status dot) and an optional short value.
    component Indicator: PlasmaCore.ToolTipArea {
        id: ind
        property string icon
        property string value
        property color valueColor: rail.tk.textSecondary
        property color dot: "transparent"
        property bool dim: false
        property real iconScale: 1
        Layout.fillWidth: true
        implicitHeight: col.implicitHeight + Kirigami.Units.smallSpacing * 2
        ColumnLayout {
            id: col
            anchors.centerIn: parent
            spacing: 1
            Item {
                Layout.alignment: Qt.AlignHCenter
                implicitWidth: Kirigami.Units.iconSizes.smallMedium * ind.iconScale
                implicitHeight: implicitWidth
                Kirigami.Icon {
                    anchors.fill: parent
                    source: ind.icon
                    isMask: true
                    color: ind.dim ? rail.tk.textSecondary : rail.tk.text
                    opacity: ind.dim ? 0.55 : 1
                }
                Rectangle {
                    visible: ind.dot !== Qt.color("transparent")
                    width: 7; height: 7; radius: 3.5
                    anchors { right: parent.right; bottom: parent.bottom; rightMargin: -2; bottomMargin: -1 }
                    color: ind.dot
                    border.color: rail.tk.background
                    border.width: 1
                }
            }
            Text {
                visible: ind.value.length > 0
                Layout.alignment: Qt.AlignHCenter
                text: ind.value
                color: ind.valueColor
                font.pixelSize: Math.round(Kirigami.Theme.smallFont.pixelSize * 0.95)
                font.family: "Inter"
            }
        }
    }

    ColumnLayout {
        id: column
        width: parent.width
        spacing: Kirigami.Units.smallSpacing

        // NexusOS status: badge colour follows the most severe alert
        PlasmaCore.ToolTipArea {
            Layout.fillWidth: true
            implicitHeight: Kirigami.Units.iconSizes.medium + Kirigami.Units.smallSpacing * 2
            mainText: i18n("NexusOS")
            subText: root.alertCritical ? i18np("%1 critical alert", "%1 critical alerts", root.alertCritical)
                   : root.alertWarning ? i18np("%1 warning", "%1 warnings", root.alertWarning)
                   : root.status.loaded ? i18n("All systems normal") : i18n("Checking…")
            Kirigami.Icon {
                anchors.centerIn: parent
                width: Kirigami.Units.iconSizes.medium; height: width
                source: "nexusos"
            }
            Rectangle {
                visible: root.alertCritical + root.alertWarning > 0
                width: 9; height: 9; radius: 4.5
                x: parent.width / 2 + Kirigami.Units.iconSizes.medium / 2 - 6; y: 2
                color: root.alertCritical ? rail.tk.critical : rail.tk.warning
                border.color: rail.tk.background
            }
        }

        // clock + date
        PlasmaCore.ToolTipArea {
            Layout.fillWidth: true
            implicitHeight: clock.implicitHeight + Kirigami.Units.smallSpacing
            mainText: Qt.formatDate(root.now, Qt.locale().dateFormat(Locale.LongFormat))
            subText: Qt.formatTime(root.now, root.cfg.use24h ? "HH:mm" : "h:mm AP")
            ColumnLayout {
                id: clock
                anchors.centerIn: parent
                spacing: 0
                Text {
                    Layout.alignment: Qt.AlignHCenter
                    text: Qt.formatTime(root.now, root.cfg.use24h ? "HH:mm" : "h:mm")
                    color: rail.tk.text
                    font.pixelSize: Math.round(Kirigami.Theme.defaultFont.pixelSize * 1.15)
                    font.weight: Font.DemiBold
                    font.family: "Inter"
                }
                Text {
                    Layout.alignment: Qt.AlignHCenter
                    text: Qt.formatDate(root.now, "ddd d")
                    color: rail.tk.textSecondary
                    font.pixelSize: Math.round(Kirigami.Theme.smallFont.pixelSize * 0.95)
                    font.family: "Inter"
                }
            }
        }

        Rectangle { Layout.alignment: Qt.AlignHCenter; Layout.preferredWidth: rail.railWidth * 0.45; Layout.preferredHeight: 1; color: rail.tk.border }

        Indicator {
            icon: root.networkIcon()
            dot: root.online ? rail.tk.positive : rail.tk.critical
            dim: !root.online
            mainText: root.net.kind === "wifi" ? i18n("Wi-Fi: %1", root.net.name) : root.net.kind === "ethernet" ? i18n("Wired: %1", root.net.name)
                    : root.online ? i18n("Connected") : i18n("Offline")
            subText: root.net.kind === "wifi" && root.net.signal >= 0 ? i18n("Signal %1 %", root.net.signal) : ""
        }
        Indicator {
            visible: root.btAvailable
            icon: root.btOn ? "network-bluetooth-activated" : "network-bluetooth-inactive"
            dot: root.btConnected > 0 ? rail.tk.accent : "transparent"
            dim: !root.btOn
            mainText: root.btOn ? i18n("Bluetooth on") : i18n("Bluetooth off")
            subText: root.btConnected > 0 ? i18np("%1 device connected", "%1 devices connected", root.btConnected) : ""
        }
        Indicator {
            icon: "network-vpn"
            dot: root.net.vpn.length ? rail.tk.positive : "transparent"
            dim: root.net.vpn.length === 0
            mainText: root.net.vpn.length ? i18n("VPN active") : i18n("VPN not connected")
            subText: root.net.vpn.join(", ")
        }
        Indicator {
            visible: root.hasBattery
            icon: root.batteryIcon()
            value: root.batteryPercent >= 0 ? root.batteryPercent + "%" : ""
            valueColor: root.batteryState === "Charging" ? rail.tk.positive : root.batteryPercent <= 15 ? rail.tk.critical : rail.tk.textSecondary
            mainText: i18n("Battery %1 %", root.batteryPercent)
            subText: root.batteryState === "Charging" ? i18n("Charging") : root.batteryRemainingMs > 0 ? i18n("%1 remaining", root.duration(root.batteryRemainingMs)) : root.batteryState
        }

        Rectangle { Layout.alignment: Qt.AlignHCenter; Layout.preferredWidth: rail.railWidth * 0.45; Layout.preferredHeight: 1; color: rail.tk.border }

        Indicator {
            icon: Qt.resolvedUrl("../icons/cpu.svg")
            value: root.cfg.showPercentages && root.cpu >= 0 ? root.cpu + "%" : ""
            valueColor: root.levelColor(root.cpu)
            mainText: i18n("CPU %1 %", root.cpu)
        }
        Indicator {
            icon: Qt.resolvedUrl("../icons/memory.svg")
            value: root.cfg.showPercentages && root.memory >= 0 ? root.memory + "%" : ""
            valueColor: root.levelColor(root.memory)
            mainText: i18n("Memory %1 %", root.memory)
        }
        Indicator {
            icon: Qt.resolvedUrl("../icons/disk.svg")
            value: root.cfg.showPercentages && root.disk >= 0 ? root.disk + "%" : ""
            valueColor: root.levelColor(root.disk)
            mainText: i18n("Disk %1 % used", root.disk)
            subText: root.status.root ? i18n("%1 free on %2", root.bytes(root.status.root.free), root.status.root.mount) : ""
        }

        // expand / collapse
        PlasmaCore.ToolTipArea {
            Layout.fillWidth: true
            implicitHeight: Kirigami.Units.iconSizes.small + Kirigami.Units.smallSpacing * 2
            mainText: root.expanded ? i18n("Close the panel") : i18n("Open the System Status panel")
            Kirigami.Icon {
                anchors.centerIn: parent
                width: Kirigami.Units.iconSizes.small; height: width
                source: root.expanded ? "arrow-right" : "arrow-left"
                isMask: true
                color: rail.tk.accent
            }
        }
    }
}
