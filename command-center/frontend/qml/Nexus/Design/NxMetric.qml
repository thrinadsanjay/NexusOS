import QtQuick
import QtQuick.Layouts

// One metric tile: label, value, optional detail and usage bar (0..1, -1 hides it).
NxCard {
    property string label
    property string value
    property string detail: ""
    property real fraction: -1
    property string status: ""
    implicitHeight: 96
    Layout.fillWidth: true
    Layout.preferredHeight: 96
    ColumnLayout {
        anchors.fill: parent
        spacing: 2
        Text { text: label; color: Theme.c.textSecondary; font.pixelSize: Theme.fontSmall; font.family: Theme.fontFamily }
        Text { text: value; color: status ? Theme.statusColor(status) : Theme.c.text; font.pixelSize: Theme.fontDisplay; font.family: Theme.fontFamily; font.weight: Font.DemiBold; elide: Text.ElideRight; Layout.fillWidth: true }
        Text { visible: detail.length; text: detail; color: Theme.c.textSecondary; font.pixelSize: Theme.fontSmall; font.family: Theme.fontFamily; elide: Text.ElideRight; Layout.fillWidth: true }
        NxProgress { visible: fraction >= 0; value: fraction; Layout.fillWidth: true }
    }
}
