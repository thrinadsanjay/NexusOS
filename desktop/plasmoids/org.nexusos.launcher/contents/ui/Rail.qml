/*
 * Minimized launcher: one icon per shortcut, the name on hover, a running dot, keyboard
 * navigation (Tab / arrow keys, Enter to start).
 */
import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.core as PlasmaCore
import org.kde.kirigami as Kirigami

Item {
    id: rail
    readonly property int cell: Kirigami.Units.gridUnit * 2.6
    readonly property color accent: "#31C6BD"
    readonly property color text: "#E8F1F2"
    Layout.preferredWidth: cell
    Layout.minimumHeight: column.implicitHeight
    Layout.preferredHeight: column.implicitHeight
    Layout.maximumHeight: column.implicitHeight

    ColumnLayout {
        id: column
        width: parent.width
        spacing: Kirigami.Units.smallSpacing

        Repeater {
            model: root.visibleItems
            PlasmaCore.ToolTipArea {
                id: entry
                required property string modelData
                required property int index
                readonly property var e: root.catalogue[modelData]
                readonly property var state: root.runningOf(modelData)
                Layout.fillWidth: true
                implicitHeight: rail.cell
                mainText: e.title
                subText: e.description
                location: Plasmoid.location
                activeFocusOnTab: true
                Accessible.role: Accessible.Button
                Accessible.name: e.title
                Keys.onPressed: event => {
                    if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) { root.activate(modelData); event.accepted = true }
                    else if (event.key === Qt.Key_Down) { nextItemInFocusChain(true).forceActiveFocus(); event.accepted = true }
                    else if (event.key === Qt.Key_Up) { nextItemInFocusChain(false).forceActiveFocus(); event.accepted = true }
                }

                Rectangle {   // hover / focus / active background
                    anchors.centerIn: parent
                    width: rail.cell - Kirigami.Units.smallSpacing * 2
                    height: width
                    radius: 10
                    color: mouse.containsMouse || entry.activeFocus ? Qt.rgba(49 / 255, 198 / 255, 189 / 255, 0.16)
                         : entry.state && entry.state.active ? Qt.rgba(49 / 255, 198 / 255, 189 / 255, 0.1) : "transparent"
                    border.color: mouse.containsMouse || entry.activeFocus ? Qt.rgba(49 / 255, 198 / 255, 189 / 255, 0.65) : "transparent"
                    border.width: 1
                    Behavior on color { ColorAnimation { duration: Kirigami.Units.shortDuration } }
                }
                Kirigami.Icon {
                    anchors.centerIn: parent
                    width: entry.e.logo ? Kirigami.Units.iconSizes.medium : Kirigami.Units.iconSizes.smallMedium
                    height: width
                    source: root.iconSource(entry.modelData)
                    isMask: !entry.e.logo
                    color: mouse.containsMouse || entry.activeFocus ? rail.accent : rail.text
                }
                Rectangle {   // running indicator (left edge, like a dock dot)
                    visible: !!entry.state
                    width: 3; height: entry.state && entry.state.active ? 18 : 8; radius: 1.5
                    anchors { left: parent.left; leftMargin: 1; verticalCenter: parent.verticalCenter }
                    color: rail.accent
                    Behavior on height { NumberAnimation { duration: Kirigami.Units.shortDuration } }
                }
                MouseArea {
                    id: mouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    acceptedButtons: Qt.LeftButton | Qt.MiddleButton
                    onClicked: mouse => mouse.button === Qt.MiddleButton ? root.launch(entry.modelData) : root.activate(entry.modelData)
                }
            }
        }
    }
}
