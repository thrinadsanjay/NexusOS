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
    readonly property bool online: !!(d.status && d.status.reachable)

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.s5
        spacing: Theme.s3
        NxPageHeader {
            title: "Local AI"
            subtitle: page.online ? "Ollama " + d.status.version + " at " + d.status.endpoint : "Ollama is optional. Nothing is downloaded or started unless you ask."
            NxButton { text: "Start Ollama"; visible: !!(d.status && d.status.cli_installed) && !page.online; onClicked: controller.service("start") }
            NxButton { text: "Stop Ollama"; visible: !!(page.online && d.serviceState === "active"); onClicked: controller.service("stop") }
            NxButton { text: "Refresh"; onClicked: controller.refresh() }
        }
        NxBanner {
            kind: "info"
            text: d.status && !d.status.cli_installed ? "Ollama is not installed. Install it from the official instructions (" + d.installDoc + ") after reviewing the script, or use the Local AI profile. Models are never downloaded automatically." : ""
        }
        NxErrorState { message: controller ? controller.error : ""; onRetry: controller.refresh() }
        NxTabBar { id: tabs; Layout.fillWidth: true; tabs: ["Chat", "Models"] }
        StackLayout {
            currentIndex: tabs.currentIndex
            Layout.fillWidth: true
            Layout.fillHeight: true

            // ------------------------------------------------------ chat
            RowLayout {
                spacing: Theme.s3
                ColumnLayout {
                    Layout.preferredWidth: 240
                    Layout.fillHeight: true
                    ComboBox { id: modelBox; Layout.fillWidth: true; model: (d.models || []).map(m => m.name); enabled: page.online }
                    NxButton { text: "New conversation"; variant: "primary"; Layout.fillWidth: true; enabled: !!(page.online && modelBox.currentText.length > 0); onClicked: controller.newConversation(modelBox.currentText) }
                    ListView {
                        Layout.fillWidth: true; Layout.fillHeight: true
                        clip: true
                        model: d.conversations || []
                        delegate: ItemDelegate {
                            required property var modelData
                            width: ListView.view.width
                            text: modelData.title
                            highlighted: d.conversation && d.conversation.id === modelData.id
                            onClicked: controller.openConversation(modelData.id)
                            contentItem: Text { text: parent.text; color: Theme.c.text; elide: Text.ElideRight; font.family: Theme.fontFamily }
                            background: Rectangle { radius: Theme.radiusSmall; color: parent.highlighted ? Theme.c.backgroundSecondary : "transparent" }
                        }
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    NxEmptyState { visible: !d.conversation; Layout.alignment: Qt.AlignCenter; title: page.online ? ((d.models || []).length ? "Start a conversation" : "No models installed") : "Ollama is not running"; message: page.online && !(d.models || []).length ? "Download a model in the Models tab, e.g. llama3.2:3b (≈2 GB)." : (page.online ? "" : "Start ollama.service, or install Ollama as described above. Nothing runs until you do.") }
                    RowLayout {
                        visible: !!d.conversation
                        Text { text: d.conversation ? d.conversation.model : ""; color: Theme.c.textSecondary; font.family: Theme.monoFamily; Layout.fillWidth: true }
                        NxButton { text: "Clear"; onClicked: controller.clearConversation() }
                        NxButton { text: "Delete"; variant: "danger"; onClicked: confirm.ask("Delete conversation", d.conversation.title, [], "Delete", true, () => controller.deleteConversation(d.conversation.id)) }
                    }
                    ListView {
                        id: messages
                        visible: !!d.conversation
                        Layout.fillWidth: true; Layout.fillHeight: true
                        clip: true
                        spacing: Theme.s2
                        model: (d.messages || []).concat(d.streaming ? [{ role: "assistant", content: d.draft || "…" }] : [])
                        onCountChanged: positionViewAtEnd()
                        delegate: Rectangle {
                            required property var modelData
                            width: messages.width
                            height: body.implicitHeight + Theme.s3 * 2
                            radius: Theme.radius
                            color: modelData.role === "user" ? Theme.c.backgroundSecondary : Theme.c.surface
                            border.color: Theme.c.border
                            TextEdit {
                                id: body
                                anchors.fill: parent
                                anchors.margins: Theme.s3
                                text: modelData.content
                                textFormat: modelData.role === "assistant" ? TextEdit.MarkdownText : TextEdit.PlainText
                                readOnly: true
                                selectByMouse: true
                                wrapMode: TextEdit.Wrap
                                color: Theme.c.text
                                font.family: Theme.fontFamily
                                font.pixelSize: Theme.fontBody
                            }
                            NxButton { anchors.top: parent.top; anchors.right: parent.right; anchors.margins: 4; text: "Copy"; variant: "ghost"; visible: modelData.role === "assistant"; onClicked: { body.selectAll(); body.copy(); body.deselect() } }
                        }
                    }
                    RowLayout {
                        visible: !!d.conversation
                        ScrollView {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 72
                            TextArea { id: input; placeholderText: "Message (Ctrl+Enter to send)"; wrapMode: TextArea.Wrap; color: Theme.c.text; font.family: Theme.fontFamily
                                background: Rectangle { color: Theme.c.background; border.color: Theme.c.border; radius: Theme.radiusSmall }
                                Keys.onPressed: e => { if ((e.modifiers & Qt.ControlModifier) && (e.key === Qt.Key_Return || e.key === Qt.Key_Enter)) { controller.send(text); text = ""; e.accepted = true } } }
                        }
                        NxButton { text: d.streaming ? "Stop" : "Send"; variant: d.streaming ? "danger" : "primary"; onClicked: { if (d.streaming) controller.stop(); else { controller.send(input.text); input.text = "" } } }
                    }
                    RowLayout {
                        NxTextField { id: sys; Layout.fillWidth: true; placeholderText: "System prompt for new conversations"; text: d.systemPrompt || ""; onEditingFinished: controller.setSystemPrompt(text) }
                        Text { text: "Temperature"; color: Theme.c.textSecondary; font.family: Theme.fontFamily }
                        SpinBox { id: temp; from: 0; to: 20; textFromValue: (v, l) => (v / 10).toFixed(1); valueFromText: (t, l) => Math.round(parseFloat(t) * 10); value: Math.round(((d.options || {}).temperature || 0.7) * 10); onValueModified: controller.setOptions(value / 10, ctx.value) }
                        Text { text: "Context"; color: Theme.c.textSecondary; font.family: Theme.fontFamily }
                        SpinBox { id: ctx; from: 0; to: 131072; stepSize: 2048; editable: true; Layout.preferredWidth: 210; textFromValue: (v, l) => v === 0 ? "model default" : String(v); valueFromText: (t, l) => /^[0-9]+$/.test(t.trim()) ? parseInt(t) : 0; value: (d.options || {}).num_ctx || 0; onValueModified: controller.setOptions(temp.value / 10, value) }
                    }
                }
            }

            // ------------------------------------------------------ models
            ColumnLayout {
                RowLayout {
                    NxTextField { id: pullName; placeholderText: "model to download, e.g. llama3.2:3b or qwen2.5-coder:1.5b"; Layout.fillWidth: true; enabled: page.online }
                    NxButton { text: "Download"; variant: "primary"; enabled: !!(page.online && pullName.text && !d.pull); onClicked: confirm.ask("Download model", "Download " + pullName.text + " from the Ollama registry? Models are several GB.", [], "Download", false, () => controller.pull(pullName.text)) }
                }
                RowLayout {
                    visible: !!d.pull
                    Text { text: d.pull ? d.pull.name + ": " + d.pull.status : ""; color: Theme.c.text; font.family: Theme.fontFamily }
                    NxProgress { value: d.pull ? d.pull.fraction : 0; Layout.fillWidth: true }
                    NxButton { text: "Cancel"; onClicked: controller.cancelPull() }
                }
                NxTable {
                    id: modelTable
                    Layout.fillWidth: true; Layout.fillHeight: true
                    rows: d.models || []
                    emptyText: page.online ? "No local models" : "Ollama is not reachable"
                    columns: [{ title: "Model", role: "name", width: 0.3 }, { title: "Size", width: 0.12, format: r => Theme.bytes(r.size_bytes) }, { title: "Parameters", role: "parameter_size", width: 0.13 }, { title: "Quantisation", role: "quantization", width: 0.15 }, { title: "Context", width: 0.15, format: r => d.info && d.info[r.name] && d.info[r.name].context_length ? d.info[r.name].context_length : "" }, { title: "Family", role: "family", width: 0.15 }]
                    onCurrentRowChanged: if (currentRow) controller.showModel(currentRow.name)
                }
                RowLayout {
                    NxButton { text: "Delete model"; variant: "danger"; enabled: !!modelTable.currentRow; onClicked: confirm.ask("Delete model", "Delete " + modelTable.currentRow.name + " (" + Theme.bytes(modelTable.currentRow.size_bytes) + ")?", [], "Delete", true, () => controller.deleteModel(modelTable.currentRow.name)) }
                    Text { text: "Loaded now: " + ((d.running || []).map(r => r.name + " " + Theme.bytes(r.size_bytes) + " (" + r.mode + (r.vram_bytes ? ", VRAM " + Theme.bytes(r.vram_bytes) : "") + ")").join(", ") || "none"); color: Theme.c.textSecondary; font.family: Theme.fontFamily; Layout.fillWidth: true; elide: Text.ElideRight }
                }
                Text { text: d.gpu ? "GPU acceleration: " + (d.gpu.nvidia.length ? "NVIDIA " + d.gpu.nvidia.join("; ") : d.gpu.amd_rocm_device ? "AMD ROCm device present" : "none detected (CPU inference)") : ""; color: Theme.c.textSecondary; font.family: Theme.fontFamily }
            }
        }
    }
}
