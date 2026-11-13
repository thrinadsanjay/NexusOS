import QtQuick
import QtQuick.Controls.Basic as B

// Monospace, selectable, bounded log/output view.
Rectangle {
    id: logRoot
    property string text: ""
    color: Theme.c.background
    radius: Theme.radiusSmall
    border.color: Theme.c.border
    B.ScrollView {
        anchors.fill: parent
        anchors.margins: Theme.s2
        B.TextArea {
            text: logRoot.text
            readOnly: true
            selectByMouse: true
            wrapMode: Text.NoWrap
            color: Theme.c.text
            font.family: Theme.monoFamily
            font.pixelSize: Theme.fontSmall
            background: null
        }
    }
}
