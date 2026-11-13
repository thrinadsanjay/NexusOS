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
    readonly property var details: d.details || null

    Component.onCompleted: {
        if (intent.startsWith("details:")) { tabs.currentIndex = 0; controller.search(intent.slice(8)); controller.select(intent.slice(8)) }
        else if (intent === "packages.upgrade") { tabs.currentIndex = 2; controller.loadUpdates() }
        else if (intent === "packages.update") askUpdateIndexes()
    }

    function planText(plan) {
        const lines = ["$ " + plan.command.join(" "), ""]
        for (const c of plan.changes) lines.push(c.action.padEnd(9) + " " + c.name + (c.old_version ? "  " + c.old_version : "") + (c.new_version ? "  → " + c.new_version : ""))
        if (plan.warnings.length) { lines.push(""); for (const w of plan.warnings) lines.push("! " + w) }
        return lines
    }
    function askUpdateIndexes() {
        confirm.ask("Refresh package indexes", "Download the latest package lists from the configured repositories.", ["$ apt-get update"], "Refresh", false,
                    () => { controller.plan("update", "[]") })
    }
    Connections {
        target: page.controller
        function onDataChanged() {
            const p = page.controller.data.plan
            if (p && !confirm.visible) {
                confirm.ask(p.operation === "update" ? "Refresh package indexes" : "Review " + p.operation,
                            p.changes.length === 0 && p.operation !== "update" ? "Nothing to change." : "The following changes will be made. Administrator authentication is requested by polkit.",
                            page.planText(p), p.destructive ? "Apply changes" : "Continue", p.destructive,
                            () => page.controller.execute(), "", () => page.controller.dismissPlan())
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.s5
        spacing: Theme.s3
        NxPageHeader {
            title: "Software Center"
            subtitle: "Ubuntu APT and dpkg — the same packages and history as the terminal (apt, dpkg remain fully available)."
            NxButton { text: "Refresh indexes"; enabled: !!(d.agent && !(d.op && d.op.running)); onClicked: page.askUpdateIndexes() }
        }
        NxBanner { kind: "warning"; text: d.agent ? "" : "The NexusOS management agent is not installed: you can browse, but installing and removing are disabled. Install nexusos-management-agent." }
        NxBanner { kind: "warning"; text: d.lock && d.lock.locked ? "The package manager is in use by " + (d.lock.holder_name || "another program") + " (pid " + d.lock.holder_pid + "). Operations will wait until it finishes." : "" }
        NxErrorState { message: controller ? controller.error : ""; onRetry: controller.refresh() }

        // ------------------------------------------------------------ progress of a running operation
        NxCard {
            visible: !!(d.op && (d.op.running || d.op.phase === "done" || d.op.phase === "failed" || d.op.phase === "cancelled"))
            Layout.fillWidth: true
            Layout.preferredHeight: 200
            ColumnLayout {
                anchors.fill: parent
                RowLayout {
                    Text { text: (d.op ? d.op.phase : "") + (d.op && d.op.message ? " — " + d.op.message : ""); color: Theme.c.text; font.family: Theme.fontFamily; Layout.fillWidth: true; elide: Text.ElideRight }
                    NxButton { text: "Cancel"; visible: !!(d.op && d.op.running); enabled: !!(d.op && (d.op.phase === "download" || d.op.phase === "starting" || d.op.phase === "prepare")); onClicked: controller.cancel() }
                }
                NxProgress { value: d.op ? d.op.percent / 100 : 0; Layout.fillWidth: true }
                NxLogView { text: d.op ? d.op.log : ""; Layout.fillWidth: true; Layout.fillHeight: true }
            }
        }

        NxTabBar {
            id: tabs
            Layout.fillWidth: true
            tabs: ["Search & browse", "Installed", "Updates", "History", "Repositories"]
            onCurrentIndexChanged: {
                if (currentIndex === 1) controller.loadInstalled(appsOnly.checked)
                else if (currentIndex === 2) controller.loadUpdates()
                else if (currentIndex === 3) controller.loadHistory()
                else if (currentIndex === 4) controller.loadRepos()
            }
        }
        StackLayout {
            currentIndex: tabs.currentIndex
            Layout.fillWidth: true
            Layout.fillHeight: true

            // ------------------------------------------------------ search
            RowLayout {
                spacing: Theme.s3
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.horizontalStretchFactor: 45
                    Layout.fillHeight: true
                    RowLayout {
                        NxTextField { id: term; Layout.fillWidth: true; placeholderText: "Search 70,000+ packages by name or description"; onAccepted: controller.search(text) }
                        NxButton { text: "Search"; variant: "primary"; onClicked: controller.search(term.text) }
                        NxButton { text: "Browse"; onClicked: { controller.loadSections(); sectionMenu.open() } }
                    }
                    Menu {
                        id: sectionMenu
                        Repeater { model: d.sections || []; MenuItem { required property var modelData; text: modelData.name + " (" + modelData.count + ")"; onTriggered: controller.browse(modelData.name) } }
                    }
                    NxLoading { running: controller ? controller.busy : false }
                    NxTable {
                        id: resultTable
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        rows: d.results || []
                        emptyText: "Search for software, or browse by section"
                        columns: [
                            { title: "Package", role: "name", width: 0.35 },
                            { title: "Summary", role: "summary", width: 0.45 },
                            { title: "Installed", width: 0.2, format: r => r.installed_version || "" }
                        ]
                        onCurrentRowChanged: if (currentRow) controller.select(currentRow.name)
                    }
                }
                NxCard {
                    Layout.fillWidth: true
                    Layout.horizontalStretchFactor: 55
                    Layout.fillHeight: true
                    NxEmptyState { anchors.centerIn: parent; visible: !page.details; title: "Select a package"; message: "Details, versions and dependencies appear here." }
                    ScrollView {
                        anchors.fill: parent
                        visible: !!page.details
                        ColumnLayout {
                            width: parent.width
                            spacing: Theme.s2
                            Text { text: page.details ? page.details.name : ""; color: Theme.c.text; font.pixelSize: Theme.fontDisplay; font.family: Theme.fontFamily; font.weight: Font.DemiBold }
                            Text { text: page.details ? (page.details.installed_version ? "Installed " + page.details.installed_version : "Not installed") + "  ·  candidate " + (page.details.candidate_version || "none") + "  ·  " + (page.details.section || "") : ""; color: Theme.c.textSecondary; font.family: Theme.fontFamily }
                            Text { text: page.details ? "Download " + Theme.bytes(page.details.download_size_bytes) + "  ·  installed size " + Theme.bytes((page.details.installed_size_kib || 0) * 1024) + (page.details.origin ? "  ·  " + page.details.origin : "") : ""; color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall }
                            RowLayout {
                                enabled: !!(d.agent && !(d.op && d.op.running) && !!page.details)
                                NxButton { text: "Install"; variant: "primary"; visible: !!(page.details && !page.details.installed_version); onClicked: controller.plan("install", JSON.stringify([page.details.name])) }
                                NxButton { text: "Remove"; variant: "danger"; visible: !!(page.details && !!page.details.installed_version && !page.details.essential); onClicked: controller.plan("remove", JSON.stringify([page.details.name])) }
                                NxButton { text: "Purge"; variant: "danger"; visible: !!(page.details && !!page.details.installed_version && !page.details.essential); onClicked: controller.plan("purge", JSON.stringify([page.details.name])) }
                                NxButton { text: "Upgrade"; visible: !!(page.details && page.details.installed_version && page.details.candidate_version !== page.details.installed_version); onClicked: controller.plan("install", JSON.stringify([page.details.name])) }
                            }
                            Text { visible: !!(page.details && page.details.essential); text: "Essential package: removal is not offered."; color: Theme.c.warning; font.family: Theme.fontFamily }
                            Text { text: page.details ? page.details.description : ""; wrapMode: Text.WordWrap; color: Theme.c.text; font.family: Theme.fontFamily; Layout.fillWidth: true }
                            NxSectionTitle { text: "Depends on" }
                            Text { text: page.details ? page.details.depends.join(", ") || "—" : ""; wrapMode: Text.WordWrap; color: Theme.c.textSecondary; font.family: Theme.monoFamily; font.pixelSize: Theme.fontSmall; Layout.fillWidth: true }
                            NxSectionTitle { text: "Recommends" }
                            Text { text: page.details ? page.details.recommends.join(", ") || "—" : ""; wrapMode: Text.WordWrap; color: Theme.c.textSecondary; font.family: Theme.monoFamily; font.pixelSize: Theme.fontSmall; Layout.fillWidth: true }
                            NxSectionTitle { text: "Installed packages that depend on it" }
                            Text { text: (d.rdeps || []).join(", ") || "—"; wrapMode: Text.WordWrap; color: Theme.c.textSecondary; font.family: Theme.monoFamily; font.pixelSize: Theme.fontSmall; Layout.fillWidth: true }
                            Text { visible: !!(page.details && !!page.details.homepage); text: page.details && page.details.homepage ? "<a href='" + page.details.homepage + "'>" + page.details.homepage + "</a>" : ""; onLinkActivated: link => Qt.openUrlExternally(link); color: Theme.c.accent; font.family: Theme.fontFamily }
                        }
                    }
                }
            }
            // ------------------------------------------------------ installed
            ColumnLayout {
                RowLayout {
                    CheckBox { id: appsOnly; text: "Applications only (packages with launchers)"; checked: true; onToggled: controller.loadInstalled(checked) }
                    Item { Layout.fillWidth: true }
                    Text { text: (d.installed || []).length + " packages"; color: Theme.c.textSecondary; font.family: Theme.fontFamily }
                }
                NxTable {
                    Layout.fillWidth: true; Layout.fillHeight: true
                    rows: d.installed || []
                    columns: [{ title: "Package", role: "name", width: 0.3 }, { title: "Version", role: "installed_version", width: 0.25, mono: true }, { title: "Summary", role: "summary", width: 0.45 }]
                    onActivated: row => { tabs.currentIndex = 0; controller.select(row.name) }
                }
            }
            // ------------------------------------------------------ updates
            ColumnLayout {
                RowLayout {
                    Text { text: d.updates ? d.updates.changes.length + " package(s) can be upgraded (from the current indexes)" : "Checking…"; color: Theme.c.text; font.family: Theme.fontFamily; Layout.fillWidth: true }
                    NxButton { text: "Upgrade all"; variant: "primary"; enabled: !!(d.agent && d.updates && d.updates.changes.length > 0 && !(d.op && d.op.running)); onClicked: controller.plan("upgrade", "[]") }
                }
                NxTable {
                    Layout.fillWidth: true; Layout.fillHeight: true
                    rows: d.updates ? d.updates.changes : []
                    emptyText: "System is up to date"
                    columns: [{ title: "Package", role: "name", width: 0.34 }, { title: "Installed", role: "old_version", width: 0.33, mono: true }, { title: "Candidate", role: "new_version", width: 0.33, mono: true }]
                }
            }
            // ------------------------------------------------------ history
            NxTable {
                rows: d.history || []
                emptyText: "No package history found in /var/log/apt"
                columns: [
                    { title: "Date", role: "start", width: 0.2 },
                    { title: "Command", width: 0.4, format: r => r.command || "" },
                    { title: "Changes", width: 0.4, format: r => [r.install.length ? "+" + r.install.length : "", r.upgrade.length ? "↑" + r.upgrade.length : "", r.remove.length ? "−" + r.remove.length : "", r.purge.length ? "purged " + r.purge.length : "", r.error ? "error" : ""].filter(Boolean).join("  ") }
                ]
            }
            // ------------------------------------------------------ repositories
            ColumnLayout {
                NxTable {
                    id: repoTable
                    Layout.fillWidth: true; Layout.fillHeight: true
                    rows: d.repos || []
                    columns: [
                        { title: "URI", width: 0.35, format: r => r.uris.join(" ") },
                        { title: "Suites", width: 0.25, format: r => r.suites.join(" ") },
                        { title: "Components", width: 0.2, format: r => r.components.join(" ") },
                        { title: "Managed", width: 0.2, format: r => (r.managed_by_nexusos ? "NexusOS" : "system") + (r.enabled ? "" : " (disabled)") }
                    ]
                }
                RowLayout {
                    NxButton { text: "Remove selected NexusOS repository"; variant: "danger"; enabled: !!(d.agent && repoTable.currentRow && repoTable.currentRow.managed_by_nexusos)
                        onClicked: { const n = repoTable.currentRow.file.split("/").pop().replace("nexusos-", "").replace(".sources", ""); confirm.ask("Remove repository", "Remove " + repoTable.currentRow.file + "?", [], "Remove", true, () => controller.removeRepository(n)) } }
                }
                NxSectionTitle { text: "Add a repository (signed, https)" }
                GridLayout {
                    columns: 6
                    Layout.fillWidth: true
                    NxTextField { id: rName; placeholderText: "name (a-z0-9-)" ; Layout.fillWidth: true }
                    NxTextField { id: rUri; placeholderText: "https://…"; Layout.fillWidth: true }
                    NxTextField { id: rSuites; placeholderText: "suites (e.g. resolute)"; Layout.fillWidth: true }
                    NxTextField { id: rComps; placeholderText: "components (e.g. main)"; Layout.fillWidth: true }
                    NxTextField { id: rKey; placeholderText: "/etc/apt/keyrings/<key>.gpg"; Layout.fillWidth: true }
                    NxButton { text: "Add"; enabled: d.agent; onClicked: confirm.ask("Add repository", "Packages from this repository will be trusted for installation.", ["URIs: " + rUri.text, "Suites: " + rSuites.text, "Components: " + rComps.text, "Signed-By: " + rKey.text], "Add repository", true,
                                                                       () => controller.addRepository(rName.text, rUri.text, rSuites.text, rComps.text, rKey.text)) }
                }
            }
        }
    }
}
