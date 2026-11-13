import QtQuick
import QtQuick.Layouts

// Inline error with optional retry. Shows the backend message and hint verbatim.
Rectangle {
    property string message: ""
    signal retry()
    visible: message.length > 0
    color: Qt.rgba(Theme.c.negative.r, Theme.c.negative.g, Theme.c.negative.b, 0.12)
    border.color: Theme.c.negative
    border.width: 1
    radius: Theme.radiusSmall
    implicitHeight: layout.implicitHeight + Theme.s3 * 2
    Layout.fillWidth: true
    RowLayout {
        id: layout
        anchors.fill: parent
        anchors.margins: Theme.s3
        Text { text: message; color: Theme.c.text; wrapMode: Text.WordWrap; font.pixelSize: Theme.fontBody; font.family: Theme.fontFamily; Layout.fillWidth: true }
        NxButton { text: "Retry"; variant: "ghost"; onClicked: retry() }
    }
}
