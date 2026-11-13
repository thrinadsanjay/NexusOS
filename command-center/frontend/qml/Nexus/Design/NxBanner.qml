import QtQuick
import QtQuick.Layouts

// Contextual notice: kind = info | warning | error | success.
Rectangle {
    property string kind: "info"
    property string text: ""
    readonly property color tone: kind === "warning" ? Theme.c.warning : kind === "error" ? Theme.c.negative : kind === "success" ? Theme.c.positive : Theme.c.accent
    visible: text.length > 0
    radius: Theme.radiusSmall
    color: Qt.rgba(tone.r, tone.g, tone.b, 0.10)
    border.width: 1
    border.color: Qt.rgba(tone.r, tone.g, tone.b, 0.6)
    implicitHeight: label.implicitHeight + Theme.s2 * 2
    Layout.fillWidth: true
    Text {
        id: label
        anchors.fill: parent
        anchors.margins: Theme.s2
        text: parent.text
        wrapMode: Text.WordWrap
        color: Theme.c.text
        font.pixelSize: Theme.fontBody
        font.family: Theme.fontFamily
    }
}
