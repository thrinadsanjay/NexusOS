import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Nexus.Design

// Files: an Explorer-style browser. Back/forward/up, a clickable breadcrumb (click the empty
// part to type a path), Quick access + This PC navigation, details or icon view with sortable
// columns, multi-select, context menu, inline rename (F2), cut/copy/paste through KIO, and a
// status bar. Deleting moves items to the trash. Dolphin remains one click away.
Item {
    id: page
    objectName: "filesPage"
    property var controller
    property var confirm
    property string intent: ""
    readonly property var d: controller ? controller.data : ({})
    readonly property var smokeStates: ["icons", "menu"]

    // ------------------------------------------------------------------ state
    property var history: []
    property int historyIndex: -1
    property var selected: ({})          // path -> true
    property int anchorRow: -1
    property string viewMode: "details"  // "details" | "icons"
    property string sortKey: "name"
    property bool sortAscending: true
    property string renaming: ""
    property string filter: ""
    property bool editingPath: false

    readonly property string path: d.path || ""
    readonly property var clip: d.clipboard || ({ paths: [], cut: false })
    readonly property bool searching: (d.results || []).length > 0
    readonly property var rows: {
        let list = searching ? d.results.map(p => ({ name: p.split("/").pop(), path: p, is_dir: false, size: 0, mtime: 0, mode: "", hidden: false }))
                             : (d.entries || [])
        if (filter.length > 0) {
            const f = filter.toLowerCase()
            list = list.filter(e => e.name.toLowerCase().indexOf(f) >= 0)
        }
        const dir = sortAscending ? 1 : -1
        const key = sortKey
        return list.slice().sort((a, b) => {
            if (a.is_dir !== b.is_dir) return a.is_dir ? -1 : 1
            let r = 0
            if (key === "size") r = a.size - b.size
            else if (key === "mtime") r = a.mtime - b.mtime
            else if (key === "type") r = page.kind(a).label.localeCompare(page.kind(b).label)
            if (r === 0) r = a.name.toLowerCase().localeCompare(b.name.toLowerCase())
            return r * dir
        })
    }
    readonly property var selectedPaths: Object.keys(selected).filter(p => selected[p])
    readonly property var selectedRows: rows.filter(r => selected[r.path])
    readonly property var single: selectedRows.length === 1 ? selectedRows[0] : null

    // ------------------------------------------------------------------ helpers
    readonly property var kinds: ({
        image: ["png", "jpg", "jpeg", "gif", "webp", "svg", "bmp", "tiff", "ico", "heic"],
        video: ["mp4", "mkv", "webm", "avi", "mov", "m4v"],
        music: ["mp3", "flac", "ogg", "wav", "m4a", "opus", "aac"],
        archive: ["zip", "tar", "gz", "tgz", "xz", "bz2", "7z", "zst", "rar", "deb", "iso"],
        code: ["py", "js", "ts", "qml", "c", "h", "cpp", "rs", "go", "sh", "json", "yaml", "yml", "toml", "html", "css", "xml", "java", "kt"],
        doc: ["txt", "md", "pdf", "odt", "doc", "docx", "rtf", "ods", "xls", "xlsx", "odp", "ppt", "pptx", "csv", "log"]
    })
    function kind(e) {
        if (e.is_dir) return { icon: "folder", color: Theme.c.mDisk, label: "File folder" }
        const ext = e.name.indexOf(".") > 0 ? e.name.split(".").pop().toLowerCase() : ""
        const colors = { image: Theme.c.mGpu, video: Theme.c.mVuln, music: Theme.c.mUpdates, archive: Theme.c.mMounts, code: Theme.c.mCpu, doc: Theme.c.mNetwork }
        for (const k in kinds) if (kinds[k].indexOf(ext) >= 0) return { icon: k, color: colors[k], label: ext.toUpperCase() + " " + (k === "doc" ? "document" : k === "code" ? "source" : k) }
        return { icon: "file", color: Theme.c.textSecondary, label: ext ? ext.toUpperCase() + " file" : "File" }
    }
    function when(ts) { return ts ? new Date(ts * 1000).toLocaleString(Qt.locale(), Locale.ShortFormat) : "" }
    function home() { return (d.quick && d.quick.length) ? d.quick[0].path : "" }
    function crumbs() {
        const h = home()
        let rest = path, out = []
        if (h && (path === h || path.startsWith(h + "/"))) { out.push({ title: "Home", path: h }); rest = path.slice(h.length) }
        else out.push({ title: "This PC", path: "/" })
        let acc = out[0].path === "/" ? "" : out[0].path
        for (const part of rest.split("/").filter(x => x)) { acc += "/" + part; out.push({ title: part, path: acc }) }
        return out
    }

    function go(target, remember) {
        if (!target || !controller) return
        if (remember !== false) {
            const h = history.slice(0, historyIndex + 1); h.push(target)
            history = h; historyIndex = h.length - 1
        }
        selected = ({}); anchorRow = -1; renaming = ""; filter = ""; searchField.text = ""
        controller.open(target)
    }
    function back() { if (historyIndex > 0) { historyIndex--; go(history[historyIndex], false) } }
    function forward() { if (historyIndex < history.length - 1) { historyIndex++; go(history[historyIndex], false) } }
    function up() { if (path !== "/") go(path.replace(/\/[^\/]+\/?$/, "") || "/") }
    function activate(row) { row.is_dir ? go(row.path) : controller.openFile(row.path) }

    function select(index, modifiers) {
        const row = rows[index]
        if (!row) return
        let s = Object.assign({}, selected)
        if (modifiers & Qt.ShiftModifier && anchorRow >= 0) {
            if (!(modifiers & Qt.ControlModifier)) s = {}
            const a = Math.min(anchorRow, index), b = Math.max(anchorRow, index)
            for (let i = a; i <= b; i++) s[rows[i].path] = true
        } else if (modifiers & Qt.ControlModifier) {
            s[row.path] = !s[row.path]; anchorRow = index
        } else {
            s = {}; s[row.path] = true; anchorRow = index
        }
        selected = s
    }
    function selectAll() { let s = {}; rows.forEach(r => s[r.path] = true); selected = s }
    function copySel(cut) { if (selectedPaths.length) controller.setClipboard(selectedPaths, cut) }
    function trashSel() {
        if (!selectedPaths.length) return
        const n = selectedPaths.length
        confirm.ask(n === 1 ? "Move to trash" : "Move " + n + " items to trash", "You can restore them from the trash in Dolphin.",
                    selectedPaths.slice(0, 6), "Move to trash", true, () => { controller.trash(page.selectedPaths); page.selected = ({}) })
    }
    function startRename() { if (single) renaming = single.path }

    function applySmokeState(name) {
        viewMode = name === "icons" ? "icons" : "details"
        if (name === "menu" && rows.length) { select(0, 0); contextMenu.popup(detailsView, 220, 90) }
        else contextMenu.close()
    }

    Component.onCompleted: {
        if (intent.startsWith("file:")) Qt.callLater(() => go(intent.slice(5).replace(/\/[^\/]*$/, "")))
        else Qt.callLater(() => { history = [path]; historyIndex = 0 })
    }
    // A folder created with "New folder" is selected and opened for renaming, as in Explorer.
    property string lastCreated: ""
    Connections {
        target: page.controller
        function onDataChanged() {
            const p = page.d.created || ""
            if (p && p !== page.lastCreated) { page.lastCreated = p; page.selected = ({ [p]: true }); page.renaming = p }
        }
    }

    // keyboard (when no text field has focus)
    Shortcut { sequences: ["Alt+Left", "Backspace"]; enabled: page.visible && !page.renaming && !pathField.activeFocus && !searchField.activeFocus; onActivated: page.back() }
    Shortcut { sequence: "Alt+Right"; enabled: page.visible; onActivated: page.forward() }
    Shortcut { sequence: "Alt+Up"; enabled: page.visible; onActivated: page.up() }
    Shortcut { sequence: "F2"; enabled: page.visible && !!page.single; onActivated: page.startRename() }
    Shortcut { sequence: "F5"; enabled: page.visible; onActivated: page.controller.reload() }
    Shortcut { sequence: "Delete"; enabled: page.visible && !page.renaming && !pathField.activeFocus && !searchField.activeFocus; onActivated: page.trashSel() }
    Shortcut { sequence: "Ctrl+A"; enabled: page.visible && !pathField.activeFocus && !searchField.activeFocus; onActivated: page.selectAll() }
    Shortcut { sequence: "Ctrl+C"; enabled: page.visible && !page.renaming && !pathField.activeFocus && !searchField.activeFocus; onActivated: page.copySel(false) }
    Shortcut { sequence: "Ctrl+X"; enabled: page.visible && !page.renaming && !pathField.activeFocus && !searchField.activeFocus; onActivated: page.copySel(true) }
    Shortcut { sequence: "Ctrl+V"; enabled: page.visible && !page.renaming && !pathField.activeFocus && !searchField.activeFocus; onActivated: page.controller.paste() }
    Shortcut { sequence: "Ctrl+Shift+N"; enabled: page.visible; onActivated: page.controller.newFolder() }
    Shortcut { sequence: "Ctrl+L"; enabled: page.visible; onActivated: { page.editingPath = true; pathField.forceActiveFocus(); pathField.selectAll() } }

    // ------------------------------------------------------------------ building blocks
    component Sep: Rectangle { Layout.preferredWidth: 1; Layout.preferredHeight: 22; color: Theme.c.border }
    component NavItem: Rectangle {
        id: nav
        property string title
        property string target
        property string iconName: "folder"
        property real fill: -1          // drive usage 0..1, -1 = none
        property string detail
        Layout.fillWidth: true
        implicitHeight: fill >= 0 ? 48 : 30
        radius: Theme.radiusSmall
        readonly property bool current: page.path === target
        color: current ? Theme.c.backgroundSecondary : navHover.hovered ? Theme.c.surfaceElevated : "transparent"
        HoverHandler { id: navHover; cursorShape: Qt.PointingHandCursor }
        TapHandler { onTapped: page.go(nav.target) }
        Accessible.role: Accessible.Button
        Accessible.name: title
        ColumnLayout {
            anchors.fill: parent; anchors.leftMargin: Theme.s2; anchors.rightMargin: Theme.s2
            spacing: 3
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.s2
                NxIcon { name: nav.iconName; size: 16; color: nav.current ? Theme.c.accent : Theme.c.textSecondary }
                Text { text: nav.title; color: nav.current ? Theme.c.text : Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; elide: Text.ElideRight; Layout.fillWidth: true }
            }
            Rectangle {
                visible: nav.fill >= 0
                Layout.fillWidth: true; Layout.leftMargin: 24; implicitHeight: 4; radius: 2; color: Theme.c.border
                Rectangle { width: parent.width * Math.max(0, Math.min(1, nav.fill)); height: parent.height; radius: 2; color: nav.fill > 0.9 ? Theme.c.negative : Theme.c.accent }
            }
            Text { visible: nav.detail.length > 0; Layout.leftMargin: 24; text: nav.detail; color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall; elide: Text.ElideRight; Layout.fillWidth: true }
        }
    }
    component NavHeader: Text {
        Layout.topMargin: Theme.s2
        Layout.leftMargin: Theme.s2
        color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall; font.weight: Font.DemiBold; font.capitalization: Font.AllUppercase
    }
    component HeaderCell: Rectangle {
        id: hc
        property string title
        property string key
        property bool alignEnd: false
        color: hcHover.hovered ? Theme.c.surfaceElevated : "transparent"
        implicitHeight: 30
        HoverHandler { id: hcHover; cursorShape: Qt.PointingHandCursor }
        TapHandler { onTapped: { if (page.sortKey === hc.key) page.sortAscending = !page.sortAscending; else { page.sortKey = hc.key; page.sortAscending = true } } }
        RowLayout {
            anchors.fill: parent; anchors.leftMargin: Theme.s2; anchors.rightMargin: Theme.s2
            spacing: 4
            Item { Layout.fillWidth: hc.alignEnd }
            Text { text: hc.title; color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall + 1; font.weight: Font.DemiBold; elide: Text.ElideRight }
            Text { visible: page.sortKey === hc.key; text: page.sortAscending ? "▲" : "▼"; color: Theme.c.accent; font.pixelSize: 8 }
            Item { Layout.fillWidth: !hc.alignEnd }
        }
        Rectangle { anchors.right: parent.right; width: 1; height: parent.height - 10; anchors.verticalCenter: parent.verticalCenter; color: Theme.c.border }
    }

    // ------------------------------------------------------------------ layout
    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.s4
        spacing: Theme.s2

        // navigation bar: back · forward · up · refresh · breadcrumb / path · search
        RowLayout {
            Layout.fillWidth: true
            spacing: 2
            NxIconButton { iconName: "back"; tip: "Back (Alt+Left)"; enabled: page.historyIndex > 0; onClicked: page.back() }
            NxIconButton { iconName: "forward"; tip: "Forward (Alt+Right)"; enabled: page.historyIndex < page.history.length - 1; onClicked: page.forward() }
            NxIconButton { iconName: "up"; tip: "Up to the parent folder (Alt+Up)"; enabled: page.path !== "/"; onClicked: page.up() }
            NxIconButton { iconName: "refresh"; tip: "Refresh (F5)"; onClicked: page.controller.reload() }
            Rectangle {
                Layout.fillWidth: true
                Layout.leftMargin: Theme.s2
                implicitHeight: Theme.controlHeight
                radius: Theme.radiusSmall
                color: Theme.c.surface
                border.color: pathField.activeFocus ? Theme.c.accent : Theme.c.border
                TapHandler { enabled: !page.editingPath; onTapped: { page.editingPath = true; pathField.forceActiveFocus(); pathField.selectAll() } }
                Row {
                    visible: !page.editingPath
                    anchors.verticalCenter: parent.verticalCenter
                    x: Theme.s2
                    width: parent.width - Theme.s4
                    clip: true
                    spacing: 0
                    NxIcon { name: page.crumbs()[0].title === "Home" ? "home" : "desktop"; size: 15; anchors.verticalCenter: parent.verticalCenter }
                    Repeater {
                        model: page.crumbs()
                        Row {
                            required property var modelData
                            required property int index
                            anchors.verticalCenter: parent.verticalCenter
                            Text { visible: index > 0; text: "  ›  "; color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; anchors.verticalCenter: parent.verticalCenter }
                            Rectangle {
                                width: crumb.implicitWidth + 10; height: 24; radius: 4
                                anchors.verticalCenter: parent.verticalCenter
                                color: crumbHover.hovered ? Theme.c.surfaceElevated : "transparent"
                                Text { id: crumb; anchors.centerIn: parent; text: modelData.title; color: Theme.c.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody }
                                HoverHandler { id: crumbHover; cursorShape: Qt.PointingHandCursor }
                                TapHandler { onTapped: page.go(modelData.path) }
                            }
                        }
                    }
                }
                TextField {
                    id: pathField
                    visible: page.editingPath
                    anchors.fill: parent
                    text: page.path
                    color: Theme.c.text
                    font.family: Theme.monoFamily
                    font.pixelSize: Theme.fontBody
                    background: null
                    leftPadding: Theme.s2
                    onAccepted: { page.editingPath = false; page.go(text) }
                    onActiveFocusChanged: if (!activeFocus) page.editingPath = false
                    Keys.onEscapePressed: { page.editingPath = false; text = page.path }
                }
            }
            Rectangle {
                Layout.preferredWidth: Math.max(160, Math.min(260, page.width * 0.22))
                Layout.leftMargin: Theme.s2
                implicitHeight: Theme.controlHeight
                radius: Theme.radiusSmall
                color: Theme.c.surface
                border.color: searchField.activeFocus ? Theme.c.accent : Theme.c.border
                RowLayout {
                    anchors.fill: parent; anchors.leftMargin: Theme.s2; anchors.rightMargin: 4
                    spacing: 4
                    NxIcon { name: "search"; size: 15 }
                    TextField {
                        id: searchField
                        Layout.fillWidth: true
                        placeholderText: "Search " + (page.crumbs().slice(-1)[0] || { title: "" }).title
                        placeholderTextColor: Theme.c.textSecondary
                        color: Theme.c.text
                        font.family: Theme.fontFamily
                        font.pixelSize: Theme.fontBody
                        background: null
                        onTextChanged: { page.filter = text; if (!text && page.searching) page.controller.open(page.path) }
                        onAccepted: if (text.length > 1) page.controller.search(text)   // Enter: search everywhere (Baloo)
                        ToolTip.visible: activeFocus && text.length > 1
                        ToolTip.text: "Filtering this folder · Enter searches all indexed files"
                    }
                }
            }
        }

        // command bar
        Rectangle {
            Layout.fillWidth: true
            implicitHeight: 44
            radius: Theme.radius
            color: Theme.c.surface
            border.color: Theme.c.border
            RowLayout {
                anchors.fill: parent; anchors.leftMargin: Theme.s2; anchors.rightMargin: Theme.s2
                spacing: 2
                NxButton { iconName: "newfolder"; text: page.width > 900 ? "New folder" : ""; variant: "ghost"; onClicked: page.controller.newFolder(); ToolTip.visible: hovered; ToolTip.text: "New folder (Ctrl+Shift+N)" }
                Sep { Layout.leftMargin: 4; Layout.rightMargin: 4 }
                NxIconButton { iconName: "cut"; tip: "Cut (Ctrl+X)"; enabled: page.selectedPaths.length > 0; onClicked: page.copySel(true) }
                NxIconButton { iconName: "copy"; tip: "Copy (Ctrl+C)"; enabled: page.selectedPaths.length > 0; onClicked: page.copySel(false) }
                NxIconButton { iconName: "paste"; tip: page.clip.paths.length ? "Paste " + page.clip.paths.length + " item(s) here (Ctrl+V)" : "Paste (Ctrl+V)"; enabled: page.clip.paths.length > 0 && !page.searching; onClicked: page.controller.paste() }
                NxIconButton { iconName: "rename"; tip: "Rename (F2)"; enabled: !!page.single; onClicked: page.startRename() }
                NxIconButton { iconName: "trash"; tip: "Move to trash (Delete)"; enabled: page.selectedPaths.length > 0; onClicked: page.trashSel() }
                Sep { Layout.leftMargin: 4; Layout.rightMargin: 4 }
                NxButton {
                    iconName: "archive"; variant: "ghost"
                    readonly property bool isArchive: !!page.single && !page.single.is_dir && page.kind(page.single).icon === "archive"
                    text: page.width > 1000 ? (isArchive ? "Extract here" : "Compress") : ""
                    enabled: page.selectedPaths.length > 0
                    onClicked: isArchive ? page.controller.extract(page.single.path) : page.controller.compress(page.selectedPaths)
                    ToolTip.visible: hovered; ToolTip.text: isArchive ? "Extract here (Ark)" : "Compress to .tar.gz (Ark)"
                }
                Item { Layout.fillWidth: true }
                NxIconButton { iconName: "eye"; tip: page.d.hidden ? "Hide hidden files" : "Show hidden files"; active: !!page.d.hidden; onClicked: page.controller.setHidden(!page.d.hidden) }
                NxIconButton { iconName: "list"; tip: "Details"; active: page.viewMode === "details"; onClicked: page.viewMode = "details" }
                NxIconButton { iconName: "grid"; tip: "Large icons"; active: page.viewMode === "icons"; onClicked: page.viewMode = "icons" }
                Sep { Layout.leftMargin: 4; Layout.rightMargin: 4 }
                NxButton { iconName: "external"; text: page.width > 1000 ? "Open in Dolphin" : ""; variant: "ghost"; onClicked: page.controller.openInDolphin(page.path); ToolTip.visible: hovered; ToolTip.text: "Tabs, network places, properties and permissions" }
            }
        }

        NxErrorState { Layout.fillWidth: true; message: page.controller ? page.controller.error : ""; onRetry: page.controller.reload() }

        // navigation pane + content
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: Theme.s2

            Rectangle {
                Layout.preferredWidth: page.width > 900 ? 210 : 170
                Layout.fillHeight: true
                radius: Theme.radius
                color: Theme.c.surface
                border.color: Theme.c.border
                Flickable {
                    anchors.fill: parent
                    anchors.margins: Theme.s2
                    contentHeight: navColumn.implicitHeight
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: ScrollBar {}
                    ColumnLayout {
                        id: navColumn
                        width: parent.width
                        spacing: 1
                        NavHeader { text: "Quick access" }
                        Repeater { model: page.d.quick || []; NavItem { required property var modelData; title: modelData.title; target: modelData.path; iconName: modelData.icon } }
                        NavHeader { text: "Bookmarks"; visible: bookmarks.count > 0 }
                        Repeater {
                            id: bookmarks
                            model: (page.d.places || []).filter(p => p.url.startsWith("/") || p.url.startsWith("file://"))
                                .map(p => ({ title: p.title, path: decodeURIComponent(p.url.replace("file://", "")) }))
                                .filter(p => !(page.d.quick || []).some(q => q.path === p.path.replace(/\/$/, "")))
                            NavItem { required property var modelData; title: modelData.title; target: modelData.path; iconName: "star" }
                        }
                        NavHeader { text: "This PC" }
                        NavItem { title: "File system"; target: "/"; iconName: "desktop" }
                        Repeater {
                            model: (page.d.drives || []).filter(x => x.mount !== "/" && !x.mount.startsWith("/boot") && !x.mount.startsWith("/snap"))
                            NavItem {
                                required property var modelData
                                title: modelData.mount.split("/").pop() || modelData.mount
                                target: modelData.mount
                                iconName: "disk"
                                fill: modelData.size ? modelData.used / modelData.size : -1
                                detail: Theme.bytes(modelData.available) + " free of " + Theme.bytes(modelData.size)
                            }
                        }
                    }
                }
            }

            // content
            Rectangle {
                id: content
                Layout.fillWidth: true
                Layout.fillHeight: true
                radius: Theme.radius
                color: Theme.c.surface
                border.color: Theme.c.border
                clip: true

                // empty area: clear selection / context menu for the folder
                MouseArea {
                    anchors.fill: parent
                    acceptedButtons: Qt.LeftButton | Qt.RightButton
                    onClicked: mouse => { page.selected = ({}); page.renaming = ""; if (mouse.button === Qt.RightButton) contextMenu.popup() }
                }

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 1
                    spacing: 0
                    visible: page.viewMode === "details"
                    Row {
                        id: header
                        Layout.fillWidth: true
                        readonly property real w: content.width - 2
                        HeaderCell { title: "Name"; key: "name"; width: header.w * 0.46 }
                        HeaderCell { title: "Date modified"; key: "mtime"; width: header.w * 0.22 }
                        HeaderCell { title: "Type"; key: "type"; width: header.w * 0.18 }
                        HeaderCell { title: "Size"; key: "size"; alignEnd: true; width: header.w * 0.14 }
                    }
                    Rectangle { Layout.fillWidth: true; implicitHeight: 1; color: Theme.c.border }
                    ListView {
                        id: detailsView
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        model: page.rows
                        boundsBehavior: Flickable.StopAtBounds
                        ScrollBar.vertical: ScrollBar {}
                        delegate: Rectangle {
                            id: rowItem
                            required property var modelData
                            required property int index
                            readonly property bool sel: !!page.selected[modelData.path]
                            readonly property var k: page.kind(modelData)
                            width: detailsView.width
                            height: 32
                            color: sel ? Qt.rgba(Theme.c.accent.r, Theme.c.accent.g, Theme.c.accent.b, 0.18) : rowHover.hovered ? Theme.c.surfaceElevated : "transparent"
                            opacity: page.clip.cut && page.clip.paths.indexOf(modelData.path) >= 0 ? 0.5 : 1
                            HoverHandler { id: rowHover }
                            MouseArea {
                                anchors.fill: parent
                                acceptedButtons: Qt.LeftButton | Qt.RightButton
                                onClicked: mouse => {
                                    if (mouse.button === Qt.RightButton && !rowItem.sel) page.select(rowItem.index, 0)
                                    else if (mouse.button === Qt.LeftButton) page.select(rowItem.index, mouse.modifiers)
                                    if (mouse.button === Qt.RightButton) contextMenu.popup()
                                }
                                onDoubleClicked: page.activate(rowItem.modelData)
                            }
                            Row {
                                anchors.fill: parent
                                Item {
                                    width: header.w * 0.46; height: parent.height
                                    NxIcon { id: rowIcon; x: Theme.s2; anchors.verticalCenter: parent.verticalCenter; name: rowItem.k.icon; color: rowItem.k.color; size: 17 }
                                    Text {
                                        visible: page.renaming !== rowItem.modelData.path
                                        anchors { left: rowIcon.right; leftMargin: Theme.s2; right: parent.right; rightMargin: Theme.s2; verticalCenter: parent.verticalCenter }
                                        text: rowItem.modelData.name
                                        color: rowItem.modelData.hidden ? Theme.c.textSecondary : Theme.c.text
                                        font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody
                                        elide: Text.ElideMiddle
                                    }
                                    TextField {
                                        visible: page.renaming === rowItem.modelData.path
                                        anchors { left: rowIcon.right; leftMargin: Theme.s2; right: parent.right; rightMargin: Theme.s2; verticalCenter: parent.verticalCenter }
                                        height: 26
                                        text: rowItem.modelData.name
                                        color: Theme.c.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody
                                        background: Rectangle { color: Theme.c.background; border.color: Theme.c.accent; radius: 3 }
                                        onVisibleChanged: if (visible) { forceActiveFocus(); const dot = text.lastIndexOf("."); select(0, rowItem.modelData.is_dir || dot <= 0 ? text.length : dot) }
                                        onAccepted: { if (text !== rowItem.modelData.name) page.controller.rename(rowItem.modelData.path, text); page.renaming = "" }
                                        Keys.onEscapePressed: page.renaming = ""
                                        onActiveFocusChanged: if (!activeFocus && page.renaming === rowItem.modelData.path) page.renaming = ""
                                    }
                                }
                                Text { width: header.w * 0.22; height: parent.height; verticalAlignment: Text.AlignVCenter; leftPadding: Theme.s2; text: page.when(rowItem.modelData.mtime); color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall + 1; elide: Text.ElideRight }
                                Text { width: header.w * 0.18; height: parent.height; verticalAlignment: Text.AlignVCenter; leftPadding: Theme.s2; text: rowItem.k.label; color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall + 1; elide: Text.ElideRight }
                                Text { width: header.w * 0.14; height: parent.height; verticalAlignment: Text.AlignVCenter; rightPadding: Theme.s3; horizontalAlignment: Text.AlignRight; text: rowItem.modelData.is_dir ? "" : Theme.bytes(rowItem.modelData.size); color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall + 1 }
                            }
                        }
                    }
                }

                GridView {
                    id: iconView
                    visible: page.viewMode === "icons"
                    anchors.fill: parent
                    anchors.margins: Theme.s2
                    clip: true
                    model: page.rows
                    cellWidth: 112
                    cellHeight: 104
                    boundsBehavior: Flickable.StopAtBounds
                    ScrollBar.vertical: ScrollBar {}
                    delegate: Rectangle {
                        id: cell
                        required property var modelData
                        required property int index
                        readonly property bool sel: !!page.selected[modelData.path]
                        readonly property var k: page.kind(modelData)
                        width: iconView.cellWidth - 6
                        height: iconView.cellHeight - 6
                        radius: Theme.radiusSmall
                        color: sel ? Qt.rgba(Theme.c.accent.r, Theme.c.accent.g, Theme.c.accent.b, 0.18) : cellHover.hovered ? Theme.c.surfaceElevated : "transparent"
                        border.color: sel ? Qt.rgba(Theme.c.accent.r, Theme.c.accent.g, Theme.c.accent.b, 0.5) : "transparent"
                        opacity: page.clip.cut && page.clip.paths.indexOf(modelData.path) >= 0 ? 0.5 : 1
                        HoverHandler { id: cellHover }
                        MouseArea {
                            anchors.fill: parent
                            acceptedButtons: Qt.LeftButton | Qt.RightButton
                            onClicked: mouse => {
                                if (mouse.button === Qt.RightButton && !cell.sel) page.select(cell.index, 0)
                                else if (mouse.button === Qt.LeftButton) page.select(cell.index, mouse.modifiers)
                                if (mouse.button === Qt.RightButton) contextMenu.popup()
                            }
                            onDoubleClicked: page.activate(cell.modelData)
                        }
                        ColumnLayout {
                            anchors.fill: parent; anchors.margins: 6
                            spacing: 4
                            NxIcon { Layout.alignment: Qt.AlignHCenter; name: cell.k.icon; color: cell.k.color; size: 44 }
                            Text {
                                Layout.fillWidth: true
                                text: cell.modelData.name
                                horizontalAlignment: Text.AlignHCenter
                                wrapMode: Text.WrapAnywhere
                                maximumLineCount: 2
                                elide: Text.ElideRight
                                color: Theme.c.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall + 1
                            }
                        }
                    }
                }

                ColumnLayout {
                    anchors.centerIn: parent
                    visible: page.rows.length === 0 && !(page.controller && page.controller.busy)
                    spacing: Theme.s2
                    NxIcon { Layout.alignment: Qt.AlignHCenter; name: page.filter ? "search" : "folder"; size: 36 }
                    Text { Layout.alignment: Qt.AlignHCenter; text: page.filter ? "No items match \"" + page.filter + "\"" : "This folder is empty"; color: Theme.c.textSecondary; font.family: Theme.fontFamily }
                }
            }
        }

        // status bar
        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.s3
            Text {
                text: page.rows.length + (page.rows.length === 1 ? " item" : " items") + (page.searching ? " found" : "")
                color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall + 1
            }
            Text {
                visible: page.selectedRows.length > 0
                text: "|   " + page.selectedRows.length + " selected" + (page.selectedRows.some(r => !r.is_dir) ? "   " + Theme.bytes(page.selectedRows.reduce((a, r) => a + (r.is_dir ? 0 : r.size), 0)) : "")
                color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall + 1
            }
            Text {
                visible: page.clip.paths.length > 0
                text: "|   " + page.clip.paths.length + (page.clip.cut ? " cut" : " copied") + " · Ctrl+V to paste"
                color: Theme.c.accent; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall + 1
            }
            Item { Layout.fillWidth: true }
            NxLoading { visible: !!(page.controller && page.controller.busy) }
        }
    }

    // ------------------------------------------------------------------ context menu
    Menu {
        id: contextMenu
        readonly property bool any: page.selectedPaths.length > 0
        MenuItem { text: page.single && page.single.is_dir ? "Open" : "Open"; enabled: !!page.single; onTriggered: page.activate(page.single) }
        MenuItem { text: "Open in Dolphin"; onTriggered: page.controller.openInDolphin(page.single && page.single.is_dir ? page.single.path : page.path) }
        MenuSeparator {}
        MenuItem { text: "Cut"; enabled: contextMenu.any; onTriggered: page.copySel(true) }
        MenuItem { text: "Copy"; enabled: contextMenu.any; onTriggered: page.copySel(false) }
        MenuItem { text: "Paste"; enabled: page.clip.paths.length > 0 && !page.searching; onTriggered: page.controller.paste() }
        MenuSeparator {}
        MenuItem { text: "Rename"; enabled: !!page.single; onTriggered: page.startRename() }
        MenuItem { text: "Move to trash"; enabled: contextMenu.any; onTriggered: page.trashSel() }
        MenuSeparator {}
        MenuItem { text: "Compress to .tar.gz"; enabled: contextMenu.any; onTriggered: page.controller.compress(page.selectedPaths) }
        MenuItem { text: "New folder"; enabled: !page.searching; onTriggered: page.controller.newFolder() }
        MenuItem { text: "Select all"; onTriggered: page.selectAll() }
    }
}
