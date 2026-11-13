import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Dialogs
import QtQuick.Layouts
import Nexus.Design

Item {
    id: page
    property var controller
    property var confirm
    property string intent: ""
    readonly property var d: controller ? controller.data : ({})
    readonly property var sel: containerTable.currentRow

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.s5
        spacing: Theme.s3
        NxPageHeader {
            title: "Containers"
            subtitle: d.status && d.status.reachable ? "Docker Engine " + d.status.server_version + "  ·  local socket only" : "Docker Engine"
            NxButton { text: "Refresh"; onClicked: controller.refresh() }
        }
        NxBanner { kind: "info"; text: d.note || "" }
        NxEmptyState {
            visible: d.available === false
            Layout.alignment: Qt.AlignCenter
            title: "Docker Engine is not available"
            message: (d.status ? (d.status.error || "") + "\n" + (d.status.hint || "") : "") + "\nDocker is part of the Development Workstation and Private Cloud Host profiles. The Command Center works without it."
        }
        NxErrorState { message: controller ? controller.error : ""; onRetry: controller.refresh() }
        NxTabBar { id: tabs; visible: d.available === true; Layout.fillWidth: true; tabs: ["Containers", "Images", "Volumes", "Networks", "Compose"]
            onCurrentIndexChanged: controller.loadTab(["containers", "images", "volumes", "networks", "compose"][currentIndex]) }
        StackLayout {
            visible: d.available === true
            currentIndex: tabs.currentIndex
            Layout.fillWidth: true
            Layout.fillHeight: true
            ColumnLayout {
                NxTable {
                    id: containerTable
                    Layout.fillWidth: true; Layout.fillHeight: true
                    rows: d.containers || []
                    emptyText: "No containers"
                    columns: [{ title: "Name", role: "name", width: 0.2 }, { title: "Image", role: "image", width: 0.25 }, { title: "State", role: "state", width: 0.1 }, { title: "Status", role: "status", width: 0.2 }, { title: "Ports", width: 0.25, format: r => r.ports.join(", "), mono: true }]
                }
                RowLayout {
                    enabled: !!page.sel
                    Repeater {
                        model: ["start", "stop", "restart", "pause", "unpause"]
                        NxButton { required property string modelData; text: modelData; onClicked: controller.containerAction(page.sel.name, modelData) }
                    }
                    NxButton { text: "Remove"; variant: "danger"; onClicked: confirm.ask("Remove container", "Remove '" + page.sel.name + "' (forced)? Named volumes are kept.", ["docker rm -f " + page.sel.name], "Remove", true, () => controller.containerAction(page.sel.name, "remove")) }
                    NxButton { text: "Logs"; onClicked: { controller.logs(page.sel.name); detailTabs.currentIndex = 0 } }
                    NxButton { text: "Inspect"; onClicked: { controller.inspect(page.sel.name); detailTabs.currentIndex = 1 } }
                    NxButton { text: "Usage"; onClicked: controller.stats(page.sel.name) }
                    NxButton { text: "Terminal"; onClicked: controller.openShell(page.sel.name) }
                }
                Text { visible: !!d.stats; text: d.stats ? d.stats.id + ": CPU " + d.stats.cpu_percent + " %  ·  memory " + Theme.bytes(d.stats.memory_bytes) + (d.stats.memory_limit ? " / " + Theme.bytes(d.stats.memory_limit) : "") : ""; color: Theme.c.text; font.family: Theme.fontFamily }
                NxTabBar { id: detailTabs; tabs: ["Logs", "Inspect (secrets redacted)"] }
                NxLogView { Layout.fillWidth: true; Layout.preferredHeight: 200; text: detailTabs.currentIndex === 0 ? (d.logs || "") : (d.inspect || "") }
            }
            ColumnLayout {
                RowLayout {
                    NxTextField { id: pullRef; placeholderText: "image reference, e.g. nginx:1.27"; Layout.fillWidth: true }
                    NxButton { text: "Pull"; variant: "primary"; enabled: !!(pullRef.text.length > 0 && !d.pull); onClicked: controller.pullImage(pullRef.text) }
                    NxButton { text: "Search registry"; onClicked: controller.searchImages(pullRef.text) }
                }
                Text { visible: !!d.pull; text: d.pull ? d.pull.ref + ": " + d.pull.status + " " + (d.pull.progress || "") : ""; color: Theme.c.text; font.family: Theme.monoFamily; font.pixelSize: Theme.fontSmall }
                Text { visible: !!((d.searchResults || []).length > 0); text: (d.searchResults || []).slice(0, 8).map(r => r.name + (r.is_official ? " (official)" : "") + " ★" + r.star_count).join("   "); color: Theme.c.textSecondary; wrapMode: Text.WordWrap; Layout.fillWidth: true; font.family: Theme.fontFamily }
                NxTable {
                    id: imageTable
                    Layout.fillWidth: true; Layout.fillHeight: true
                    rows: d.images || []
                    columns: [{ title: "Tags", width: 0.5, format: r => r.tags.join(", ") }, { title: "ID", role: "id", width: 0.2, mono: true }, { title: "Size", width: 0.15, format: r => Theme.bytes(r.size) }, { title: "Created", width: 0.15, format: r => new Date(r.created * 1000).toLocaleDateString() }]
                }
                RowLayout {
                    enabled: !!imageTable.currentRow
                    NxTextField { id: newTag; placeholderText: "repo:tag"; Layout.preferredWidth: 220 }
                    NxButton { text: "Tag"; onClicked: { const i = newTag.text.lastIndexOf(":"); controller.tagImage(imageTable.currentRow.id, newTag.text.slice(0, i), newTag.text.slice(i + 1)) } }
                    NxButton { text: "Remove"; variant: "danger"; onClicked: confirm.ask("Remove image", imageTable.currentRow.tags.join(", "), [], "Remove", true, () => controller.removeImage(imageTable.currentRow.id, false)) }
                }
            }
            ColumnLayout {
                NxTable { id: volumeTable; Layout.fillWidth: true; Layout.fillHeight: true; rows: d.volumes || []; columns: [{ title: "Name", role: "name", width: 0.45 }, { title: "Driver", role: "driver", width: 0.15 }, { title: "Mountpoint", role: "mountpoint", width: 0.4, mono: true }] }
                RowLayout {
                    NxTextField { id: volName; placeholderText: "new volume name" }
                    NxButton { text: "Create"; onClicked: controller.createVolume(volName.text) }
                    NxButton { text: "Remove"; variant: "danger"; enabled: !!volumeTable.currentRow; onClicked: confirm.ask("Remove volume", "Delete volume '" + volumeTable.currentRow.name + "' and all its data?", [], "Remove", true, () => controller.removeVolume(volumeTable.currentRow.name), volumeTable.currentRow.name) }
                    NxButton { text: "Remove unused volumes"; variant: "danger"; onClicked: confirm.ask("Prune volumes", "Delete every volume not used by a container? This cannot be undone.", [], "Prune", true, () => controller.pruneVolumes()) }
                }
            }
            ColumnLayout {
                NxTable { id: netTable; Layout.fillWidth: true; Layout.fillHeight: true; rows: d.networks || []; columns: [{ title: "Name", role: "name", width: 0.35 }, { title: "Driver", role: "driver", width: 0.2 }, { title: "Scope", role: "scope", width: 0.15 }, { title: "Internal", width: 0.1, format: r => r.internal ? "yes" : "" }, { title: "ID", role: "id", width: 0.2, mono: true }] }
                RowLayout {
                    NxTextField { id: netName; placeholderText: "network name" }
                    NxButton { text: "Create"; onClicked: controller.createNetwork(netName.text) }
                    NxTextField { id: netContainer; placeholderText: "container name" }
                    NxButton { text: "Connect"; enabled: !!netTable.currentRow; onClicked: controller.networkConnect(netTable.currentRow.name, netContainer.text, true) }
                    NxButton { text: "Disconnect"; enabled: !!netTable.currentRow; onClicked: controller.networkConnect(netTable.currentRow.name, netContainer.text, false) }
                    NxButton { text: "Remove"; variant: "danger"; enabled: !!netTable.currentRow; onClicked: controller.removeNetwork(netTable.currentRow.name) }
                    NxButton { text: "Remove unused"; variant: "danger"; onClicked: confirm.ask("Prune networks", "Remove all unused networks?", [], "Prune", true, () => controller.pruneNetworks()) }
                }
            }
            ColumnLayout {
                NxTable { id: projTable; Layout.fillWidth: true; Layout.fillHeight: true; rows: d.projects || []; emptyText: "No Compose projects found"
                    columns: [{ title: "Project", role: "name", width: 0.25 }, { title: "Running", width: 0.15, format: r => r.running + " / " + r.total }, { title: "Services", width: 0.3, format: r => Object.keys(r.services).join(", ") }, { title: "Directory", role: "working_dir", width: 0.3, mono: true }] }
                RowLayout {
                    enabled: !!projTable.currentRow
                    Repeater { model: ["up", "stop", "restart", "pull"]; NxButton { required property string modelData; text: modelData; onClicked: controller.composeAction(projTable.currentRow.name, modelData) } }
                    NxButton { text: "Down"; variant: "danger"; onClicked: confirm.ask("Compose down", "Stop and remove the containers of '" + projTable.currentRow.name + "'? Volumes are kept.", [], "Down", true, () => controller.composeAction(projTable.currentRow.name, "down")) }
                    NxButton { text: "Logs"; onClicked: controller.composeLogs(projTable.currentRow.name) }
                }
                RowLayout {
                    NxTextField { id: projName; placeholderText: "project name (a-z0-9_-)" }
                    NxButton { text: "Choose compose file…"; onClicked: composeFile.open() }
                    Text { text: composeFile.selectedFile.toString().replace("file://", "") + "  " + (d.composeCheck || ""); color: Theme.c.textSecondary; font.family: Theme.fontFamily; Layout.fillWidth: true; elide: Text.ElideLeft }
                    NxButton { text: "Validate"; enabled: composeFile.selectedFile.toString().length > 0; onClicked: controller.composeValidate(projName.text, composeFile.selectedFile.toString()) }
                    NxButton { text: "Deploy"; variant: "primary"; enabled: !!(projName.text.length > 0 && composeFile.selectedFile.toString().length > 0); onClicked: confirm.ask("Deploy compose project", "Run 'docker compose up -d' for " + projName.text + "? Keep secrets in an .env file (mode 600), not in the compose file.", [], "Deploy", false, () => controller.composeDeploy(projName.text, composeFile.selectedFile.toString())) }
                }
                FileDialog { id: composeFile; nameFilters: ["Compose files (*.yaml *.yml)"] }
                NxLogView { Layout.fillWidth: true; Layout.preferredHeight: 160; text: d.logs || "" }
            }
        }
    }
}
