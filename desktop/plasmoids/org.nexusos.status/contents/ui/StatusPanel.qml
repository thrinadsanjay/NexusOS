/*
 * Expanded System Status panel: header, connectivity, battery, resources, health and alerts,
 * storage, services and quick controls. A control surface, not a copy of the Command Center:
 * details open the matching Command Center page.
 */
import QtQuick
import QtQuick.Layouts
import QtQuick.Shapes
import QtQuick.Window
import QtQuick.Controls as QQC2
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PlasmaComponents3
import org.kde.plasma.workspace.calendar as PlasmaCalendar
import org.kde.kirigami as Kirigami

Item {
    id: panel
    readonly property var tk: root.tk
    readonly property int pad: Kirigami.Units.largeSpacing
    property bool showCalendar: false

    Layout.minimumWidth: Kirigami.Units.gridUnit * 21
    Layout.preferredWidth: Kirigami.Units.gridUnit * 22
    Layout.maximumWidth: Kirigami.Units.gridUnit * 24
    Layout.preferredHeight: Math.min(flick.contentHeight + 2, Screen.height * 0.9)
    Layout.minimumHeight: Kirigami.Units.gridUnit * 12

    Keys.onEscapePressed: root.expanded = false

    // ------------------------------------------------------------------ building blocks
    component Tile: Rectangle {
        id: tile
        property bool active: false
        property bool interactive: true
        signal clicked()
        radius: panel.tk.radius
        color: tileMouse.containsMouse && interactive ? panel.tk.tileHover : panel.tk.tile
        border.color: active ? panel.tk.borderStrong : panel.tk.border
        border.width: 1
        activeFocusOnTab: interactive
        Accessible.role: Accessible.Button
        Keys.onPressed: event => { if (event.key === Qt.Key_Return || event.key === Qt.Key_Space) { tile.clicked(); event.accepted = true } }
        Rectangle {   // keyboard focus ring
            anchors.fill: parent; anchors.margins: -2; radius: parent.radius + 2
            color: "transparent"; border.color: panel.tk.accent; border.width: 2
            visible: tile.activeFocus
        }
        MouseArea {
            id: tileMouse
            anchors.fill: parent
            hoverEnabled: true
            enabled: tile.interactive
            cursorShape: tile.interactive ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: tile.clicked()
        }
    }
    component Label: Text {
        color: panel.tk.text
        font.family: "Inter"
        font.pixelSize: Kirigami.Theme.defaultFont.pixelSize
        elide: Text.ElideRight
    }
    component Muted: Label { color: panel.tk.textSecondary; font.pixelSize: Kirigami.Theme.smallFont.pixelSize }
    component Glyph: Kirigami.Icon {
        property color tint: panel.tk.text
        isMask: !String(source).startsWith("file:")   // own outline SVGs are drawn as they are
        color: tint
        implicitWidth: Kirigami.Units.iconSizes.smallMedium
        implicitHeight: implicitWidth
    }
    // A section card with a title row; optional chevron opens the Command Center or expands details.
    component Section: Tile {
        id: sec
        property string title
        property string iconName
        property string summary
        property color summaryColor: panel.tk.textSecondary
        property bool expandable: false
        property bool open: false
        default property alias content: body.data
        Layout.fillWidth: true
        implicitHeight: secCol.implicitHeight + panel.pad * 1.5
        interactive: true
        onClicked: expandable ? (open = !open) : null
        ColumnLayout {
            id: secCol
            anchors { left: parent.left; right: parent.right; top: parent.top; margins: panel.pad * 0.75 }
            spacing: Kirigami.Units.smallSpacing
            RowLayout {
                Layout.fillWidth: true
                spacing: Kirigami.Units.smallSpacing * 2
                Glyph { source: sec.iconName; tint: panel.tk.accent; implicitWidth: Kirigami.Units.iconSizes.small }
                Label { text: sec.title; font.weight: Font.DemiBold }
                Label { Layout.fillWidth: true; text: sec.summary; color: sec.summaryColor; horizontalAlignment: Text.AlignRight; font.pixelSize: Kirigami.Theme.smallFont.pixelSize }
                Glyph { source: sec.expandable ? (sec.open ? "arrow-up" : "arrow-down") : "arrow-right"; tint: panel.tk.textSecondary; implicitWidth: Kirigami.Units.iconSizes.small }
            }
            ColumnLayout { id: body; Layout.fillWidth: true; spacing: Kirigami.Units.smallSpacing }
        }
    }
    component Ring: Tile {
        id: ring
        property string label
        property int value: -1
        property color tint: panel.tk.accent
        Layout.fillWidth: true
        implicitHeight: Kirigami.Units.gridUnit * 4.6
        Accessible.name: label + " " + (value >= 0 ? value + "%" : "")
        Shape {
            id: shape
            width: Kirigami.Units.gridUnit * 3.2; height: width
            anchors.centerIn: parent
            preferredRendererType: Shape.CurveRenderer
            ShapePath {
                strokeColor: Qt.rgba(panel.tk.textSecondary.r, panel.tk.textSecondary.g, panel.tk.textSecondary.b, 0.18)
                strokeWidth: 4; fillColor: "transparent"; capStyle: ShapePath.RoundCap
                PathAngleArc { centerX: shape.width / 2; centerY: shape.height / 2; radiusX: shape.width / 2 - 3; radiusY: radiusX; startAngle: 0; sweepAngle: 360 }
            }
            ShapePath {
                strokeColor: ring.tint
                strokeWidth: 4; fillColor: "transparent"; capStyle: ShapePath.RoundCap
                PathAngleArc { centerX: shape.width / 2; centerY: shape.height / 2; radiusX: shape.width / 2 - 3; radiusY: radiusX; startAngle: -90; sweepAngle: Math.max(0, ring.value) * 3.6 }
            }
        }
        ColumnLayout {
            anchors.centerIn: shape
            spacing: -2
            Muted { Layout.alignment: Qt.AlignHCenter; text: ring.label }
            Label { Layout.alignment: Qt.AlignHCenter; text: ring.value >= 0 ? ring.value + "%" : "–"; font.weight: Font.DemiBold }
        }
    }
    component Quick: Tile {
        id: q
        property string iconName
        property string label
        property bool on: false
        Layout.fillWidth: true
        implicitHeight: Kirigami.Units.gridUnit * 3.6
        active: on
        Accessible.name: label
        ColumnLayout {
            anchors.centerIn: parent
            spacing: Kirigami.Units.smallSpacing
            Glyph { Layout.alignment: Qt.AlignHCenter; source: q.iconName; tint: q.on ? panel.tk.accent : panel.tk.text }
            Muted { Layout.alignment: Qt.AlignHCenter; text: q.label; color: q.on ? panel.tk.accent : panel.tk.textSecondary }
        }
    }
    component Bar: Rectangle {
        property real fraction: 0
        property color tint: panel.tk.accent
        Layout.fillWidth: true
        implicitHeight: 6
        radius: 3
        color: Qt.rgba(panel.tk.textSecondary.r, panel.tk.textSecondary.g, panel.tk.textSecondary.b, 0.18)
        Rectangle { width: parent.width * Math.max(0, Math.min(1, parent.fraction)); height: parent.height; radius: 3; color: parent.tint }
    }

    // ------------------------------------------------------------------ content
    Flickable {
        id: flick
        anchors.fill: parent
        contentHeight: content.implicitHeight + panel.pad * 2
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        QQC2.ScrollBar.vertical: QQC2.ScrollBar { policy: flick.contentHeight > flick.height ? QQC2.ScrollBar.AsNeeded : QQC2.ScrollBar.AlwaysOff }

        ColumnLayout {
            id: content
            x: panel.pad
            y: panel.pad
            width: flick.width - panel.pad * 2
            spacing: Kirigami.Units.smallSpacing * 2

            // A. header
            RowLayout {
                Layout.fillWidth: true
                spacing: Kirigami.Units.largeSpacing
                Kirigami.Icon { source: "nexusos"; implicitWidth: Kirigami.Units.iconSizes.large; implicitHeight: implicitWidth }
                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 0
                    Label { text: Qt.formatTime(root.now, root.cfg.use24h ? "HH:mm" : "h:mm AP"); font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * 2; font.weight: Font.DemiBold }
                    Muted { text: Qt.formatDate(root.now, "dddd, d MMMM yyyy"); font.pixelSize: Kirigami.Theme.defaultFont.pixelSize }
                }
                PlasmaComponents3.ToolButton {
                    icon.name: "view-calendar"; checkable: true; checked: panel.showCalendar
                    onToggled: panel.showCalendar = checked
                    PlasmaComponents3.ToolTip.text: i18n("Calendar"); PlasmaComponents3.ToolTip.visible: hovered
                    Accessible.name: i18n("Calendar")
                }
                PlasmaComponents3.ToolButton {
                    icon.name: root.cfg.pinned ? "window-unpin" : "window-pin"; checkable: true; checked: root.cfg.pinned
                    onToggled: root.cfg.pinned = checked
                    PlasmaComponents3.ToolTip.text: root.cfg.pinned ? i18n("Unpin: close when clicking elsewhere") : i18n("Pin: keep the panel open")
                    PlasmaComponents3.ToolTip.visible: hovered
                    Accessible.name: i18n("Pin the panel")
                }
                PlasmaComponents3.ToolButton {
                    icon.name: "configure"
                    onClicked: Plasmoid.internalAction("configure").trigger()
                    PlasmaComponents3.ToolTip.text: i18n("Panel settings"); PlasmaComponents3.ToolTip.visible: hovered
                    Accessible.name: i18n("Panel settings")
                }
            }
            Loader {
                Layout.fillWidth: true
                Layout.preferredHeight: active ? Kirigami.Units.gridUnit * 15 : 0
                active: panel.showCalendar
                visible: active
                sourceComponent: PlasmaCalendar.MonthView { today: root.now; showWeekNumbers: false }
            }

            // B. connectivity
            GridLayout {
                Layout.fillWidth: true
                columns: 4
                columnSpacing: Kirigami.Units.smallSpacing * 2
                rowSpacing: columnSpacing
                Repeater {
                    model: [
                        { key: "wifi", visible: true },
                        { key: "bt", visible: root.btAvailable },
                        { key: "vpn", visible: true },
                        { key: "notifications", visible: true }
                    ].filter(x => x.visible)
                    Tile {
                        id: conn
                        required property var modelData
                        readonly property string key: modelData.key
                        Layout.fillWidth: true
                        implicitHeight: Kirigami.Units.gridUnit * 4
                        active: key === "wifi" ? root.online : key === "bt" ? root.btOn : key === "vpn" ? root.net.vpn.length > 0 : root.unread > 0
                        Accessible.name: connTitle.text + " " + connSub.text
                        onClicked: {
                            if (key === "wifi") { if (root.wifiAvailable) root.setWifi(!root.wifiEnabled); else root.systemSettings("kcm_networkmanagement") }
                            else if (key === "bt") root.setBluetooth(!root.btOn)
                            else if (key === "vpn") root.systemSettings("kcm_networkmanagement")
                            else root.openNotifications()
                        }
                        PlasmaComponents3.ToolTip.visible: connHover.hovered
                        PlasmaComponents3.ToolTip.text: key === "wifi" ? (root.wifiAvailable ? i18n("Click to turn Wi-Fi %1", root.wifiEnabled ? i18n("off") : i18n("on")) : i18n("Network settings"))
                                                      : key === "bt" ? i18n("Click to turn Bluetooth %1", root.btOn ? i18n("off") : i18n("on"))
                                                      : key === "vpn" ? i18n("VPN connections") : i18n("Notification history")
                        HoverHandler { id: connHover }
                        ColumnLayout {
                            anchors.fill: parent; anchors.margins: Kirigami.Units.smallSpacing
                            spacing: 2
                            Item {
                                Layout.alignment: Qt.AlignHCenter
                                implicitWidth: Kirigami.Units.iconSizes.smallMedium; implicitHeight: implicitWidth
                                Glyph {
                                    anchors.fill: parent
                                    source: conn.key === "wifi" ? root.networkIcon() : conn.key === "bt" ? (root.btOn ? "network-bluetooth-activated" : "network-bluetooth-inactive")
                                          : conn.key === "vpn" ? "network-vpn" : (root.focusMode ? "notifications-disabled" : "notifications")
                                    tint: conn.active ? panel.tk.accent : panel.tk.text
                                }
                                Rectangle {
                                    visible: conn.key === "notifications" && root.unread > 0
                                    x: parent.width - 6; y: -6
                                    width: Math.max(16, badge.implicitWidth + 8); height: 16; radius: 8
                                    color: panel.tk.accent
                                    Text { id: badge; anchors.centerIn: parent; text: root.unread > 99 ? "99+" : root.unread; color: panel.tk.background; font.pixelSize: 10; font.bold: true }
                                }
                            }
                            Label {
                                id: connTitle
                                Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter
                                font.pixelSize: Kirigami.Theme.smallFont.pixelSize
                                text: conn.key === "wifi" ? (root.net.kind === "wifi" ? root.net.name : root.net.kind === "ethernet" ? i18n("Wired") : root.wifiAvailable && !root.wifiEnabled ? i18n("Wi-Fi off") : i18n("Offline"))
                                    : conn.key === "bt" ? i18n("Bluetooth") : conn.key === "vpn" ? i18n("VPN") : i18n("Alerts")
                                color: conn.active ? panel.tk.accent : panel.tk.text
                            }
                            Muted {
                                id: connSub
                                Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter
                                font.pixelSize: Kirigami.Theme.smallFont.pixelSize * 0.92
                                text: conn.key === "wifi" ? (root.online ? i18n("Connected") : i18n("Not connected"))
                                    : conn.key === "bt" ? (!root.btOn ? i18n("Off") : root.btConnected ? i18np("%1 device", "%1 devices", root.btConnected) : i18n("On"))
                                    : conn.key === "vpn" ? (root.net.vpn.length ? i18n("Active") : i18n("Off"))
                                    : root.focusMode ? i18n("Focus on") : root.unread ? i18np("%1 new", "%1 new", root.unread) : i18n("None")
                            }
                        }
                    }
                }
            }

            // C. battery (hidden without a battery)
            Tile {
                visible: root.hasBattery
                Layout.fillWidth: true
                implicitHeight: batt.implicitHeight + panel.pad * 1.5
                interactive: true
                onClicked: root.systemSettings("kcm_powerdevilprofilesconfig")
                Accessible.name: i18n("Battery %1 percent", root.batteryPercent)
                ColumnLayout {
                    id: batt
                    anchors { left: parent.left; right: parent.right; top: parent.top; margins: panel.pad * 0.75 }
                    spacing: Kirigami.Units.smallSpacing
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Kirigami.Units.largeSpacing
                        Glyph { source: root.batteryIcon(); tint: root.batteryState === "Charging" ? panel.tk.positive : root.batteryPercent <= 15 ? panel.tk.critical : panel.tk.text; implicitWidth: Kirigami.Units.iconSizes.medium }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 0
                            Label { text: root.batteryPercent + " %" + (root.batteryState === "Charging" ? "  ⚡" : ""); font.weight: Font.DemiBold; font.pixelSize: Kirigami.Theme.defaultFont.pixelSize * 1.3 }
                            Muted {
                                Layout.fillWidth: true
                                text: (root.batteryState === "Charging" ? i18n("Charging") : root.batteryState === "FullyCharged" ? i18n("Fully charged")
                                      : root.pluggedIn ? i18n("Plugged in, not charging") : i18n("On battery"))
                                      + (root.batteryRemainingMs > 0 ? " · " + i18n("%1 remaining", root.duration(root.batteryRemainingMs)) : "")
                            }
                        }
                        Muted { visible: root.batteryHealth > 0; text: i18n("Health %1 %", root.batteryHealth) }
                    }
                    Bar { fraction: root.batteryPercent / 100; tint: root.batteryPercent <= 15 ? panel.tk.critical : root.batteryState === "Charging" ? panel.tk.positive : panel.tk.accent }
                }
            }

            // D. system resources
            Label { text: i18n("System Resources"); font.weight: Font.DemiBold; Layout.topMargin: Kirigami.Units.smallSpacing }
            RowLayout {
                Layout.fillWidth: true
                spacing: Kirigami.Units.smallSpacing * 2
                Ring { label: i18n("CPU"); value: root.cpu; tint: root.levelColor(root.cpu); onClicked: root.openCenter("overview") }
                Ring { label: i18n("RAM"); value: root.memory; tint: root.cpu >= 0 ? root.levelColor(root.memory) : panel.tk.accent; onClicked: root.openCenter("overview") }
                Ring { visible: root.gpu >= 0; label: i18n("GPU"); value: root.gpu; tint: panel.tk.violet; onClicked: root.openCenter("overview") }
                Ring { label: i18n("Disk"); value: root.disk; tint: root.disk >= 85 ? root.levelColor(root.disk) : panel.tk.amber; onClicked: root.openCenter("storage") }
            }

            // E. health and alerts
            Section {
                id: health
                title: i18n("Health & Alerts")
                iconName: Qt.resolvedUrl("../icons/shield.svg")
                expandable: (root.status.alerts || []).length > 0
                summary: !root.status.loaded ? i18n("Checking…")
                       : root.status.error ? i18n("Unavailable")
                       : (root.status.alerts || []).length === 0 ? i18n("All clear")
                       : [root.alertCritical ? i18np("%1 critical", "%1 critical", root.alertCritical) : "",
                          root.alertWarning ? i18np("%1 warning", "%1 warnings", root.alertWarning) : ""].filter(s => s).join(" · ")
                summaryColor: root.alertCritical ? panel.tk.critical : root.alertWarning ? panel.tk.warning : panel.tk.positive
                RowLayout {
                    visible: !!(root.status.updates && root.status.updates.known)
                    Layout.fillWidth: true
                    spacing: Kirigami.Units.largeSpacing
                    Rectangle { width: 8; height: 8; radius: 4; color: root.status.updates && root.status.updates.security ? panel.tk.critical : panel.tk.positive }
                    Muted {
                        Layout.fillWidth: true
                        text: root.status.updates ? i18n("%1 security fixes · %2 other updates", root.status.updates.security, root.status.updates.regular) : ""
                    }
                    PlasmaComponents3.ToolButton {
                        visible: !!(root.status.updates && root.status.updates.total)
                        text: i18n("Update…")
                        onClicked: root.openCenter("packages")
                    }
                }
                Repeater {
                    model: health.open ? (root.status.alerts || []) : []
                    Tile {
                        required property var modelData
                        Layout.fillWidth: true
                        implicitHeight: alertRow.implicitHeight + Kirigami.Units.smallSpacing * 2
                        Accessible.name: modelData.title
                        onClicked: root.openCenter(modelData.page)
                        RowLayout {
                            id: alertRow
                            anchors { left: parent.left; right: parent.right; verticalCenter: parent.verticalCenter; margins: Kirigami.Units.smallSpacing * 2 }
                            Rectangle { width: 8; height: 8; radius: 4; color: modelData.severity === "critical" ? panel.tk.critical : panel.tk.warning }
                            ColumnLayout {
                                Layout.fillWidth: true
                                spacing: 0
                                Label { Layout.fillWidth: true; text: modelData.title; font.pixelSize: Kirigami.Theme.smallFont.pixelSize * 1.05 }
                                Muted { Layout.fillWidth: true; visible: text.length > 0; text: modelData.detail }
                            }
                            Glyph { source: "arrow-right"; tint: panel.tk.textSecondary; implicitWidth: Kirigami.Units.iconSizes.small }
                        }
                    }
                }
            }

            // F. storage
            Section {
                id: storage
                title: i18n("Storage")
                iconName: Qt.resolvedUrl("../icons/disk.svg")
                expandable: (root.status.mounts || []).length > 1
                readonly property var worst: (root.status.mounts || []).reduce((a, m) => !a || m.percent > a.percent ? m : a, null)
                summary: root.status.root ? root.status.root.mount + " " + Math.round(root.status.root.percent) + " %"
                         + (worst && worst.mount !== root.status.root.mount && worst.level !== "ok" ? "  ·  " + worst.mount + " " + Math.round(worst.percent) + " %" : "")
                       : root.disk >= 0 ? root.disk + " %" : "–"
                summaryColor: worst && worst.level === "critical" ? panel.tk.critical : worst && worst.level === "warning" ? panel.tk.warning : panel.tk.textSecondary
                Bar {
                    visible: !!root.status.root
                    fraction: root.status.root ? root.status.root.percent / 100 : 0
                    tint: root.status.root ? root.levelColor(root.status.root.percent) : panel.tk.accent
                }
                Muted { visible: !!root.status.root; text: root.status.root ? i18n("%1 free of %2", root.bytes(root.status.root.free), root.bytes(root.status.root.size)) : "" }
                Repeater {
                    model: storage.open ? (root.status.mounts || []).filter(m => m.mount !== "/") : []
                    ColumnLayout {
                        required property var modelData
                        Layout.fillWidth: true
                        spacing: 2
                        RowLayout {
                            Layout.fillWidth: true
                            Label { Layout.fillWidth: true; text: modelData.mount; font.pixelSize: Kirigami.Theme.smallFont.pixelSize }
                            Muted { text: Math.round(modelData.percent) + " % · " + root.bytes(modelData.free) + " " + i18n("free"); color: modelData.level === "ok" ? panel.tk.textSecondary : root.levelColor(modelData.percent) }
                        }
                        Bar { fraction: modelData.percent / 100; tint: root.levelColor(modelData.percent) }
                    }
                }
                PlasmaComponents3.ToolButton { visible: storage.open; text: i18n("Open Storage"); icon.name: "drive-harddisk"; onClicked: root.openCenter("storage") }
            }

            // G. services
            Section {
                title: i18n("Services")
                id: services
                iconName: Qt.resolvedUrl("../icons/services.svg")
                readonly property var s: root.status.services || ({})
                summary: root.status.loaded && !root.status.error
                         ? [i18n("%1 running", s.running || 0), (s.failed ? i18n("%1 failed", s.failed) : ""), (s.warnings ? i18np("%1 changing", "%1 changing", s.warnings) : "")].filter(x => x).join("  ·  ")
                         : "–"
                summaryColor: s.failed ? panel.tk.critical : s.warnings ? panel.tk.warning : panel.tk.textSecondary
                onClicked: root.openCenter("settings")
                Muted { visible: !!(services.s.failed_units && services.s.failed_units.length); Layout.fillWidth: true; wrapMode: Text.Wrap; text: (services.s.failed_units || []).join(", "); color: panel.tk.critical }
            }

            // H. quick controls
            RowLayout {
                Layout.fillWidth: true
                Layout.topMargin: Kirigami.Units.smallSpacing
                spacing: Kirigami.Units.smallSpacing * 2
                Quick { iconName: root.focusMode ? "notifications-disabled" : "notifications"; label: i18n("Focus"); on: root.focusMode; onClicked: root.setFocusMode(!root.focusMode) }
                Quick { iconName: "configure"; label: i18n("Settings"); onClicked: root.systemSettings("") }
                Quick { iconName: "system-lock-screen"; label: i18n("Lock"); onClicked: root.lockScreen() }
                Quick { iconName: "system-shutdown"; label: i18n("Power"); onClicked: root.powerMenu() }
            }
        }
    }
}
