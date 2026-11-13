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
    property string filter: ""
    property string groupFilter: "All"
    property var selected: null
    readonly property var visibleProfiles: (d.profiles || []).filter(p =>
        (groupFilter === "All" || (groupFilter === "Favorites" ? p.favorite : p.group === groupFilter)) &&
        (filter === "" || (p.name + " " + p.host + " " + p.user + " " + p.tags.join(" ")).toLowerCase().indexOf(filter.toLowerCase()) >= 0))

    Component.onCompleted: if (intent.startsWith("profile:")) Qt.callLater(() => { page.selected = (d.profiles || []).find(p => p.id === intent.slice(8)) || null })

    function blankProfile() {
        return { id: "", name: "", host: "", port: 22, user: "", auth: "agent", key_path: null, credential_ref: null, jump_profile_id: null,
                 agent_forwarding: false, agent_forwarding_consent: null, forwards: [], options: {}, group: "Custom", tags: [], favorite: false,
                 konsole_profile: "Nexus", reconnect_on_restore: false, notes: "" }
    }

    RowLayout {
        anchors.fill: parent
        anchors.margins: Theme.s5
        spacing: Theme.s4

        // ------------------------------------------------------------ connection navigator
        ColumnLayout {
            Layout.preferredWidth: 300
            Layout.fillHeight: true
            spacing: Theme.s2
            NxPageHeader { title: "Terminal & SSH"; subtitle: "OpenSSH sessions in Konsole tabs" }
            RowLayout {
                NxButton { text: "New terminal"; variant: "primary"; onClicked: localDialog.open() }
                NxButton { text: "New SSH profile"; onClicked: { editor.load(page.blankProfile()); editor.open() } }
            }
            NxTextField { Layout.fillWidth: true; placeholderText: "Search hosts, users, tags"; onTextChanged: page.filter = text }
            ComboBox { Layout.fillWidth: true; model: ["All", ...(d.groups || [])]; onActivated: page.groupFilter = currentText }
            Text { visible: !!((d.recent || []).length > 0); text: "Recent"; color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall }
            Flow {
                Layout.fillWidth: true
                spacing: Theme.s1
                Repeater { model: d.recent || []; NxButton { required property var modelData; text: modelData.name; variant: "ghost"; onClicked: page.selected = modelData } }
            }
            ListView {
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                model: page.visibleProfiles
                section.property: "group"
                section.delegate: Text { required property string section; text: section; color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall; topPadding: Theme.s2 }
                delegate: ItemDelegate {
                    required property var modelData
                    width: ListView.view.width
                    highlighted: page.selected && page.selected.id === modelData.id
                    onClicked: page.selected = modelData
                    onDoubleClicked: controller.connect(modelData.id)
                    contentItem: ColumnLayout {
                        spacing: 0
                        Text { text: (parent.parent.modelData.favorite ? "★ " : "") + parent.parent.modelData.name; color: Theme.c.text; font.family: Theme.fontFamily }
                        Text { text: parent.parent.modelData.user + "@" + parent.parent.modelData.host + ":" + parent.parent.modelData.port + "  ·  " + parent.parent.modelData.auth; color: Theme.c.textSecondary; font.family: Theme.monoFamily; font.pixelSize: Theme.fontSmall }
                    }
                    background: Rectangle { radius: Theme.radiusSmall; color: parent.highlighted ? Theme.c.backgroundSecondary : parent.hovered ? Theme.c.surfaceElevated : "transparent" }
                }
                NxEmptyState { anchors.centerIn: parent; visible: parent.count === 0; title: "No SSH profiles"; message: "Create a profile to save hosts, jump hosts and port forwards." }
            }
        }

        // ------------------------------------------------------------ workspace
        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: Theme.s3
            NxErrorState { message: controller ? controller.error : ""; onRetry: controller.refresh() }
            NxTabBar { id: tabs; Layout.fillWidth: true; tabs: ["Session", "SFTP", "Credentials", "History"] }
            StackLayout {
                currentIndex: tabs.currentIndex
                Layout.fillWidth: true
                Layout.fillHeight: true

                // -------------------------------------------------- session
                ColumnLayout {
                    spacing: Theme.s3
                    NxEmptyState { visible: !page.selected; Layout.alignment: Qt.AlignCenter; title: "Select a connection"; message: "Double-click a profile to open it in a Konsole tab. Konsole provides tabs, split panes (Ctrl+( / Ctrl+)), search (Ctrl+Shift+F), themes and output export." }
                    ColumnLayout {
                        visible: !!page.selected
                        spacing: Theme.s2
                        Text { text: page.selected ? page.selected.name : ""; color: Theme.c.text; font.pixelSize: Theme.fontDisplay; font.family: Theme.fontFamily; font.weight: Font.DemiBold }
                        Text { text: page.selected ? page.selected.user + "@" + page.selected.host + ":" + page.selected.port : ""; color: Theme.c.textSecondary; font.family: Theme.monoFamily }
                        RowLayout {
                            NxButton { text: "Connect"; variant: "primary"; onClicked: controller.connect(page.selected.id) }
                            NxButton { text: "Verify host key"; onClicked: controller.scanHostKey(page.selected.id) }
                            NxButton { text: "Browse files (SFTP)"; onClicked: { tabs.currentIndex = 1; controller.sftpOpen(page.selected.id) } }
                            NxButton { text: "Edit"; onClicked: { editor.load(page.selected); editor.open() } }
                            NxButton { text: "Delete"; variant: "danger"; onClicked: confirm.ask("Delete profile", "Delete '" + page.selected.name + "'? Saved credentials stay in the wallet.", [], "Delete", true, () => { controller.deleteProfile(page.selected.id); page.selected = null }) }
                        }
                        NxFormRow { label: "Authentication"; Text { text: page.selected ? page.selected.auth + (page.selected.credential_ref ? " (credential: " + page.selected.credential_ref + ")" : "") + (page.selected.key_path ? " (key: " + page.selected.key_path + ")" : "") : ""; color: Theme.c.text; font.family: Theme.fontFamily } }
                        NxFormRow { label: "Jump host"; Text { text: page.selected && page.selected.jump_profile_id ? ((d.profiles || []).find(p => p.id === page.selected.jump_profile_id) || {}).name || page.selected.jump_profile_id : "—"; color: Theme.c.text; font.family: Theme.fontFamily } }
                        NxFormRow { label: "Agent forwarding"; Text { text: page.selected && page.selected.agent_forwarding ? "enabled (consented)" : "off"; color: page.selected && page.selected.agent_forwarding ? Theme.c.warning : Theme.c.text; font.family: Theme.fontFamily } }
                        NxFormRow { label: "Port forwards"; Text { text: page.selected && page.selected.forwards.length ? page.selected.forwards.map(f => f.kind + " " + f.bind_address + ":" + f.listen_port + (f.dest_host ? " → " + f.dest_host + ":" + f.dest_port : " (SOCKS)")).join("\n") : "—"; color: Theme.c.text; font.family: Theme.monoFamily; font.pixelSize: Theme.fontSmall } }
                        NxFormRow { label: "Tags"; Text { text: page.selected ? page.selected.tags.join(", ") || "—" : ""; color: Theme.c.text; font.family: Theme.fontFamily } }
                    }
                    NxCard {
                        visible: !!((d.hostkeys || []).length > 0 && page.selected && d.hostkeysFor === page.selected.id)
                        Layout.fillWidth: true
                        ColumnLayout {
                            width: parent.width
                            NxSectionTitle { text: d.hostKnown ? "Host key already trusted" : "Compare these fingerprints with the server before trusting it" }
                            Repeater { model: d.hostkeys || []; Text { required property var modelData; text: modelData.key_type + "  " + modelData.fingerprint; color: Theme.c.text; font.family: Theme.monoFamily; font.pixelSize: Theme.fontSmall } }
                            NxButton { visible: !d.hostKnown; text: "Trust these keys"; onClicked: confirm.ask("Trust host key", "Only trust the key if the fingerprint matches what the server administrator gave you.", d.hostkeys.map(k => k.key_type + " " + k.fingerprint), "Trust", true, () => controller.trustHostKeys()) }
                        }
                    }
                    Item { Layout.fillHeight: true }
                }

                // -------------------------------------------------- SFTP
                ColumnLayout {
                    RowLayout {
                        NxButton { text: "Up"; onClicked: controller.sftpList(d.remotePath === "." ? ".." : d.remotePath.replace(/\/[^\/]*$/, "") || "/") }
                        NxTextField { id: remotePath; text: d.remotePath || "."; Layout.fillWidth: true; onAccepted: controller.sftpList(text) }
                        NxButton { text: "New folder"; onClicked: controller.sftpMkdir(d.remotePath + "/new-folder") }
                        NxButton { text: "Upload…"; onClicked: uploadDialog.open() }
                        NxButton { text: "Download"; enabled: !!(!!remoteTable.currentRow && !remoteTable.currentRow.is_dir); onClicked: downloadDialog.open() }
                        NxButton { text: "Delete"; variant: "danger"; enabled: !!remoteTable.currentRow; onClicked: confirm.ask("Delete remote item", remoteTable.currentRow.path, [], "Delete", true, () => controller.sftpDelete(remoteTable.currentRow.path)) }
                    }
                    Repeater {
                        model: d.transfers || []
                        RowLayout {
                            required property var modelData
                            Text { text: modelData.kind + " " + modelData.name; color: Theme.c.text; font.family: Theme.fontFamily }
                            NxProgress { value: modelData.total ? modelData.done / modelData.total : 0; Layout.fillWidth: true }
                            NxButton { text: "Cancel"; onClicked: controller.cancelTransfer() }
                        }
                    }
                    NxTable {
                        id: remoteTable
                        Layout.fillWidth: true; Layout.fillHeight: true
                        rows: d.remote || []
                        emptyText: "Open a profile's files with “Browse files (SFTP)”"
                        columns: [{ title: "Name", width: 0.45, format: r => (r.is_dir ? "▸ " : "") + r.name }, { title: "Size", width: 0.15, format: r => r.is_dir ? "" : Theme.bytes(r.size) }, { title: "Mode", role: "mode", width: 0.2, mono: true }, { title: "Modified", width: 0.2, format: r => new Date(r.mtime * 1000).toLocaleString(Qt.locale(), Locale.ShortFormat) }]
                        onActivated: row => { if (row.is_dir) controller.sftpList(row.path) }
                    }
                    FileDialog { id: uploadDialog; title: "Upload file"; onAccepted: controller.sftpUpload(selectedFile.toString(), d.remotePath) }
                    FolderDialog { id: downloadDialog; title: "Download to folder"; onAccepted: controller.sftpDownload(remoteTable.currentRow.path, selectedFolder.toString()) }
                }

                // -------------------------------------------------- credentials
                ColumnLayout {
                    NxBanner { kind: "info"; text: "Secrets are stored in KDE Wallet (Secret Service). NexusOS never writes passwords to files, logs or command lines." }
                    NxBanner { kind: "error"; text: d.credentialsError || "" }
                    NxTable {
                        id: credTable
                        Layout.fillWidth: true; Layout.fillHeight: true
                        rows: d.credentials || []
                        emptyText: "No saved credentials"
                        columns: [{ title: "Reference", role: "ref", width: 0.3 }, { title: "Type", role: "kind", width: 0.25 }, { title: "Username", role: "username", width: 0.2 }, { title: "Rotation", width: 0.25, format: r => r.rotate_after_days ? "every " + r.rotate_after_days + " days" : "—" }]
                    }
                    RowLayout {
                        NxTextField { id: credRef; placeholderText: "reference (e.g. homelab-root)"; Layout.preferredWidth: 200 }
                        ComboBox { id: credKind; model: ["ssh-password", "ssh-key-passphrase", "generic"] }
                        NxTextField { id: credUser; placeholderText: "username (optional)"; Layout.preferredWidth: 150 }
                        NxTextField { id: credSecret; placeholderText: "secret"; echoMode: TextInput.Password; Layout.fillWidth: true }
                        SpinBox { id: credRotate; from: 0; to: 365; value: 0; ToolTip.text: "rotation reminder (days, 0 = none)"; ToolTip.visible: hovered }
                        NxButton { text: "Save to wallet"; variant: "primary"; enabled: !!(credRef.text && credSecret.text); onClicked: { controller.saveCredential(credRef.text, credKind.currentText, credSecret.text, credUser.text, credRotate.value); credSecret.text = "" } }
                        NxButton { text: "Delete"; variant: "danger"; enabled: !!credTable.currentRow; onClicked: confirm.ask("Delete credential", "Remove '" + credTable.currentRow.ref + "' from the wallet?", [], "Delete", true, () => controller.deleteCredential(credTable.currentRow.ref)) }
                    }
                }

                // -------------------------------------------------- history
                NxTable {
                    rows: d.history || []
                    columns: [{ title: "Time", width: 0.3, format: r => new Date(r.ts * 1000).toLocaleString(Qt.locale(), Locale.ShortFormat) }, { title: "Profile", width: 0.4, format: r => r.name || r.profile_id }, { title: "Event", role: "event", width: 0.3 }]
                }
            }
        }
    }

    // ------------------------------------------------------------ dialogs
    Dialog {
        id: localDialog
        title: "New local terminal"
        modal: true
        anchors.centerIn: parent
        standardButtons: Dialog.Open | Dialog.Cancel
        ColumnLayout {
            NxFormRow { label: "Shell"; ComboBox { id: shellBox; model: ["default", "bash", "zsh"] } }
            NxFormRow { label: "Working directory"; NxTextField { id: workdir; text: "~"; width: 280 } }
            NxFormRow { label: "Tab title"; NxTextField { id: tabTitle; text: "Terminal"; width: 280 } }
        }
        onAccepted: controller.openTerminal(shellBox.currentText, workdir.text, tabTitle.text)
    }

    Dialog {
        id: editor
        title: "SSH profile"
        modal: true
        anchors.centerIn: parent
        width: Math.min(page.width - 60, 720)
        property var p: page.blankProfile()
        function load(profile) { p = JSON.parse(JSON.stringify(profile)); fName.text = p.name; fHost.text = p.host; fPort.value = p.port; fUser.text = p.user; fAuth.currentIndex = ["agent", "key", "password"].indexOf(p.auth); fKey.text = p.key_path || ""; fCred.text = p.credential_ref || ""; fGroup.editText = p.group; fTags.text = p.tags.join(", "); fFav.checked = p.favorite; fAgent.checked = p.agent_forwarding; fForwards.text = p.forwards.map(f => f.kind === "dynamic" ? "D " + f.bind_address + ":" + f.listen_port : (f.kind === "local" ? "L " : "R ") + f.bind_address + ":" + f.listen_port + " " + f.dest_host + ":" + f.dest_port).join("\n"); fJump.currentIndex = Math.max(0, (d.profiles || []).findIndex(x => x.id === p.jump_profile_id) + 1) }
        function parseForwards(text) {
            const out = []
            for (const line of text.split("\n").map(l => l.trim()).filter(Boolean)) {
                const parts = line.split(/\s+/)
                const [bind, lport] = parts[1].includes(":") ? [parts[1].slice(0, parts[1].lastIndexOf(":")), parts[1].slice(parts[1].lastIndexOf(":") + 1)] : ["127.0.0.1", parts[1]]
                if (parts[0] === "D") out.push({ kind: "dynamic", bind_address: bind, listen_port: parseInt(lport) })
                else { const dest = parts[2]; out.push({ kind: parts[0] === "L" ? "local" : "remote", bind_address: bind, listen_port: parseInt(lport), dest_host: dest.slice(0, dest.lastIndexOf(":")), dest_port: parseInt(dest.slice(dest.lastIndexOf(":") + 1)) }) }
            }
            return out
        }
        ScrollView {
            implicitHeight: Math.min(560, page.height - 160)
            implicitWidth: editor.width - 40
            ColumnLayout {
                width: editor.width - 60
                NxFormRow { label: "Name"; NxTextField { id: fName; width: parent.width } }
                NxFormRow { label: "Host"; NxTextField { id: fHost; width: parent.width; placeholderText: "hostname or IP" } }
                NxFormRow { label: "Port"; SpinBox { id: fPort; from: 1; to: 65535; editable: true } }
                NxFormRow { label: "Username"; NxTextField { id: fUser; width: parent.width } }
                NxFormRow { label: "Authentication"; ComboBox { id: fAuth; model: ["agent", "key", "password"] } }
                NxFormRow { label: "Private key file"; NxTextField { id: fKey; width: parent.width; placeholderText: "~/.ssh/id_ed25519 (reference only; the key stays where it is)"; enabled: fAuth.currentText === "key" } }
                NxFormRow { label: "Credential reference"; NxTextField { id: fCred; width: parent.width; placeholderText: "wallet reference for the password / key passphrase" } }
                NxFormRow { label: "Jump host"; ComboBox { id: fJump; width: parent.width; model: ["none", ...(d.profiles || []).map(x => x.name)] } }
                NxFormRow { label: "Group"; ComboBox { id: fGroup; editable: true; model: d.groups || [] } }
                NxFormRow { label: "Tags"; NxTextField { id: fTags; width: parent.width; placeholderText: "comma separated" } }
                NxFormRow { label: "Favorite"; CheckBox { id: fFav } }
                NxFormRow { label: "Port forwards"; TextArea { id: fForwards; width: parent.width; height: 70; placeholderText: "L 127.0.0.1:8080 db.internal:5432\nR 127.0.0.1:9000 localhost:3000\nD 127.0.0.1:1080"; font.family: Theme.monoFamily } }
                NxFormRow { label: "Agent forwarding"; CheckBox { id: fAgent; text: "Allow the remote host to use my SSH agent" } }
                Text { visible: fAgent.checked; text: "Warning: anyone with root on the remote host can use your keys while you are connected. Saving this profile records your consent."; color: Theme.c.warning; wrapMode: Text.WordWrap; Layout.fillWidth: true; font.family: Theme.fontFamily }
                Text { text: "Production hosts are never reconnected automatically."; color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall }
            }
        }
        footer: DialogButtonBox {
            NxButton { text: "Cancel"; DialogButtonBox.buttonRole: DialogButtonBox.RejectRole }
            NxButton {
                text: "Save"; variant: "primary"
                onClicked: {
                    const p = editor.p
                    const jump = fJump.currentIndex > 0 ? d.profiles[fJump.currentIndex - 1].id : null
                    const out = Object.assign({}, p, { name: fName.text, host: fHost.text, port: fPort.value, user: fUser.text, auth: fAuth.currentText,
                        key_path: fKey.text || null, credential_ref: fCred.text || null, jump_profile_id: jump, group: fGroup.editText || "Custom",
                        tags: fTags.text.split(",").map(t => t.trim()).filter(Boolean), favorite: fFav.checked, agent_forwarding: fAgent.checked,
                        agent_forwarding_consent: fAgent.checked ? (p.agent_forwarding_consent || Date.now() / 1000) : null,
                        forwards: editor.parseForwards(fForwards.text) })
                    controller.saveProfile(JSON.stringify(out))
                    editor.close()
                }
            }
        }
    }
}
