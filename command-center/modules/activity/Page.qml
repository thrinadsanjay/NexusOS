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
        NxPageHeader { title: "Activity History"; subtitle: "Operations started from the Command Center and the nexus CLI (last 5,000 kept; secrets redacted)." }
        NxTextField { Layout.fillWidth: true; placeholderText: "Filter by action, target or outcome"; onTextChanged: controller.filter(text) }
        NxTable {
            Layout.fillWidth: true; Layout.fillHeight: true
            rows: d.items || []
            emptyText: "No activity recorded yet"
            columns: [{ title: "Time", width: 0.18, format: r => new Date(r.ts * 1000).toLocaleString(Qt.locale(), Locale.ShortFormat) }, { title: "User", role: "actor", width: 0.1 }, { title: "Action", role: "action", width: 0.2, mono: true }, { title: "Target", role: "target", width: 0.27 }, { title: "Outcome", role: "outcome", width: 0.1 }, { title: "Detail", role: "detail", width: 0.15 }]
        }
    }
}
