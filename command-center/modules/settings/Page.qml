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
    Component.onCompleted: { if (intent === "native:services") tabs.currentIndex = 2; else if (intent === "native:datetime" || intent === "native:hostname") tabs.currentIndex = 1 }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.s5
        spacing: Theme.s3
        NxPageHeader { title: "System Settings"; subtitle: "One entry point. Desktop settings open the mature KDE modules; system settings use polkit-protected system services." }
        NxErrorState { message: controller ? controller.error : ""; onRetry: controller.refresh() }
        NxTabBar { id: tabs; Layout.fillWidth: true; tabs: ["All settings", "System", "Services", "Users", "Command Center"]
            onCurrentIndexChanged: { if (currentIndex === 2) controller.loadUnits(); if (currentIndex === 1 && (d.timezones || []).length === 0) controller.loadTimezones() } }
        StackLayout {
            currentIndex: tabs.currentIndex
            Layout.fillWidth: true
            Layout.fillHeight: true

            ScrollView {
                contentWidth: availableWidth
                GridLayout {
                    width: parent.width
                    columns: Math.max(1, Math.floor(width / 420))
                    columnSpacing: Theme.s3
                    rowSpacing: Theme.s3
                    Repeater {
                        model: d.categories || []
                        NxCard {
                            required property var modelData
                            Layout.fillWidth: true
                            Layout.alignment: Qt.AlignTop
                            ColumnLayout {
                                width: parent.width
                                NxSectionTitle { text: modelData.name }
                                Repeater {
                                    model: modelData.entries
                                    RowLayout {
                                        required property var modelData
                                        Text { text: modelData.title; color: modelData.available ? Theme.c.text : Theme.c.textSecondary; font.family: Theme.fontFamily; Layout.fillWidth: true; elide: Text.ElideRight }
                                        Text { visible: !modelData.available; text: "needs " + (modelData.package || ""); color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall }
                                        NxButton { text: modelData.kcm ? "Open" : "Show"; variant: "ghost"; enabled: !!modelData.available
                                            onClicked: modelData.kcm ? controller.openKcm(modelData.kcm) : (tabs.currentIndex = modelData.native === "services" ? 2 : 1) }
                                    }
                                }
                            }
                        }
                    }
                }
            }
            ColumnLayout {
                spacing: Theme.s3
                NxFormRow { label: "Hostname"; RowLayout { width: parent.width; NxTextField { id: host; text: d.hostname || ""; Layout.fillWidth: true } NxButton { admin: true; text: "Apply"; onClicked: confirm.ask("Change hostname", "Set the hostname to '" + host.text + "'? Network names and SSH known_hosts entries elsewhere may need updating.", ["$ hostnamectl set-hostname " + host.text], "Change", false, () => controller.setHostname(host.text)) } } }
                NxFormRow { label: "Time zone"; RowLayout { width: parent.width; ComboBox { id: tz; model: d.timezones || []; Layout.fillWidth: true; currentIndex: (d.timezones || []).indexOf(d.time ? d.time.timezone : "") } NxButton { admin: true; text: "Apply"; onClicked: controller.setTimezone(tz.currentText) } } }
                NxFormRow { label: "Network time (NTP)"; Switch { enabled: App.canAdmin; checked: d.time ? !!d.time.ntp_enabled : false; onToggled: controller.setNtp(checked) } }
                NxFormRow { label: "Clock synchronised"; Text { text: d.time ? (d.time.ntp_synchronized ? "yes" : "no") : "unknown"; color: Theme.c.text; font.family: Theme.fontFamily } }
                NxFormRow { label: "Locale"; Text { text: d.locale ? (d.locale["System Locale"] || "") : ""; color: Theme.c.text; font.family: Theme.fontFamily } }
                NxButton { text: "Language and region…"; onClicked: controller.openKcm("kcm_regionandlang") }
                Item { Layout.fillHeight: true }
            }
            ColumnLayout {
                RowLayout {
                    NxTextField { id: unitFilter; placeholderText: "Filter services"; Layout.fillWidth: true }
                    CheckBox { id: approvedOnly; text: "Manageable only"; checked: true }
                }
                NxTable {
                    id: unitTable
                    Layout.fillWidth: true; Layout.fillHeight: true
                    rows: (d.units || []).filter(u => (!approvedOnly.checked || u.approved) && u.name.indexOf(unitFilter.text) >= 0)
                    columns: [{ title: "Unit", role: "name", width: 0.3 }, { title: "Active", role: "active", width: 0.12 }, { title: "Sub", role: "sub", width: 0.12 }, { title: "Description", role: "description", width: 0.46 }]
                }
                RowLayout {
                    enabled: !!unitTable.currentRow
                    Repeater {
                        model: ["start", "stop", "restart", "enable", "disable"]
                        NxButton { admin: true; required property string modelData; text: modelData; enabled: !!(unitTable.currentRow && unitTable.currentRow.approved)
                            onClicked: confirm.ask(modelData + " " + unitTable.currentRow.name, "systemd will ask for administrator authentication.", ["$ systemctl " + modelData + " " + unitTable.currentRow.name], modelData, modelData === "stop" || modelData === "disable", () => controller.control(unitTable.currentRow.name, modelData)) }
                    }
                    NxButton { text: "Logs"; onClicked: controller.loadLogs(unitTable.currentRow.name) }
                }
                NxLogView { text: d.logs || ""; Layout.fillWidth: true; Layout.preferredHeight: 180 }
            }
            ColumnLayout {
                NxTable {
                    Layout.fillWidth: true; Layout.fillHeight: true
                    rows: d.users || []
                    columns: [{ title: "User", role: "name", width: 0.2 }, { title: "Name", role: "full_name", width: 0.25 }, { title: "Administrator", width: 0.15, format: r => r.administrator ? "yes" : "no" }, { title: "Groups", width: 0.4, format: r => r.groups.join(", ") }]
                }
                NxButton { text: "Manage users and passwords…"; onClicked: controller.openKcm("kcm_users") }
            }
            ColumnLayout {
                NxFormRow { label: "Dark theme"; Switch { checked: App.dark; onToggled: App.dark = checked } }
                NxFormRow { label: "Monitoring interval"; RowLayout { SpinBox { from: 1; to: 60; value: Math.round(App.monitoringInterval / 1000); onValueModified: App.monitoringInterval = value * 1000 } Text { text: "seconds (only while a monitoring page is visible)"; color: Theme.c.textSecondary; font.family: Theme.fontFamily } } }
                Item { Layout.fillHeight: true }
            }
        }
    }
}
