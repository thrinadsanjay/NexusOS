import QtQuick
import QtQuick.Layouts

// Label + field row for forms. Put the input as the child.
RowLayout {
    property string label
    default property alias field: holder.data
    spacing: Theme.s3
    Layout.fillWidth: true
    Text { text: label; color: Theme.c.textSecondary; font.pixelSize: Theme.fontBody; font.family: Theme.fontFamily; Layout.preferredWidth: 160; horizontalAlignment: Text.AlignRight }
    Item { id: holder; Layout.fillWidth: true; implicitHeight: childrenRect.height; Layout.preferredHeight: childrenRect.height }
}
