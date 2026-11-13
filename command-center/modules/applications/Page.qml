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
    readonly property var app: d.selected || null
    readonly property var st: d.state || null
    Component.onCompleted: if (intent.startsWith("app:")) controller.select(intent.slice(4))

    RowLayout {
        anchors.fill: parent
        anchors.margins: Theme.s5
        spacing: Theme.s4
        ColumnLayout {
            Layout.preferredWidth: 380
            Layout.fillHeight: true
            NxPageHeader { title: "Nexus Applications"; subtitle: "Optional, independently deployed apps. Nothing is installed automatically." }
            NxErrorState { message: controller ? controller.error : ""; onRetry: controller.refresh() }
            ListView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: Theme.s2
                clip: true
                model: d.apps || []
                delegate: NxCard {
                    required property var modelData
                    width: ListView.view.width
                    implicitHeight: 92
                    color: page.app && page.app.id === modelData.app.id ? Theme.c.backgroundSecondary : Theme.c.surface
                    TapHandler { onTapped: controller.select(modelData.app.id) }
                    ColumnLayout {
                        anchors.fill: parent
                        RowLayout {
                            Text { text: modelData.app.name; color: Theme.c.text; font.pixelSize: Theme.fontTitle; font.family: Theme.fontFamily; Layout.fillWidth: true; elide: Text.ElideRight }
                            NxStatusBadge { status: modelData.state.installed ? modelData.state.status : modelData.app.status; label: modelData.state.installed ? modelData.state.status : modelData.app.status }
                        }
                        Text { text: modelData.app.summary; color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall; wrapMode: Text.WordWrap; Layout.fillWidth: true; maximumLineCount: 2; elide: Text.ElideRight }
                    }
                }
            }
        }
        NxCard {
            Layout.fillWidth: true
            Layout.fillHeight: true
            NxEmptyState { anchors.centerIn: parent; visible: !page.app; title: "Select an application"; message: "Application code lives in its own repository. NexusOS keeps the registry, pinned versions, deployment definitions and health checks." }
            ScrollView {
                anchors.fill: parent
                visible: !!page.app
                contentWidth: availableWidth
                ColumnLayout {
                    width: parent.width
                    spacing: Theme.s2
                    RowLayout {
                        Text { text: page.app ? page.app.name : ""; color: Theme.c.text; font.pixelSize: Theme.fontDisplay; font.family: Theme.fontFamily; font.weight: Font.DemiBold; Layout.fillWidth: true }
                        NxStatusBadge { status: page.app ? page.app.status : ""; label: page.app ? page.app.status + "  ·  " + page.app.version : "" }
                    }
                    Text { text: page.app ? page.app.description || page.app.summary : ""; wrapMode: Text.WordWrap; color: Theme.c.text; font.family: Theme.fontFamily; Layout.fillWidth: true }
                    NxBanner { kind: page.app && page.app.status === "unavailable" ? "error" : "warning"; text: page.app && page.app.status !== "available" ? page.app.status_reason : "" }
                    NxBanner { kind: "warning"; text: (d.deps || []).length ? "Cannot install yet:\n• " + d.deps.join("\n• ") : "" }
                    RowLayout {
                        visible: !!(page.app && page.app.status !== "unavailable")
                        NxButton { text: "Install"; variant: "primary"; visible: !!(!(page.st && page.st.installed)); enabled: !!((d.deps || []).length === 0 && !controller.busy)
                            onClicked: confirm.ask("Install " + page.app.name, "NexusOS will fetch the pinned version, generate secrets into a private .env file (mode 600), publish ports on 127.0.0.1 only and start the Compose project.",
                                ["project: " + page.app.deployment.project, page.app.deployment.source_repo ? "source: " + page.app.deployment.source_repo + " @ " + page.app.deployment.source_ref.slice(0, 12) : "images only", "ports: " + page.app.ports.map(p => "127.0.0.1:" + p.host_port).join(", "), "memory: " + (page.app.resources.memory || "unknown")], "Install", false, () => controller.install(page.app.id)) }
                        NxButton { text: "Start"; visible: !!(page.st && page.st.installed); onClicked: controller.action(page.app.id, "start") }
                        NxButton { text: "Stop"; visible: !!(page.st && page.st.installed); onClicked: controller.action(page.app.id, "stop") }
                        NxButton { text: "Restart"; visible: !!(page.st && page.st.installed); onClicked: controller.action(page.app.id, "restart") }
                        NxButton { text: "Update"; visible: !!(page.st && page.st.installed); onClicked: confirm.ask("Update " + page.app.name, "Re-deploy at the version pinned in the registry (" + page.app.version + ").", [], "Update", false, () => controller.update(page.app.id)) }
                        NxButton { text: "Logs"; visible: !!(page.st && page.st.installed); onClicked: controller.logs(page.app.id) }
                        NxButton { text: "Back up"; visible: !!(page.st && page.st.installed); onClicked: controller.backup(page.app.id) }
                        NxButton { text: "Uninstall"; variant: "danger"; visible: !!(page.st && page.st.installed); onClicked: confirm.ask("Uninstall " + page.app.name, "Stop and remove the containers. Data volumes and configuration are kept (delete them with: nexus apps uninstall " + page.app.id + " --delete-data).", [], "Uninstall", true, token => controller.uninstall(page.app.id, false)) }
                    }
                    RowLayout {
                        visible: !!(page.st && page.st.installed)
                        Text { text: page.st ? "Health: " + (page.st.health || "n/a") : ""; color: Theme.c.text; font.family: Theme.fontFamily }
                        Repeater { model: page.st ? page.st.urls : []; Text { required property string modelData; text: "<a href='" + modelData + "'>" + modelData + "</a>"; onLinkActivated: link => Qt.openUrlExternally(link); color: Theme.c.accent; font.family: Theme.fontFamily } }
                        NxButton { text: "Propose gateway route"; visible: !!(page.app && !!page.app.gateway); onClicked: controller.proposeRoute(page.app.id) }
                    }
                    NxTable {
                        visible: !!(page.st && page.st.installed)
                        Layout.fillWidth: true
                        Layout.preferredHeight: 140
                        rows: page.st ? page.st.services : []
                        columns: [{ title: "Service", role: "name", width: 0.4 }, { title: "State", role: "state", width: 0.3 }, { title: "Health", role: "health", width: 0.3 }]
                    }
                    NxSectionTitle { text: "Integration contract" }
                    NxFormRow { label: "Authentication"; Text { text: page.app ? page.app.contract.authentication : ""; color: Theme.c.text; font.family: Theme.fontFamily } }
                    NxFormRow { label: "UI integration"; Text { text: page.app ? (page.app.contract.embed === "window" ? "separate window (browser fallback)" : page.app.contract.embed) : ""; color: Theme.c.text; font.family: Theme.fontFamily } }
                    NxFormRow { label: "Capabilities"; Text { text: page.app ? page.app.contract.capabilities.join(", ") : ""; wrapMode: Text.WordWrap; color: Theme.c.text; font.family: Theme.fontFamily; width: 400 } }
                    NxFormRow { label: "Gateway"; Text { text: page.app && page.app.gateway ? page.app.gateway.suggested_hostname + " → 127.0.0.1:" + page.app.gateway.backend_port : "—"; color: Theme.c.text; font.family: Theme.fontFamily } }
                    NxFormRow { label: "Source"; Text { text: page.app && page.app.homepage ? "<a href='" + page.app.homepage + "'>" + page.app.homepage + "</a>" : "—"; onLinkActivated: link => Qt.openUrlExternally(link); color: Theme.c.accent; font.family: Theme.fontFamily } }
                    Repeater { model: page.app ? page.app.dependencies.notes : []; Text { required property string modelData; text: "• " + modelData; color: Theme.c.textSecondary; wrapMode: Text.WordWrap; Layout.fillWidth: true; font.family: Theme.fontFamily } }
                    NxLogView { visible: !!((d.logs || "").length > 0); text: d.logs || ""; Layout.fillWidth: true; Layout.preferredHeight: 220 }
                }
            }
        }
    }
}
