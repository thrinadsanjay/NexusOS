import QtQuick

// Flat surface panel. Use sparingly: group related content, not every value.
Rectangle {
    default property alias content: inner.data
    property int padding: Theme.s4
    color: Theme.c.surface
    radius: Theme.radius
    border.width: 1
    border.color: Theme.c.border
    // implicit size comes from the first child's implicit height (no childrenRect binding loops)
    implicitHeight: (inner.children.length ? inner.children[0].implicitHeight : 0) + 2 * padding
    Item {
        id: inner
        anchors.fill: parent
        anchors.margins: parent.padding
    }
}
