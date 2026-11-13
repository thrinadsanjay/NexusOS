import QtQuick
import QtQuick.Controls.Basic as B

// Lightweight table: columns = [{title, role, width (fraction), format(row) optional}].
// Rows are plain JS objects; delegates are recycled by ListView.
Rectangle {
    id: table
    property var columns: []
    property var rows: []
    property int currentIndex: -1
    property var currentRow: currentIndex >= 0 && currentIndex < rows.length ? rows[currentIndex] : null
    property string emptyText: "Nothing to show"
    signal activated(var row)
    color: Theme.c.surface
    radius: Theme.radius
    border.width: 1
    border.color: Theme.c.border
    clip: true

    function cell(row, col) {
        if (col.format) return col.format(row)
        const v = row[col.role]
        return v === undefined || v === null ? "" : String(v)
    }

    Rectangle {
        id: head
        width: parent.width; height: 30
        color: Theme.c.surfaceElevated
        radius: Theme.radius
        Row {
            anchors.fill: parent
            anchors.leftMargin: Theme.s3
            Repeater {
                model: table.columns
                Text {
                    width: (table.width - Theme.s3 * 2) * (modelData.width || 1 / table.columns.length)
                    height: 30
                    verticalAlignment: Text.AlignVCenter
                    text: modelData.title
                    color: Theme.c.textSecondary
                    font.pixelSize: Theme.fontSmall
                    font.family: Theme.fontFamily
                    font.weight: Font.DemiBold
                    elide: Text.ElideRight
                }
            }
        }
    }
    ListView {
        id: list
        anchors.top: head.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        model: table.rows
        clip: true
        currentIndex: table.currentIndex
        reuseItems: true
        B.ScrollBar.vertical: B.ScrollBar {}
        delegate: Rectangle {
            required property var modelData
            required property int index
            width: list.width
            height: 30
            color: index === table.currentIndex ? Theme.c.backgroundSecondary : (hover.hovered ? Theme.c.surfaceElevated : "transparent")
            HoverHandler { id: hover }
            TapHandler {
                onTapped: table.currentIndex = index
                onDoubleTapped: table.activated(modelData)
            }
            Row {
                anchors.fill: parent
                anchors.leftMargin: Theme.s3
                Repeater {
                    model: table.columns
                    Text {
                        required property var modelData
                        width: (table.width - Theme.s3 * 2) * (modelData.width || 1 / table.columns.length)
                        height: 30
                        verticalAlignment: Text.AlignVCenter
                        text: table.cell(parent.parent.modelData, modelData)
                        color: Theme.c.text
                        font.pixelSize: Theme.fontBody
                        font.family: modelData.mono ? Theme.monoFamily : Theme.fontFamily
                        elide: Text.ElideRight
                    }
                }
            }
        }
    }
    Text {
        anchors.centerIn: list
        visible: table.rows.length === 0
        text: table.emptyText
        color: Theme.c.textSecondary
        font.pixelSize: Theme.fontBody
        font.family: Theme.fontFamily
    }
}
