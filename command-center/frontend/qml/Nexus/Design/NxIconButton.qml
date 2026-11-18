import QtQuick
import QtQuick.Controls.Basic as B

// Square icon-only button with a tooltip and an optional count badge (header bell, toolbars).
B.AbstractButton {
    id: control
    property string iconName: "info"
    property string tip: ""
    property int badge: 0
    property bool active: false
    property int iconSize: 18
    implicitWidth: Theme.controlHeight
    implicitHeight: Theme.controlHeight
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    Accessible.name: tip
    B.ToolTip.visible: hovered && tip.length > 0
    B.ToolTip.delay: 500
    B.ToolTip.text: tip
    background: Rectangle {
        radius: Theme.radiusSmall
        color: control.active ? Theme.c.backgroundSecondary : control.down ? Theme.c.backgroundSecondary : control.hovered ? Theme.c.surfaceElevated : "transparent"
        border.width: control.visualFocus ? 1 : 0
        border.color: Theme.c.accent
        opacity: control.enabled ? 1 : 0.5
    }
    contentItem: Item {
        NxIcon { anchors.centerIn: parent; name: control.iconName; size: control.iconSize; color: control.active || control.hovered ? Theme.c.text : Theme.c.textSecondary }
    }
    Rectangle {
        visible: control.badge > 0
        x: parent.width - width + 2; y: -2
        height: 16; width: Math.max(16, count.implicitWidth + 8); radius: 8
        color: Theme.c.accentSecondary
        Text { id: count; anchors.centerIn: parent; text: control.badge > 99 ? "99+" : control.badge; color: Theme.c.textOnAccent; font.pixelSize: 10; font.weight: Font.Bold; font.family: Theme.fontFamily }
    }
}
