import QtQuick
import QtQuick.Controls.Basic as B

Row {
    property string text: "Loading…"
    property bool running: true
    visible: running
    spacing: Theme.s2
    B.BusyIndicator { running: parent.running; width: 20; height: 20 }
    Text { text: parent.text; color: Theme.c.textSecondary; font.pixelSize: Theme.fontBody; font.family: Theme.fontFamily; anchors.verticalCenter: parent.verticalCenter }
}
