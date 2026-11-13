import QtQuick

Rectangle {
    property real value: 0  // 0..1
    implicitHeight: 4
    radius: 2
    color: Theme.c.border
    Rectangle {
        width: parent.width * Math.max(0, Math.min(1, parent.value))
        height: parent.height
        radius: 2
        color: parent.value > 0.9 ? Theme.c.negative : parent.value > 0.8 ? Theme.c.warning : Theme.c.accent
    }
}
