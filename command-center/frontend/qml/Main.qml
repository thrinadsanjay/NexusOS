import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Nexus.Design

// Nexus Command Center shell: sidebar navigation, header (search, notifications, theme),
// a single lazy page Loader, toasts and the global command palette (Ctrl+K).
ApplicationWindow {
    id: window
    width: 1360
    height: 860
    minimumWidth: 960
    minimumHeight: 600
    visible: true
    title: "Nexus Command Center"
    color: Theme.c.background

    // Full palette from the design tokens: Basic-style controls, dialogs and popups must not
    // inherit the desktop's (KDE/Breeze or light Fusion) palette, or text becomes unreadable.
    palette {
        window: Theme.c.background
        windowText: Theme.c.text
        base: Theme.c.surface
        alternateBase: Theme.c.surfaceElevated
        text: Theme.c.text
        placeholderText: Theme.c.textSecondary
        button: Theme.c.surfaceElevated
        buttonText: Theme.c.text
        brightText: Theme.c.textOnAccent
        highlight: Theme.c.accent
        highlightedText: Theme.c.textOnAccent
        light: Theme.c.surfaceElevated
        midlight: Theme.c.surfaceElevated
        mid: Theme.c.border
        dark: Theme.c.border
        shadow: Theme.c.background
        toolTipBase: Theme.c.surfaceElevated
        toolTipText: Theme.c.text
        link: Theme.c.accent
        linkVisited: Theme.c.accentSecondary
        disabled.text: Theme.c.textSecondary
        disabled.windowText: Theme.c.textSecondary
        disabled.buttonText: Theme.c.textSecondary
    }

    property string currentPage: InitialPage
    property string pendingIntent: ""
    property var currentMeta: App.modules.find(m => m.id === currentPage) || App.modules[0]
    property var currentController: null

    // Used by `nexus-center --smoke --screenshots DIR` (review and documentation captures).
    function capture(path) { shellBackdrop.grabToImage(result => result.saveToFile(path)) }

    function navigate(pageId, intent) {
        pendingIntent = intent || ""
        currentPage = pageId
    }

    onCurrentPageChanged: loadPage()
    Component.onCompleted: loadPage()

    function loadPage() {
        if (currentController) currentController.deactivate()
        const meta = App.modules.find(m => m.id === currentPage)
        if (!meta) return
        pageLoader.startedAt = Date.now()
        currentController = App.controller(meta.id)
        pageLoader.setSource(meta.pageUrl, { controller: currentController, confirm: confirmDialog, intent: pendingIntent })
    }

    Shortcut { sequences: ["Ctrl+K", "Ctrl+Shift+P"]; onActivated: commandPalette.openPalette() }
    Shortcut { sequence: "Ctrl+Q"; onActivated: Qt.quit() }

    Connections {
        target: App
        function onToastRequested(kind, message) { toasts.show(kind, message) }
        function onNavigateRequested(page, intent) { window.navigate(page, intent) }
    }

    // Opaque backdrop so grabToImage captures (--screenshots) match what is on screen.
    Rectangle {
        id: shellBackdrop
        anchors.fill: parent
        color: Theme.c.background

        RowLayout {
            id: shell
            anchors.fill: parent
            spacing: 0

            // ------------------------------------------------------------ sidebar
            Rectangle {
                Layout.fillHeight: true
                Layout.preferredWidth: Theme.sidebarWidth
                color: Theme.c.surface
                Rectangle { anchors.right: parent.right; width: 1; height: parent.height; color: Theme.c.border }
                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: Theme.s3
                    spacing: Theme.s1
                    RowLayout {
                        Layout.bottomMargin: Theme.s3
                        spacing: Theme.s2
                        Image {
                            source: AppIconUrl
                            sourceSize.width: 28; sourceSize.height: 28
                        }
                        ColumnLayout {
                            spacing: 0
                            Text { text: "Command Center"; color: Theme.c.text; font.pixelSize: Theme.fontTitle; font.weight: Font.DemiBold; font.family: Theme.fontFamily }
                            Text { text: "NexusOS " + App.version; color: Theme.c.textSecondary; font.pixelSize: Theme.fontSmall; font.family: Theme.fontFamily }
                        }
                    }
                    ListView {
                        id: nav
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        model: App.modules
                        spacing: 2
                        clip: true
                        keyNavigationEnabled: true
                        delegate: ItemDelegate {
                            required property var modelData
                            width: nav.width
                            height: 34
                            highlighted: modelData.id === window.currentPage
                            Accessible.name: modelData.title
                            onClicked: window.navigate(modelData.id)
                            contentItem: RowLayout {
                                spacing: Theme.s2
                                Rectangle { Layout.preferredWidth: 3; Layout.preferredHeight: 18; radius: 1.5; color: parent.parent.highlighted ? Theme.c.accent : "transparent" }
                                Text { text: parent.parent.modelData.title; color: parent.parent.highlighted ? Theme.c.text : Theme.c.textSecondary; font.pixelSize: Theme.fontBody; font.family: Theme.fontFamily; Layout.fillWidth: true; elide: Text.ElideRight }
                                Rectangle {
                                    visible: !!(parent.parent.modelData.id === "notifications" && App.unread > 0)
                                    Layout.preferredHeight: 18; Layout.preferredWidth: Math.max(18, badge.implicitWidth + 8); radius: 9; color: Theme.c.accentSecondary
                                    Text { id: badge; anchors.centerIn: parent; text: App.unread; color: Theme.c.textOnAccent; font.pixelSize: Theme.fontSmall }
                                }
                            }
                            background: Rectangle { radius: Theme.radiusSmall; color: parent.highlighted ? Theme.c.backgroundSecondary : parent.hovered ? Theme.c.surfaceElevated : "transparent" }
                        }
                    }
                }
            }

            // ------------------------------------------------------------ main area
            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 0
                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 52
                    color: Theme.c.background
                    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.c.border }
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: Theme.s5
                        anchors.rightMargin: Theme.s4
                        Text { text: "NexusOS  ›  " + (window.currentMeta ? window.currentMeta.title : ""); color: Theme.c.textSecondary; font.pixelSize: Theme.fontBody; font.family: Theme.fontFamily; Layout.fillWidth: true }
                        NxButton { text: "Search…   Ctrl+K"; Layout.preferredWidth: 220; onClicked: commandPalette.openPalette() }
                        NxButton { text: App.unread > 0 ? "Notifications (" + App.unread + ")" : "Notifications"; variant: "ghost"; onClicked: window.navigate("notifications") }
                        NxButton { text: Theme.dark ? "Light theme" : "Dark theme"; variant: "ghost"; onClicked: App.dark = !App.dark }
                    }
                }
                Loader {
                    id: pageLoader
                    property double startedAt: 0
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    asynchronous: false
                    onLoaded: {
                        App.recordPageLoad(window.currentPage, Date.now() - startedAt)
                        if (window.currentController) window.currentController.activate()
                    }
                }
            }
        }
    }

    NxConfirmDialog { id: confirmDialog; parent: Overlay.overlay }

    // ------------------------------------------------------------ toasts
    Column {
        id: toasts
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: Theme.s4
        spacing: Theme.s2
        z: 100
        function show(kind, message) { toastModel.append({ kind: kind, message: message }); if (toastModel.count > 4) toastModel.remove(0) }
        Repeater {
            model: ListModel { id: toastModel }
            delegate: Rectangle {
                required property string kind
                required property string message
                required property int index
                width: 380
                height: msg.implicitHeight + Theme.s3 * 2
                radius: Theme.radiusSmall
                color: Theme.c.surfaceElevated
                border.color: Theme.statusColor(kind)
                Text { id: msg; anchors.fill: parent; anchors.margins: Theme.s3; text: message; wrapMode: Text.WordWrap; color: Theme.c.text; font.pixelSize: Theme.fontBody; font.family: Theme.fontFamily }
                Timer { running: true; interval: 6000; onTriggered: if (index < toastModel.count) toastModel.remove(index) }
                TapHandler { onTapped: toastModel.remove(index) }
            }
        }
    }

    // ------------------------------------------------------------ command palette
    Popup {
        id: commandPalette
        modal: true
        x: (window.width - width) / 2
        y: 80
        width: Math.min(720, window.width - 80)
        height: 460
        padding: Theme.s3
        background: Rectangle { color: Theme.c.surfaceElevated; radius: Theme.radius; border.color: Theme.c.border }
        function openPalette() { query.text = ""; App.search(""); open(); query.forceActiveFocus() }
        function choose(r) {
            if (!r) return
            close()
            if (r.kind === "page") window.navigate(r.target)
            else if (r.kind === "setting") { if (r.target.startsWith("native:")) window.navigate("settings", r.target); else App.openSetting(r.target) }
            else if (r.kind === "package") window.navigate("packages", "details:" + r.target)
            else if (r.kind === "ssh") window.navigate("terminal", "profile:" + r.target)
            else if (r.kind === "app") window.navigate("applications", "app:" + r.target)
            else if (r.kind === "route") window.navigate("gateway", "route:" + r.target)
            else if (r.kind === "file") window.navigate("files", "file:" + r.target)
            else if (r.kind === "action") {
                if (r.requiresConfirmation || r.requires_confirmation)
                    confirmDialog.ask(r.title, "This is an administrative action. Run it now?", [r.target], "Run", true, () => App.runAction(r.target))
                else App.runAction(r.target)
            }
        }
        ColumnLayout {
            anchors.fill: parent
            spacing: Theme.s2
            NxTextField {
                id: query
                Layout.fillWidth: true
                placeholderText: "Search settings, software, SSH hosts, containers, apps, files and actions"
                onTextChanged: { App.search(text); results.currentIndex = 0 }
                Keys.onDownPressed: results.incrementCurrentIndex()
                Keys.onUpPressed: results.decrementCurrentIndex()
                Keys.onReturnPressed: commandPalette.choose(App.searchResults[results.currentIndex])
                Keys.onEscapePressed: commandPalette.close()
            }
            ListView {
                id: results
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                model: App.searchResults
                delegate: ItemDelegate {
                    required property var modelData
                    required property int index
                    width: results.width
                    highlighted: index === results.currentIndex
                    onClicked: commandPalette.choose(modelData)
                    contentItem: RowLayout {
                        Text { text: parent.parent.modelData.kind; color: Theme.c.accent; font.pixelSize: Theme.fontSmall; font.family: Theme.monoFamily; Layout.preferredWidth: 70 }
                        Text { text: parent.parent.modelData.title; color: Theme.c.text; font.pixelSize: Theme.fontBody; font.family: Theme.fontFamily; Layout.preferredWidth: 240; elide: Text.ElideRight }
                        Text { text: parent.parent.modelData.subtitle; color: Theme.c.textSecondary; font.pixelSize: Theme.fontSmall; font.family: Theme.fontFamily; Layout.fillWidth: true; elide: Text.ElideRight }
                    }
                    background: Rectangle { radius: Theme.radiusSmall; color: parent.highlighted ? Theme.c.backgroundSecondary : "transparent" }
                }
                Text { anchors.centerIn: parent; visible: results.count === 0; text: query.text.length < 2 ? "Type at least two characters" : "No results"; color: Theme.c.textSecondary; font.family: Theme.fontFamily }
            }
            Text { text: "Actions never run on match: administrative ones ask for confirmation."; color: Theme.c.textSecondary; font.pixelSize: Theme.fontSmall; font.family: Theme.fontFamily }
        }
    }
}
