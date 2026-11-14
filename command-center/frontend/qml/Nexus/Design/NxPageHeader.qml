import QtQuick
import QtQuick.Layouts

// Breadcrumb, title, subtitle and contextual actions (default property = action buttons).
Item {
    id: header
    property string title
    property string subtitle
    property var breadcrumb: []
    default property alias actions: actionRow.data
    implicitHeight: col.implicitHeight + Theme.s3
    // Long subtitles wrap; they must not widen the surrounding layout.
    implicitWidth: actionRow.implicitWidth + 240
    Layout.fillWidth: true
    ColumnLayout {
        id: col
        anchors.left: parent.left
        anchors.right: actionRow.left
        anchors.rightMargin: Theme.s3
        spacing: 2
        Text {
            visible: header.breadcrumb.length > 0
            text: header.breadcrumb.join("  ›  ")
            color: Theme.c.textSecondary
            font.pixelSize: Theme.fontSmall
            font.family: Theme.fontFamily
        }
        Text {
            text: header.title
            color: Theme.c.text
            font.pixelSize: Theme.fontDisplay
            font.family: Theme.fontFamily
            font.weight: Font.DemiBold
            Accessible.role: Accessible.Heading
        }
        Text {
            visible: header.subtitle.length > 0
            text: header.subtitle
            color: Theme.c.textSecondary
            font.pixelSize: Theme.fontBody
            font.family: Theme.fontFamily
            wrapMode: Text.WordWrap
            Layout.fillWidth: true
        }
    }
    Row {
        id: actionRow
        anchors.right: parent.right
        anchors.verticalCenter: col.verticalCenter
        spacing: Theme.s2
    }
}
