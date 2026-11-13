import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Nexus.Design

Item {
    id: page
    property var controller
    property var confirm
    property string intent: ""
    readonly property var d: controller ? controller.data : ({})
    RowLayout {
        anchors.fill: parent
        anchors.margins: Theme.s5
        spacing: Theme.s4
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            NxPageHeader { title: "Notifications"; subtitle: "Repeated events are grouped (count) instead of flooding the list."
                NxButton { text: "Dismiss all"; onClicked: controller.dismiss(-1) } }
            CheckBox { text: "Show dismissed"; onToggled: controller.showAll(checked) }
            ListView {
                Layout.fillWidth: true; Layout.fillHeight: true
                spacing: Theme.s2
                clip: true
                model: d.items || []
                delegate: NxCard {
                    required property var modelData
                    width: ListView.view.width
                    implicitHeight: 76
                    RowLayout {
                        anchors.fill: parent
                        NxStatusBadge { status: modelData.severity === "success" ? "ok" : modelData.severity; label: modelData.severity; Layout.preferredWidth: 80 }
                        ColumnLayout {
                            Layout.fillWidth: true
                            Text { text: modelData.title + (modelData.count > 1 ? "  ×" + modelData.count : ""); color: Theme.c.text; font.family: Theme.fontFamily; font.weight: Font.DemiBold; elide: Text.ElideRight; Layout.fillWidth: true }
                            Text { text: modelData.body; color: Theme.c.textSecondary; font.family: Theme.fontFamily; elide: Text.ElideRight; Layout.fillWidth: true }
                            Text { text: new Date(modelData.ts * 1000).toLocaleString(Qt.locale(), Locale.ShortFormat) + "  ·  " + modelData.category + "  ·  " + modelData.source; color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall }
                        }
                        NxButton { text: "Dismiss"; variant: "ghost"; visible: !modelData.dismissed; onClicked: controller.dismiss(modelData.id) }
                    }
                }
                NxEmptyState { anchors.centerIn: parent; visible: parent.count === 0; title: "All clear"; message: "Updates, failures, certificate expiry and disk alerts appear here." }
            }
        }
        NxCard {
            Layout.preferredWidth: 260
            Layout.alignment: Qt.AlignTop
            ColumnLayout {
                width: parent.width
                NxSectionTitle { text: "Show notifications for" }
                Repeater { model: d.prefs || []; CheckBox { required property var modelData; text: modelData.category; checked: modelData.enabled; onToggled: controller.setPreference(modelData.category, checked) } }
            }
        }
    }
}
