/*
 * Expanded launcher: every available shortcut with its name, description and running state.
 * Opens from the "more" entry; closes on Escape, a click outside, or after starting something.
 */
import QtQuick
import QtQuick.Layouts
import org.kde.plasma.plasmoid
import org.kde.plasma.components as PlasmaComponents3
import org.kde.kirigami as Kirigami

Item {
    id: view
    Layout.preferredWidth: Kirigami.Units.gridUnit * 18
    Layout.preferredHeight: list.contentHeight + header.implicitHeight + Kirigami.Units.largeSpacing * 3
    Keys.onEscapePressed: root.expanded = false

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Kirigami.Units.largeSpacing
        spacing: Kirigami.Units.largeSpacing
        RowLayout {
            id: header
            Layout.fillWidth: true
            Kirigami.Heading { level: 4; text: i18n("Applications"); Layout.fillWidth: true }
            PlasmaComponents3.ToolButton {
                icon.name: "configure"
                text: i18n("Edit…")
                onClicked: Plasmoid.internalAction("configure").trigger()
            }
        }
        ListView {
            id: list
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            focus: true
            keyNavigationEnabled: true
            model: root.allIds.filter(id => id !== "more" && root.isAvailable(id))
            delegate: PlasmaComponents3.ItemDelegate {
                required property string modelData
                readonly property var e: root.catalogue[modelData]
                width: ListView.view.width
                highlighted: ListView.isCurrentItem
                onClicked: root.activate(modelData)
                Keys.onReturnPressed: root.activate(modelData)
                contentItem: RowLayout {
                    spacing: Kirigami.Units.largeSpacing
                    Kirigami.Icon {
                        source: root.iconSource(parent.parent.modelData)
                        isMask: !parent.parent.e.logo
                        color: "#E8F1F2"
                        implicitWidth: Kirigami.Units.iconSizes.smallMedium; implicitHeight: implicitWidth
                    }
                    ColumnLayout {
                        spacing: 0
                        Layout.fillWidth: true
                        PlasmaComponents3.Label { text: parent.parent.parent.e.title; Layout.fillWidth: true; elide: Text.ElideRight }
                        PlasmaComponents3.Label { text: parent.parent.parent.e.description; opacity: 0.7; font: Kirigami.Theme.smallFont; Layout.fillWidth: true; elide: Text.ElideRight }
                    }
                    PlasmaComponents3.Label { visible: !!root.runningOf(parent.parent.modelData); text: i18n("running"); color: "#31C6BD"; font: Kirigami.Theme.smallFont }
                }
            }
        }
        PlasmaComponents3.Label {
            Layout.fillWidth: true
            wrapMode: Text.Wrap
            opacity: 0.7
            font: Kirigami.Theme.smallFont
            text: i18n("Containers, virtual machines, cloud and AI appear here once Docker or Podman, Virtual Machine Manager, the Nexus applications or Ollama are installed.")
        }
    }
}
