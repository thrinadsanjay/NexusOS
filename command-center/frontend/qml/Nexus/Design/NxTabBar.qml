import QtQuick
import QtQuick.Controls.Basic as B

B.TabBar {
    id: bar
    property var tabs: []
    background: Rectangle { color: "transparent"; Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.c.border } }
    Repeater {
        model: bar.tabs
        B.TabButton {
            required property string modelData
            text: modelData
            width: implicitWidth
            font.pixelSize: Theme.fontBody
            font.family: Theme.fontFamily
            contentItem: Text { text: parent.text; font: parent.font; color: parent.checked ? Theme.c.text : Theme.c.textSecondary; horizontalAlignment: Text.AlignHCenter }
            background: Rectangle { color: "transparent"; Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 2; color: parent.parent.checked ? Theme.c.accent : "transparent" } }
        }
    }
}
