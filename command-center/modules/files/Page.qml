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
    readonly property var sel: fileTable.currentRow
    Component.onCompleted: if (intent.startsWith("file:")) Qt.callLater(() => controller.open(intent.slice(5).replace(/\/[^\/]*$/, "")))
    RowLayout {
        anchors.fill: parent
        anchors.margins: Theme.s5
        spacing: Theme.s4
        ColumnLayout {
            Layout.preferredWidth: 220
            Layout.fillHeight: true
            NxPageHeader { title: "Files"; subtitle: "KIO and Dolphin" }
            Repeater { model: d.places || []; NxButton { required property var modelData; text: modelData.title; variant: "ghost"; Layout.fillWidth: true; onClicked: controller.open(modelData.url.replace("file://", "")) } }
            Item { Layout.fillHeight: true }
            NxButton { text: "Open in Dolphin"; Layout.fillWidth: true; onClicked: controller.openInDolphin(d.path) }
        }
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            RowLayout {
                NxButton { text: "Up"; onClicked: controller.open(d.path.replace(/\/[^\/]+\/?$/, "") || "/") }
                NxTextField { text: d.path || ""; Layout.fillWidth: true; onAccepted: controller.open(text) }
                CheckBox { text: "Hidden"; checked: d.hidden || false; onToggled: controller.setHidden(checked) }
                NxTextField { id: q; placeholderText: "Search (Baloo index)"; Layout.preferredWidth: 200; onAccepted: controller.search(text) }
            }
            NxErrorState { message: controller ? controller.error : ""; onRetry: controller.refresh() }
            NxTable {
                id: fileTable
                Layout.fillWidth: true; Layout.fillHeight: true
                rows: (d.results || []).length && q.text ? d.results.map(p => ({ name: p, path: p, is_dir: false, size: 0, mode: "", mtime: 0 })) : (d.entries || [])
                columns: [{ title: "Name", width: 0.5, format: r => (r.is_dir ? "▸ " : "") + r.name }, { title: "Size", width: 0.15, format: r => r.is_dir ? "" : Theme.bytes(r.size) }, { title: "Permissions", role: "mode", width: 0.15, mono: true }, { title: "Modified", width: 0.2, format: r => r.mtime ? new Date(r.mtime * 1000).toLocaleString(Qt.locale(), Locale.ShortFormat) : "" }]
                onActivated: row => row.is_dir ? controller.open(row.path) : controller.openFile(row.path)
            }
            RowLayout {
                enabled: !!page.sel
                NxButton { text: "Open"; onClicked: page.sel.is_dir ? controller.open(page.sel.path) : controller.openFile(page.sel.path) }
                NxTextField { id: newName; placeholderText: "new name"; Layout.preferredWidth: 180 }
                NxButton { text: "Rename"; enabled: newName.text.length > 0; onClicked: controller.rename(page.sel.path, newName.text) }
                NxTextField { id: dest; placeholderText: "destination folder"; Layout.preferredWidth: 200 }
                NxButton { text: "Copy"; enabled: dest.text.length > 0; onClicked: controller.transfer(page.sel.path, dest.text, false) }
                NxButton { text: "Move"; enabled: dest.text.length > 0; onClicked: controller.transfer(page.sel.path, dest.text, true) }
                NxButton { text: "Extract"; enabled: !!(page.sel && /\.(zip|tar|tgz|gz|xz|bz2|7z|zst)$/.test(page.sel.name)); onClicked: controller.extract(page.sel.path) }
                NxButton { text: "Compress"; onClicked: controller.compress(page.sel.path) }
                NxButton { text: "Move to trash"; variant: "danger"; onClicked: confirm.ask("Move to trash", page.sel.path, [], "Move to trash", true, () => controller.trash(page.sel.path)) }
            }
            Text { text: "Permissions, properties, tabs, network locations and bulk operations: use Dolphin (same KIO backend)."; color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall }
        }
    }
}
