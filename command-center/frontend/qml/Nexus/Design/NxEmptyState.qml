import QtQuick
import QtQuick.Layouts

ColumnLayout {
    property string title: "Nothing here yet"
    property string message: ""
    default property alias actions: row.data
    spacing: Theme.s2
    Text { text: parent.title; color: Theme.c.text; font.pixelSize: Theme.fontTitle; font.family: Theme.fontFamily; Layout.alignment: Qt.AlignHCenter }
    Text { visible: text.length; text: parent.message; color: Theme.c.textSecondary; font.pixelSize: Theme.fontBody; font.family: Theme.fontFamily; wrapMode: Text.WordWrap; horizontalAlignment: Text.AlignHCenter; Layout.maximumWidth: 480; Layout.alignment: Qt.AlignHCenter }
    Row { id: row; spacing: Theme.s2; Layout.alignment: Qt.AlignHCenter }
}
