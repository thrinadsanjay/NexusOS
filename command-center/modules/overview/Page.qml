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
    readonly property var snap: d.snapshot || ({})
    function shown(w) { return (d.visible || []).indexOf(w) >= 0 }
    Component.onCompleted: if (controller && d.updates === null && !d.updatesChecking) controller.checkUpdates()

    ScrollView {
        anchors.fill: parent
        contentWidth: availableWidth
        ColumnLayout {
            width: parent.width
            anchors.margins: Theme.s5
            x: Theme.s5
            spacing: Theme.s4
            Item { Layout.preferredHeight: Theme.s3 }
            NxPageHeader {
                Layout.preferredWidth: page.width - Theme.s5 * 2
                title: "Overview"
                subtitle: (d.system ? d.system.os + "  ·  kernel " + d.system.kernel : "") + "  ·  refreshes every " + Math.round(App.monitoringInterval / 1000) + " s while visible"
                NxButton { text: "Customize"; onClicked: widgetMenu.open() }
                NxButton { text: "Refresh"; variant: "primary"; onClicked: controller.refresh() }
            }
            Menu {
                id: widgetMenu
                Repeater {
                    model: d.widgets || []
                    MenuItem { required property string modelData; text: modelData; checkable: true; checked: page.shown(modelData); onToggled: controller.setWidgetVisible(modelData, checked) }
                }
            }
            NxErrorState { message: controller ? controller.error : ""; onRetry: controller.refresh(); Layout.preferredWidth: page.width - Theme.s5 * 2 }

            GridLayout {
                Layout.preferredWidth: page.width - Theme.s5 * 2
                columns: Math.max(2, Math.floor((page.width - 48) / 260))
                columnSpacing: Theme.s3
                rowSpacing: Theme.s3
                NxMetric {
                    visible: page.shown("cpu")
                    label: "CPU"
                    value: snap.cpu_percent === null || snap.cpu_percent === undefined ? "measuring…" : snap.cpu_percent.toFixed(0) + " %"
                    detail: snap.load ? "load " + snap.load.map(v => v.toFixed(2)).join(" ") : ""
                    fraction: snap.cpu_percent ? snap.cpu_percent / 100 : 0
                }
                NxMetric {
                    visible: page.shown("memory")
                    label: "Memory"
                    value: snap.memory_total ? Theme.bytes(snap.memory_total - snap.memory_available) : "n/a"
                    detail: snap.memory_total ? "of " + Theme.bytes(snap.memory_total) + (snap.swap_total ? "  ·  swap " + Theme.bytes(snap.swap_total - snap.swap_free) + " / " + Theme.bytes(snap.swap_total) : "  ·  no swap") : ""
                    fraction: snap.memory_total ? 1 - snap.memory_available / snap.memory_total : -1
                }
                NxMetric {
                    visible: page.shown("temperature")
                    label: "Temperature"
                    value: snap.temperatures && snap.temperatures.length ? Math.max(...snap.temperatures.map(t => t.celsius)).toFixed(0) + " °C" : "unavailable"
                    detail: snap.temperatures && snap.temperatures.length ? snap.temperatures[0].label : (snap.temperature_note || "")
                }
                NxMetric {
                    visible: page.shown("system")
                    label: "Uptime"
                    value: Theme.duration(snap.uptime_seconds)
                    detail: (snap.process_count || 0) + " processes" + (d.system && d.system.build ? "  ·  build " + d.system.build : "")
                }
                NxMetric {
                    visible: page.shown("updates")
                    label: "Package updates"
                    value: d.updatesChecking ? "checking…" : (d.updates === null || d.updates === undefined ? "unknown" : d.updates + " available")
                    detail: d.updatesChecked ? "checked " + d.updatesChecked + " (local package indexes)" : ""
                    status: d.updates > 0 ? "warn" : ""
                }
                NxMetric {
                    visible: page.shown("network")
                    label: "Network"
                    value: snap.net && snap.net.length ? "↓ " + Theme.bytes(snap.net.reduce((a, n) => a + n.rx_bytes_per_s, 0)) + "/s" : "measuring…"
                    detail: snap.net && snap.net.length ? "↑ " + Theme.bytes(snap.net.reduce((a, n) => a + n.tx_bytes_per_s, 0)) + "/s  ·  " + snap.net.map(n => n.interface).join(", ") : ""
                }
            }

            RowLayout {
                Layout.preferredWidth: page.width - Theme.s5 * 2
                spacing: Theme.s3
                NxCard {
                    visible: page.shown("services")
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignTop
                    ColumnLayout {
                        width: parent.width
                        NxSectionTitle { text: "Services" }
                        Repeater {
                            model: d.services || []
                            RowLayout {
                                required property var modelData
                                Text { text: modelData.unit; color: Theme.c.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; Layout.fillWidth: true }
                                NxStatusBadge { status: modelData.state === "active" ? "ok" : modelData.state === "failed" ? "fail" : "unknown"; label: modelData.state === "not-found" ? "not installed" : modelData.state }
                            }
                        }
                        RowLayout {
                            visible: !!d.ollama
                            Text { text: "Ollama API"; color: Theme.c.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; Layout.fillWidth: true }
                            NxStatusBadge { status: d.ollama && d.ollama.reachable ? "ok" : "unknown"; label: d.ollama && d.ollama.reachable ? "v" + d.ollama.version : (d.ollama && d.ollama.installed ? "stopped" : "not installed") }
                        }
                    }
                }
                NxCard {
                    visible: page.shown("disks")
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignTop
                    ColumnLayout {
                        width: parent.width
                        NxSectionTitle { text: "Disk usage" }
                        Repeater {
                            model: d.usage || []
                            ColumnLayout {
                                required property var modelData
                                Layout.fillWidth: true
                                RowLayout {
                                    Text { text: modelData.mount; color: Theme.c.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; Layout.fillWidth: true }
                                    Text { text: Theme.bytes(modelData.used) + " / " + Theme.bytes(modelData.size); color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall }
                                }
                                NxProgress { value: modelData.size ? modelData.used / modelData.size : 0; Layout.fillWidth: true }
                            }
                        }
                        Text { text: "Disk health (SMART): see Storage"; color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall }
                    }
                }
                NxCard {
                    visible: !!(page.shown("gpu") || page.shown("apps"))
                    Layout.fillWidth: true
                    Layout.alignment: Qt.AlignTop
                    ColumnLayout {
                        width: parent.width
                        NxSectionTitle { text: "GPU" }
                        Text { visible: !!(!(d.gpus && d.gpus.length)); text: "No GPU information exposed"; color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody }
                        Repeater {
                            model: d.gpus || []
                            Text { required property var modelData; text: modelData.name + (modelData.busy_percent !== null ? "  ·  " + modelData.busy_percent + " % busy" : "") + (modelData.vram_total_bytes ? "  ·  VRAM " + Theme.bytes(modelData.vram_used_bytes) + " / " + Theme.bytes(modelData.vram_total_bytes) : ""); color: Theme.c.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; wrapMode: Text.WordWrap; Layout.fillWidth: true }
                        }
                        NxSectionTitle { text: "Nexus applications" }
                        Text { visible: !!(!(d.apps && d.apps.length)); text: "None installed"; color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody }
                        Repeater {
                            model: d.apps || []
                            RowLayout { required property var modelData; Text { text: modelData.name; color: Theme.c.text; font.family: Theme.fontFamily; Layout.fillWidth: true } NxStatusBadge { status: modelData.health; label: modelData.health } }
                        }
                    }
                }
            }
            NxSectionTitle { visible: page.shown("processes"); text: "Top processes (memory)" }
            NxTable {
                visible: page.shown("processes")
                Layout.preferredWidth: page.width - Theme.s5 * 2
                Layout.preferredHeight: 330
                rows: d.processes || []
                columns: [
                    { title: "PID", role: "pid", width: 0.12, mono: true },
                    { title: "Name", role: "name", width: 0.4 },
                    { title: "Memory", width: 0.2, format: r => Theme.bytes(r.rss_bytes) },
                    { title: "UID", role: "user_id", width: 0.12 },
                    { title: "State", role: "state", width: 0.16 }
                ]
            }
            Item { Layout.preferredHeight: Theme.s5 }
        }
    }
}
