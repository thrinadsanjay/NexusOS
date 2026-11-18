import QtQuick
import QtQuick.Window
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Nexus.Design

// Nexus Command Center shell: sidebar navigation, header (search, notifications, theme),
// a single lazy page Loader, toasts and the global command palette (Ctrl+K).
ApplicationWindow {
    id: window
    // Default size follows the screen (the dashboard is designed for ≥ 1600×950; smaller windows scroll).
    width: Math.min(1680, Math.max(1100, Screen.desktopAvailableWidth * 0.9))
    height: Math.min(1000, Math.max(720, Screen.desktopAvailableHeight * 0.9))
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
    property var currentMeta: App.allModules.find(m => m.id === currentPage) || App.allModules[0]
    property var currentController: null

    // Used by `nexus-center --smoke --screenshots DIR` (review and documentation captures).
    function capture(path) { shellBackdrop.grabToImage(result => result.saveToFile(path)) }

    // Height a page needs: its implicitHeight, or that of its anchored layouts plus margins.
    // Pages with their own scroll area (scrollsItself: true) always fit the viewport.
    function neededHeight(item) {
        if (!item || item.scrollsItself) return 0
        if (item.implicitHeight > 0) return item.implicitHeight
        let h = 0
        for (let i = 0; i < item.children.length; i++) {
            const c = item.children[i]
            if (!c.visible || c.implicitHeight <= 0) continue
            h = Math.max(h, c.implicitHeight + c.anchors.topMargin + c.anchors.bottomMargin)
        }
        return Math.ceil(h)
    }

    function navigate(pageId, intent) {
        pendingIntent = intent || ""
        currentPage = pageId
    }

    onCurrentPageChanged: loadPage()
    Component.onCompleted: loadPage()

    function loadPage() {
        if (currentController) currentController.deactivate()
        const meta = App.allModules.find(m => m.id === currentPage)
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
        function onAuthRequested(request) { passwordPrompt.ask(request) }
        function onAuthPreviewClosed() { passwordPrompt.close() }
        function onNavigateRequested(page, intent) { window.navigate(page, intent) }
        function onNoticePanelRequested(shown) { shown ? noticePanel.open() : noticePanel.close() }
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
                            Text { text: "crafted by " + App.creator; color: Theme.c.accentSecondary; font.pixelSize: Theme.fontSmall; font.family: Theme.fontFamily; elide: Text.ElideRight; Layout.maximumWidth: Theme.sidebarWidth - 80 }
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
                            }
                            background: Rectangle { radius: Theme.radiusSmall; color: parent.highlighted ? Theme.c.backgroundSecondary : parent.hovered ? Theme.c.surfaceElevated : "transparent" }
                        }
                    }
                    // Who is signed in and what they may do (administrative tasks use their sudo rights).
                    Rectangle {
                        id: userChip
                        readonly property var acc: App.access || ({})
                        Layout.fillWidth: true
                        implicitHeight: 52
                        radius: Theme.radius
                        color: Theme.c.background
                        border.color: Theme.c.border
                        Accessible.name: "Signed in as " + (acc.user || "")
                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: Theme.s2
                            spacing: Theme.s2
                            Rectangle {
                                width: 32; height: 32; radius: 16
                                color: userChip.acc.admin === "none" ? Theme.c.border : Theme.c.accent
                                Text { anchors.centerIn: parent; text: (userChip.acc.user || "?").charAt(0).toUpperCase(); color: Theme.c.textOnAccent; font.family: Theme.fontFamily; font.weight: Font.Bold }
                            }
                            ColumnLayout {
                                spacing: 0
                                Layout.fillWidth: true
                                Text { text: userChip.acc.full_name || userChip.acc.user || ""; color: Theme.c.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; font.weight: Font.DemiBold; elide: Text.ElideRight; Layout.fillWidth: true }
                                Text {
                                    text: userChip.acc.admin === "root" ? "root"
                                        : userChip.acc.admin === "sudo" ? (userChip.acc.auth === "not-required" ? "Administrator · sudo, no password" : "Administrator · sudo")
                                        : "Standard user · no admin rights"
                                    color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall; elide: Text.ElideRight; Layout.fillWidth: true
                                }
                            }
                        }
                        ToolTip.visible: chipHover.hovered
                        ToolTip.text: (userChip.acc.reason || "") + (userChip.acc.admin === "none" ? "\nAdministrative actions are hidden or disabled." : "")
                        HoverHandler { id: chipHover }
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
                        spacing: Theme.s2
                        Text { text: "NexusOS  ›  " + (window.currentMeta ? window.currentMeta.title : ""); color: Theme.c.textSecondary; font.pixelSize: Theme.fontBody; font.family: Theme.fontFamily; Layout.fillWidth: true; elide: Text.ElideRight }
                        // Search box look-alike: opens the command palette.
                        Rectangle {
                            id: searchBox
                            Layout.preferredWidth: Math.min(300, Math.max(180, window.width * 0.2))
                            Layout.preferredHeight: Theme.controlHeight
                            radius: Theme.radiusSmall
                            color: searchHover.hovered ? Theme.c.surfaceElevated : Theme.c.surface
                            border.color: Theme.c.border
                            Accessible.role: Accessible.Button
                            Accessible.name: "Search (Ctrl+K)"
                            RowLayout {
                                anchors.fill: parent; anchors.leftMargin: Theme.s2; anchors.rightMargin: Theme.s2
                                spacing: Theme.s2
                                NxIcon { name: "search"; size: 15 }
                                Text { text: "Search…"; color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; Layout.fillWidth: true; elide: Text.ElideRight }
                                Rectangle {
                                    implicitWidth: kbd.implicitWidth + 10; implicitHeight: 20; radius: 4
                                    color: Theme.c.background; border.color: Theme.c.border
                                    Text { id: kbd; anchors.centerIn: parent; text: "Ctrl K"; color: Theme.c.textSecondary; font.family: Theme.monoFamily; font.pixelSize: Theme.fontSmall }
                                }
                            }
                            HoverHandler { id: searchHover; cursorShape: Qt.PointingHandCursor }
                            TapHandler { onTapped: commandPalette.openPalette() }
                        }
                        NxIconButton {
                            id: bell
                            iconName: "bell"
                            tip: App.unread > 0 ? App.unread + " unread notifications" : "Notifications"
                            badge: App.unread
                            active: noticePanel.visible
                            onClicked: noticePanel.visible ? noticePanel.close() : noticePanel.open()
                        }
                        NxIconButton {
                            iconName: Theme.dark ? "sun" : "moon"
                            tip: Theme.dark ? "Switch to the light theme" : "Switch to the dark theme"
                            onClicked: App.dark = !App.dark
                        }
                    }
                }
                // Pages scroll as a whole when the window is smaller than their content.
                Flickable {
                    id: pageFlick
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    clip: true
                    contentWidth: width
                    contentHeight: Math.max(height, window.neededHeight(pageLoader.item))
                    boundsBehavior: Flickable.StopAtBounds
                    interactive: contentHeight > height + 1
                    ScrollBar.vertical: ScrollBar { policy: pageFlick.interactive ? ScrollBar.AlwaysOn : ScrollBar.AlwaysOff }
                Loader {
                    id: pageLoader
                    property double startedAt: 0
                    width: pageFlick.width
                    height: pageFlick.contentHeight
                    asynchronous: false
                    onLoaded: {
                        pageFlick.contentY = 0
                        App.recordPageLoad(window.currentPage, Date.now() - startedAt)
                        if (window.currentController) window.currentController.activate()
                    }
                }
                }
            }
        }
    }

    NxConfirmDialog { id: confirmDialog; parent: Overlay.overlay }
    NxPasswordPrompt {
        id: passwordPrompt
        parent: shellBackdrop
        onSubmitted: password => App.submitPassword(password)
        onCancelled: App.cancelAuth()
    }

    // ------------------------------------------------------------ notification panel (bell)
    // A plain item (not a Popup) so --screenshots captures it like the rest of the shell.
    Item {
        id: noticePanel
        parent: shellBackdrop
        anchors.fill: parent
        visible: false
        z: 50
        function open() { App.refreshUnread(); visible = true }
        function close() { visible = false }
        MouseArea { anchors.fill: parent; onClicked: noticePanel.close() }   // click outside closes
        Shortcut { sequence: "Escape"; enabled: noticePanel.visible; onActivated: noticePanel.close() }
    Rectangle {
        x: parent.width - width - Theme.s4
        y: 50
        width: Math.min(400, parent.width - 40)
        height: Math.min(520, parent.height - 80)
        color: Theme.c.surfaceElevated
        radius: Theme.radius
        border.color: Theme.c.border
        MouseArea { anchors.fill: parent }   // keep clicks inside the panel
        ColumnLayout {
            anchors.fill: parent
            spacing: 0
            RowLayout {
                Layout.fillWidth: true
                Layout.margins: Theme.s3
                Text { text: "Notifications"; color: Theme.c.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontTitle; font.weight: Font.DemiBold; Layout.fillWidth: true }
                NxButton { text: "Clear all"; variant: "ghost"; visible: App.notices.length > 0; onClicked: App.dismissNotice(-1) }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.c.border }
            ListView {
                id: noticeList
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                model: App.notices
                ScrollBar.vertical: ScrollBar {}
                delegate: Item {
                    required property var modelData
                    width: noticeList.width
                    height: noticeRow.implicitHeight + Theme.s3 * 2
                    Rectangle { anchors.fill: parent; color: noticeHover.hovered ? Theme.c.surface : "transparent" }
                    HoverHandler { id: noticeHover }
                    RowLayout {
                        id: noticeRow
                        anchors.fill: parent; anchors.margins: Theme.s3
                        spacing: Theme.s2
                        Rectangle { Layout.alignment: Qt.AlignTop; Layout.topMargin: 5; width: 8; height: 8; radius: 4; color: Theme.statusColor(modelData.severity === "success" ? "ok" : modelData.severity) }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 2
                            Text { text: modelData.title + (modelData.count > 1 ? "  ×" + modelData.count : ""); color: Theme.c.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; font.weight: Font.DemiBold; wrapMode: Text.Wrap; Layout.fillWidth: true }
                            Text { text: modelData.body; visible: text.length > 0; color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall + 1; wrapMode: Text.Wrap; maximumLineCount: 3; elide: Text.ElideRight; Layout.fillWidth: true }
                            Text { text: new Date(modelData.ts * 1000).toLocaleString(Qt.locale(), Locale.ShortFormat) + "  ·  " + modelData.category; color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall }
                        }
                        NxIconButton { Layout.alignment: Qt.AlignTop; iconName: "cross"; iconSize: 15; implicitWidth: 26; implicitHeight: 26; tip: "Dismiss"; onClicked: App.dismissNotice(modelData.id) }
                    }
                }
                ColumnLayout {
                    anchors.centerIn: parent
                    visible: noticeList.count === 0
                    spacing: Theme.s2
                    NxIcon { Layout.alignment: Qt.AlignHCenter; name: "bell"; size: 28 }
                    Text { Layout.alignment: Qt.AlignHCenter; text: "You're all caught up"; color: Theme.c.text; font.family: Theme.fontFamily; font.weight: Font.DemiBold }
                    Text { Layout.alignment: Qt.AlignHCenter; text: "Updates, failures, certificate and disk alerts appear here."; color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall }
                }
            }
            Rectangle { Layout.fillWidth: true; height: 1; color: Theme.c.border }
            RowLayout {
                Layout.fillWidth: true
                Layout.margins: Theme.s2
                NxButton { text: "History and settings"; variant: "ghost"; iconName: "external"; onClicked: { noticePanel.close(); window.navigate("notifications") } }
                Item { Layout.fillWidth: true }
            }
        }
    }
    }

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
