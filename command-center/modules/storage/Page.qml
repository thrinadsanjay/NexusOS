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
    readonly property var sel: diskTable.currentRow
    Connections {
        target: page.controller
        function onDataChanged() {
            const p = page.controller.data.plan
            if (p && !confirm.visible)
                confirm.ask("Format " + p.device, p.warnings.join("\n"), ["device: " + p.device + "  (disk " + p.disk + ")", "model: " + (p.model || "?") + "  serial: " + (p.serial || "none"), "size: " + Theme.bytes(p.size), "new filesystem: " + p.filesystem + (p.label ? "  label " + p.label : "")], "Format and erase", true,
                            token => page.controller.executeFormat(token), p.confirmation_token, () => page.controller.dismissPlan())
        }
    }
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.s5
        spacing: Theme.s3
        NxPageHeader { title: "Storage"; subtitle: "UDisks2, lsblk and smartmontools. Formatting is never automatic and is refused for system disks."
            NxButton { text: "Refresh"; onClicked: controller.refresh() } }
        NxErrorState { message: controller ? controller.error : ""; onRetry: controller.refresh() }
        NxTable {
            id: diskTable
            Layout.fillWidth: true
            Layout.preferredHeight: parent.height * 0.42
            rows: d.disks || []
            columns: [
                { title: "Device", width: 0.18, format: r => (r.depth ? "   └ " : "") + r.path, mono: true },
                { title: "Type", width: 0.12, format: r => r.depth ? r.type : r.media },
                { title: "Size", width: 0.1, format: r => Theme.bytes(r.size) },
                { title: "Model / FS", width: 0.2, format: r => r.depth ? (r.fstype || "") + (r.label ? " (" + r.label + ")" : "") : (r.model || "") },
                { title: "Mounted at", width: 0.2, format: r => r.mountpoints.join(", ") },
                { title: "Used", width: 0.1, format: r => r.fs_size ? Math.round(100 * r.fs_used / r.fs_size) + " %" : "" },
                { title: "Health", width: 0.1, format: r => { const s = d.smart ? d.smart[r.path] : null; if (!s) return d.temps && d.temps[r.name] ? d.temps[r.name] + " °C" : ""; if (!s.available) return "n/a"; return (s.passed ? "PASSED" : "FAILING") + (s.temperature_c ? " " + s.temperature_c + "°C" : "") } }
            ]
        }
        RowLayout {
            enabled: !!page.sel
            NxButton { admin: true; text: "SMART health"; enabled: !!(page.sel && page.sel.depth === 0); onClicked: controller.readSmart(page.sel.path) }
            NxButton { text: "Mount"; enabled: !!(page.sel && page.sel.fstype && page.sel.mountpoints.length === 0); onClicked: controller.mount(page.sel.path) }
            NxButton { text: "Unmount"; enabled: !!(page.sel && page.sel.mountpoints.length > 0); onClicked: controller.unmount(page.sel.path) }
            Item { Layout.fillWidth: true }
            ComboBox { id: fs; model: ["ext4", "xfs", "btrfs", "exfat", "vfat", "ntfs"] }
            NxTextField { id: fsLabel; placeholderText: "label"; Layout.preferredWidth: 120 }
            NxButton { admin: true; text: "Format…"; variant: "danger"; enabled: !!(page.sel && page.sel.mountpoints.length === 0); onClicked: controller.planFormat(page.sel.path, fs.currentText, fsLabel.text) }
        }
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            NxTable {
                Layout.fillWidth: true; Layout.fillHeight: true
                rows: d.usage || []
                columns: [{ title: "Mount", role: "mount", width: 0.3 }, { title: "Source", role: "source", width: 0.3, mono: true }, { title: "Type", role: "fstype", width: 0.1 }, { title: "Used / size", width: 0.3, format: r => Theme.bytes(r.used) + " / " + Theme.bytes(r.size) }]
            }
            NxTable {
                Layout.preferredWidth: 360; Layout.fillHeight: true
                rows: d.swaps || []
                emptyText: "No swap configured"
                columns: [{ title: "Swap", role: "device", width: 0.5, mono: true }, { title: "Size", width: 0.25, format: r => Theme.bytes(r.size_kib * 1024) }, { title: "Used", width: 0.25, format: r => Theme.bytes(r.used_kib * 1024) }]
            }
        }
        Text { text: "Partitioning and swap changes: planned. Use KDE Partition Manager meanwhile (also polkit-protected)."; color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall }
    }
}
