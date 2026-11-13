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
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.s5
        spacing: Theme.s3
        NxPageHeader { title: "Security"; subtitle: "The Command Center runs as you. Privileged work goes through polkit-authorized helpers and is audited."
            NxButton { text: "Refresh"; onClicked: controller.refresh() } }
        NxErrorState { message: controller ? controller.error : ""; onRetry: controller.refresh() }
        Repeater {
            model: d.checks || []
            NxCard {
                required property var modelData
                Layout.fillWidth: true
                implicitHeight: 64
                RowLayout {
                    anchors.fill: parent
                    NxStatusBadge { status: modelData.status; label: modelData.status; Layout.preferredWidth: 90 }
                    Text { text: modelData.title; color: Theme.c.text; font.family: Theme.fontFamily; font.weight: Font.DemiBold; Layout.preferredWidth: 240 }
                    Text { text: modelData.detail; color: Theme.c.textSecondary; font.family: Theme.fontFamily; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                }
            }
        }
        NxSectionTitle { text: "Listening ports" }
        NxTable {
            Layout.fillWidth: true; Layout.fillHeight: true
            rows: d.ports || []
            columns: [{ title: "Protocol", role: "proto", width: 0.15 }, { title: "Address", role: "address", width: 0.4, mono: true }, { title: "Port", role: "port", width: 0.15 }, { title: "Exposure", width: 0.3, format: r => r.exposed ? "network" : "local only" }]
        }
        Text { text: "Privileged operations are audited by the agent in /var/log/nexusos/agent-audit.log (readable by administrators)."; color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall }
    }
}
