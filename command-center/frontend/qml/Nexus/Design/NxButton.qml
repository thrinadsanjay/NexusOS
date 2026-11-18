import QtQuick
import QtQuick.Controls.Basic as B

// Buttons: "primary" (one per view), "secondary", "danger", "ghost".
// admin: true marks an administrative action (runs through the user's sudo rights); it is
// hidden for users without administrator access (App.access.admin === "none").
B.Button {
    id: control
    property string variant: "secondary"
    property bool admin: false
    property string iconName: ""  // optional NxIcon shown before the text
    visible: !admin || typeof App === "undefined" || App.canAdmin
    implicitHeight: Theme.controlHeight
    leftPadding: Theme.s3
    rightPadding: Theme.s3
    font.family: Theme.fontFamily
    font.pixelSize: Theme.fontBody
    font.weight: variant === "primary" ? Font.DemiBold : Font.Normal
    Accessible.name: text
    readonly property color fg: !control.enabled ? Theme.c.textSecondary
             : control.variant === "primary" ? Theme.c.textOnAccent
             : control.variant === "danger" ? Theme.c.negative
             : control.variant === "ghost" ? Theme.c.accent : Theme.c.text
    contentItem: Item {
        implicitWidth: (control.iconName.length > 0 ? 21 : 0) + label.implicitWidth
        implicitHeight: label.implicitHeight
        Row {
            id: row
            anchors.centerIn: parent
            spacing: 6
            NxIcon { visible: control.iconName.length > 0; name: control.iconName; size: 15; color: control.fg; anchors.verticalCenter: parent.verticalCenter }
            Text {
                id: label
                width: Math.min(implicitWidth, Math.max(0, control.availableWidth - (control.iconName.length > 0 ? 21 : 0)))
                text: control.text
                visible: text.length > 0
                font: control.font
                color: control.fg
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
                anchors.verticalCenter: parent.verticalCenter
            }
        }
    }
    background: Rectangle {
        radius: Theme.radiusSmall
        opacity: control.enabled ? 1 : 0.5
        color: control.variant === "primary" ? (control.down ? Qt.darker(Theme.c.accent, 1.15) : control.hovered ? Qt.lighter(Theme.c.accent, 1.08) : Theme.c.accent)
             : control.variant === "ghost" ? (control.hovered ? Theme.c.surfaceElevated : "transparent")
             : (control.down ? Theme.c.backgroundSecondary : control.hovered ? Theme.c.surfaceElevated : Theme.c.surface)
        border.width: control.variant === "primary" || control.variant === "ghost" ? 0 : 1
        border.color: control.variant === "danger" ? Theme.c.negative : (control.visualFocus ? Theme.c.accent : Theme.c.border)
    }
}
