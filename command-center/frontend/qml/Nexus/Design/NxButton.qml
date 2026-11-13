import QtQuick
import QtQuick.Controls.Basic as B

// Buttons: "primary" (one per view), "secondary", "danger", "ghost".
B.Button {
    id: control
    property string variant: "secondary"
    implicitHeight: Theme.controlHeight
    leftPadding: Theme.s3
    rightPadding: Theme.s3
    font.family: Theme.fontFamily
    font.pixelSize: Theme.fontBody
    font.weight: variant === "primary" ? Font.DemiBold : Font.Normal
    Accessible.name: text
    contentItem: Text {
        text: control.text
        font: control.font
        color: !control.enabled ? Theme.c.textSecondary
             : control.variant === "primary" ? Theme.c.textOnAccent
             : control.variant === "danger" ? Theme.c.negative
             : control.variant === "ghost" ? Theme.c.accent : Theme.c.text
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
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
