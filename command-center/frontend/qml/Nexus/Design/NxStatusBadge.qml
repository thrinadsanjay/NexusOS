import QtQuick

// Status indicator: dot + label. Colour is never the only signal (label text always shown).
Row {
    property string status: "unknown"
    property string label: status
    spacing: Theme.s1 + 2
    Rectangle {
        width: 8; height: 8; radius: 4
        anchors.verticalCenter: parent.verticalCenter
        color: Theme.statusColor(parent.status)
    }
    Text {
        text: parent.label
        color: Theme.c.text
        font.pixelSize: Theme.fontSmall
        font.family: Theme.fontFamily
    }
}
