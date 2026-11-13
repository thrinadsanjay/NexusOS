import QtQuick
import QtQuick.Controls.Basic as B

B.TextField {
    id: field
    property bool invalid: false
    implicitHeight: Theme.controlHeight
    font.family: Theme.fontFamily
    font.pixelSize: Theme.fontBody
    color: Theme.c.text
    placeholderTextColor: Theme.c.textSecondary
    selectionColor: Theme.c.accent
    selectedTextColor: Theme.c.textOnAccent
    leftPadding: Theme.s2
    Accessible.name: placeholderText
    background: Rectangle {
        radius: Theme.radiusSmall
        color: Theme.c.background
        border.width: 1
        border.color: field.invalid ? Theme.c.negative : field.activeFocus ? Theme.c.accent : Theme.c.border
    }
}
