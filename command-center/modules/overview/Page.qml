import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import Nexus.Design

// Operations dashboard. Tiles show one live value and one hardware line; the (i) icon
// opens a spec card (hover or click). Panels show only what the signed-in user can read.
Item {
    id: page
    objectName: "overviewPage"
    property var controller
    property var confirm
    property string intent: ""
    readonly property var d: controller ? controller.data : ({})
    readonly property var t: d.tiles || ({})
    readonly property var hw: d.hardware || ({})
    readonly property bool wide: width >= 1240
    readonly property int gap: Theme.s3

    // ------------------------------------------------------------------ formatting
    function num(v, digits) { return v === null || v === undefined ? "–" : Number(v).toFixed(digits || 0) }
    function gb(n) {
        if (n === null || n === undefined) return "–"
        if (n >= 1e12) return (n / 1e12).toFixed(1) + " TB"
        if (n >= 1e9) return (n / 1e9).toFixed(n >= 1e11 ? 0 : 1) + " GB"
        return Math.max(1, Math.round(n / 1e6)) + " MB"
    }
    function rate(bps) {
        if (bps === null || bps === undefined) return "–"
        if (bps >= 1e9) return (bps / 1e9).toFixed(1) + " GB/s"
        if (bps >= 1e6) return (bps / 1e6).toFixed(1) + " MB/s"
        if (bps >= 1e3) return (bps / 1e3).toFixed(0) + " kB/s"
        return Math.round(bps) + " B/s"
    }
    function ghz(mhz) { return mhz ? (mhz / 1000).toFixed(1) + " GHz" : "" }
    function ago(ts) {
        const s = Math.max(0, Date.now() / 1000 - ts)
        return s < 90 ? "just now" : s < 3600 ? Math.round(s / 60) + " min ago" : s < 86400 ? Math.round(s / 3600) + " h ago" : Math.round(s / 86400) + " d ago"
    }
    function cpuModelShort(m) { return (m || "").replace(/^(AMD|Intel)\s+/, "").replace(/\s+Processor.*$/, "").replace(/ with .*$/, "") }
    function go(target, intentValue) { if (target) App.navigate(target, intentValue || "") }

    // ------------------------------------------------------------------ building blocks
    component Panel: Rectangle {
        id: panel
        property string title
        property string subtitle
        property string icon
        property string action
        property string target
        property string targetIntent
        default property alias content: body.data
        color: Theme.c.surface
        radius: Theme.radius + 2
        border.color: Theme.c.border
        ColumnLayout {
            anchors.fill: parent
            anchors.margins: Theme.s3
            spacing: Theme.s2
            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: false
                spacing: Theme.s2
                NxIcon { name: panel.icon; size: 17; visible: panel.icon.length > 0 }
                Text { text: panel.title; color: Theme.c.text; font.family: Theme.fontFamily; font.pixelSize: 14; font.weight: Font.DemiBold }
                Text { text: panel.subtitle; visible: text.length > 0; color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody }
                Item { Layout.fillWidth: true }
                Text {
                    visible: panel.action.length > 0
                    text: panel.action
                    color: Theme.c.accent; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall + 1
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: page.go(panel.target, panel.targetIntent) }
                }
                NxIcon {
                    visible: panel.action.length === 0 && panel.target.length > 0
                    name: "chevron"; size: 15; color: Theme.c.textSecondary
                    MouseArea { anchors.fill: parent; anchors.margins: -6; cursorShape: Qt.PointingHandCursor; onClicked: page.go(panel.target, panel.targetIntent) }
                }
            }
            ColumnLayout { id: body; Layout.fillWidth: true; Layout.fillHeight: true; spacing: 0 }
        }
    }

    component Row2: RowLayout {   // label … value
        property string icon
        property color iconColor: Theme.c.textSecondary
        property string label
        property string value
        property color valueColor: Theme.c.text
        Layout.fillWidth: true
        Layout.fillHeight: true
        spacing: Theme.s2
        NxIcon { name: parent.icon; color: parent.iconColor; size: 16; visible: parent.icon.length > 0 }
        Text { text: parent.label; color: Theme.c.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; Layout.fillWidth: true; Layout.fillHeight: true; verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight }
        Text { text: parent.value; color: parent.valueColor; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; font.weight: Font.DemiBold; Layout.fillHeight: true; verticalAlignment: Text.AlignVCenter }
    }

    component KV: RowLayout {     // spec line inside cards (hidden when there is no value)
        property string k
        property string v
        visible: v.length > 0
        Layout.fillWidth: true
        spacing: Theme.s3
        Text { text: parent.k; color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall + 1 }
        Text { text: parent.v; color: Theme.c.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall + 1; Layout.fillWidth: true; horizontalAlignment: Text.AlignRight; elide: Text.ElideLeft }
    }

    component LiveCell: Rectangle {
        property string k
        property string v
        Layout.fillWidth: true
        implicitHeight: 44
        radius: Theme.radius
        color: Theme.c.surface
        border.color: Theme.c.border
        Column {
            anchors.verticalCenter: parent.verticalCenter
            x: Theme.s2
            Text { text: parent.parent.k; color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall }
            Text { text: parent.parent.v; color: Theme.c.text; font.family: Theme.fontFamily; font.pixelSize: 14; font.weight: Font.DemiBold }
        }
    }

    component SectionLabel: Text {
        color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall; font.weight: Font.DemiBold
        font.capitalization: Font.AllUppercase; font.letterSpacing: 0.8
        Layout.topMargin: Theme.s1
    }

    component Tile: Rectangle {
        id: tile
        property string kind
        property string label
        property string icon
        property color k: Theme.c.accent
        property string meta
        property string value: "–"
        property string unit
        property string foot
        property var spark: []
        property real sparkMin: NaN
        property real sparkMax: NaN
        property bool info: false
        property string target
        property string targetIntent
        Layout.fillWidth: true
        Layout.preferredWidth: 100
        Layout.preferredHeight: 112
        radius: Theme.radius + 2
        color: hover.hovered || page.infoKind === kind ? Theme.c.surfaceElevated : Theme.c.surface
        border.color: page.infoKind === kind ? k : hover.hovered ? Qt.rgba(k.r, k.g, k.b, 0.6) : Theme.c.border
        Behavior on color { ColorAnimation { duration: Theme.animationMs } }
        HoverHandler { id: hover }
        Component.onCompleted: page.tileItems[kind] = tile
        TapHandler {
            onTapped: {
                if (tile.target) page.go(tile.target, tile.targetIntent)
                else if (tile.info) page.toggleInfo(tile.kind, tile)
            }
        }
        Accessible.role: Accessible.Button
        Accessible.name: label + " " + value + unit

        RowLayout {
            anchors.fill: parent
            anchors.margins: 14
            spacing: Theme.s3
            Rectangle {
                Layout.alignment: Qt.AlignTop
                Layout.topMargin: 2
                width: 44; height: 44; radius: Theme.radius + 2
                color: Qt.rgba(tile.k.r, tile.k.g, tile.k.b, Theme.dark ? 0.16 : 0.12)
                border.color: Qt.rgba(tile.k.r, tile.k.g, tile.k.b, 0.3)
                NxIcon { anchors.centerIn: parent; name: tile.icon; color: tile.k; size: 22 }
            }
            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 0
                RowLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: false
                    spacing: Theme.s2
                    Text { text: tile.label; color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 13; font.weight: Font.Medium }
                    Item { Layout.fillWidth: true }
                    Text { text: tile.meta; color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall + 1; elide: Text.ElideLeft; Layout.maximumWidth: tile.width * 0.5 }
                    Rectangle {   // (i): hardware details
                        visible: tile.info
                        width: 16; height: 16; radius: 8
                        color: page.infoKind === tile.kind ? Qt.rgba(tile.k.r, tile.k.g, tile.k.b, 0.15) : "transparent"
                        border.width: 1.3
                        border.color: page.infoKind === tile.kind || infoHover.hovered ? tile.k : Theme.c.textSecondary
                        Text { anchors.centerIn: parent; text: "i"; font.italic: true; font.bold: true; font.pixelSize: 10; font.family: "serif"; color: parent.border.color }
                        HoverHandler {
                            id: infoHover
                            cursorShape: Qt.PointingHandCursor
                            onHoveredChanged: hovered ? page.hoverInfo(tile.kind, tile) : page.unhoverInfo()
                        }
                        TapHandler { onTapped: page.toggleInfo(tile.kind, tile, true) }
                        Accessible.role: Accessible.Button
                        Accessible.name: tile.label + " details"
                    }
                    NxIcon { visible: !tile.info && tile.target.length > 0; name: "chevron"; size: 15 }
                }
                RowLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    spacing: Theme.s3
                    Row {
                        spacing: 3
                        Layout.alignment: Qt.AlignVCenter
                        Text { text: tile.value; color: Theme.c.text; font.family: Theme.fontFamily; font.pixelSize: 26; font.weight: Font.DemiBold }
                        Text { text: tile.unit; anchors.baseline: parent.children[0].baseline; color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 14; font.weight: Font.DemiBold }
                    }
                    NxSparkline {
                        visible: (tile.spark || []).length > 1
                        Layout.fillWidth: true
                        Layout.preferredHeight: 26
                        Layout.alignment: Qt.AlignVCenter
                        values: tile.spark
                        color: tile.k
                        minValue: tile.sparkMin
                        maxValue: tile.sparkMax
                    }
                    Item { visible: (tile.spark || []).length < 2; Layout.fillWidth: true }
                    Item { Layout.fillHeight: true; implicitWidth: 0 }   // lets this row take the spare height
                }
                Text {
                    Layout.fillWidth: true
                    text: tile.foot
                    textFormat: Text.StyledText
                    color: Theme.c.textSecondary
                    font.family: Theme.fontFamily
                    font.pixelSize: 12
                    elide: Text.ElideRight
                }
            }
        }
    }

    // ------------------------------------------------------------------ hardware card (hover / click on "i")
    property string infoKind: ""
    property bool infoPinned: false
    property var tileItems: ({})
    function openInfo(kind) { if (tileItems[kind]) toggleInfo(kind, tileItems[kind], true) }
    // `nexus-center --smoke --screenshots` also captures every hardware card.
    readonly property var smokeStates: ["cpu", "memory", "gpu", "storage", "vuln", "password"]
    function applySmokeState(name) {
        infoPop.close()
        App.closeAuthPreview()
        if (name === "password") App.previewAuthPrompt()
        else if (name) openInfo(name)
    }
    property string pendingKind: ""
    property var pendingTile: null
    function placeInfo(kind, tileItem) {
        const p = tileItem.mapToItem(page, 0, tileItem.height + 8)
        infoPop.x = Math.max(Theme.s5, Math.min(p.x, page.width - infoPop.width - Theme.s5))
        infoPop.y = Math.min(p.y, page.height - infoPop.implicitHeight - Theme.s3)
        infoKind = kind
        if (!infoPop.opened) infoPop.open()
    }
    function toggleInfo(kind, tileItem, pin) {
        if (infoKind === kind && infoPop.opened && (infoPinned || !pin)) { infoPop.close(); return }
        infoPinned = !!pin
        placeInfo(kind, tileItem)
    }
    function hoverInfo(kind, tileItem) { closeTimer.stop(); pendingKind = kind; pendingTile = tileItem; openTimer.restart() }
    function unhoverInfo() { openTimer.stop(); if (!infoPinned) closeTimer.restart() }
    Timer { id: openTimer; interval: 350; onTriggered: if (page.pendingTile) { page.infoPinned = false; page.placeInfo(page.pendingKind, page.pendingTile) } }
    Timer { id: closeTimer; interval: 350; onTriggered: if (!popHover.hovered && !page.infoPinned) infoPop.close() }

    // Click outside a pinned card closes it (and the click still reaches what is underneath).
    MouseArea {
        anchors.fill: parent
        z: 99
        enabled: infoPop.visible && page.infoPinned
        onPressed: mouse => { infoPop.close(); mouse.accepted = false }
    }
    Shortcut { sequence: "Escape"; enabled: infoPop.visible; onActivated: infoPop.close() }

    // Spec card: a floating item inside the page (lighter than a Popup and part of screenshots).
    Rectangle {
        id: infoPop
        readonly property bool opened: visible
        function open() { visible = true }
        function close() { visible = false; page.infoKind = ""; page.infoPinned = false }
        visible: false
        z: 100
        width: 400
        implicitHeight: cardLoader.implicitHeight + Theme.s4 * 2
        height: implicitHeight
        color: Theme.c.surfaceElevated
        radius: Theme.radius + 2
        border.color: Theme.c.border
        Rectangle {   // soft shadow
            z: -1; anchors.fill: parent; anchors.topMargin: 6; anchors.leftMargin: -2; anchors.rightMargin: -2; anchors.bottomMargin: -10
            radius: parent.radius + 4; color: Qt.rgba(0, 0, 0, Theme.dark ? 0.35 : 0.12)
        }
        HoverHandler { id: popHover; onHoveredChanged: if (!hovered) page.unhoverInfo(); else closeTimer.stop() }
        Loader {
            id: cardLoader
            x: Theme.s4; y: Theme.s4
            width: parent.width - Theme.s4 * 2
            sourceComponent: page.infoKind === "cpu" ? cpuCard : page.infoKind === "memory" ? memoryCard
                : page.infoKind === "gpu" ? gpuCard : page.infoKind === "storage" ? storageCard : page.infoKind === "vuln" ? vulnCard : null
        }
    }

    Component {
        id: cpuCard
        ColumnLayout {
            readonly property var c: page.hw.cpu || ({})
            readonly property var live: page.t.cpu || ({})
            spacing: Theme.s2
            RowLayout {
                Text { text: parent.parent.c.model || "CPU"; color: Theme.c.text; font.family: Theme.fontFamily; font.pixelSize: 14; font.weight: Font.DemiBold; Layout.fillWidth: true; elide: Text.ElideRight }
                Text { text: [parent.parent.c.vendor, parent.parent.c.architecture].filter(x => x).join(" · "); color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall }
            }
            RowLayout {
                spacing: Theme.s2
                LiveCell { k: "Usage"; v: page.num(parent.parent.live.percent) + " %" }
                LiveCell { k: "Clock"; v: page.ghz(parent.parent.live.mhz) || "–" }
                LiveCell { k: "Package"; v: parent.parent.live.temp !== null && parent.parent.live.temp !== undefined ? page.num(parent.parent.live.temp) + " °C" : "no sensor" }
            }
            Row {   // per-core load
                Layout.fillWidth: true
                Layout.preferredHeight: 34
                spacing: 3
                readonly property var cores: (parent.live.perCore || []).slice(0, 32)
                Repeater {
                    model: parent.cores
                    Rectangle {
                        required property var modelData
                        width: Math.max(4, (parent.width - 3 * (parent.cores.length - 1)) / Math.max(1, parent.cores.length))
                        height: Math.max(3, 34 * modelData / 100)
                        anchors.bottom: parent.bottom
                        radius: 2
                        color: Theme.c.mCpu
                        opacity: 0.85
                    }
                }
            }
            SectionLabel { text: "Specification" }
            KV { k: "Cores / threads"; v: parent.c.cores ? parent.c.cores + " / " + parent.c.threads : "" }
            KV { k: "Base / max clock"; v: parent.c.max_mhz ? (parent.c.base_mhz ? page.ghz(parent.c.base_mhz) + " / " : "") + page.ghz(parent.c.max_mhz) : "" }
            KV { k: "Cache"; v: parent.c.cache ? ["L2", "L3"].filter(l => parent.c.cache[l]).map(l => l + " " + parent.c.cache[l]).join(" · ") : "" }
            KV { k: "Frequency scaling"; v: [parent.c.scaling_driver, parent.c.epp || parent.c.governor].filter(x => x).join(" · ") }
            KV { k: "Virtualisation"; v: parent.c.virtualization ? parent.c.virtualization + " available" : "" }
            KV { k: "Load average"; v: parent.live.load ? parent.live.load.map(x => x.toFixed(2)).join(" · ") : "" }
            KV { k: "Microcode"; v: parent.c.microcode || "" }
            Text { text: "From lscpu, /proc/cpuinfo and cpufreq · hwmon for temperature"; color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall; Layout.topMargin: Theme.s1 }
        }
    }

    Component {
        id: memoryCard
        ColumnLayout {
            readonly property var m: page.hw.memory || ({})
            readonly property var live: page.t.memory || ({})
            readonly property var mods: m.modules || []
            spacing: Theme.s2
            RowLayout {
                Text { text: Theme.bytes(parent.parent.m.total_bytes) + (parent.parent.m.summary ? "  ·  " + parent.parent.m.summary.split(" · ")[0] : ""); color: Theme.c.text; font.family: Theme.fontFamily; font.pixelSize: 14; font.weight: Font.DemiBold; Layout.fillWidth: true }
                Text { text: parent.parent.m.ecc ? "ECC " + parent.parent.m.ecc : ""; color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall }
            }
            RowLayout {
                spacing: Theme.s2
                LiveCell { k: "Used"; v: Theme.bytes(parent.parent.live.used) }
                LiveCell { k: "Available"; v: Theme.bytes(parent.parent.live.available) }
                LiveCell { k: "Swap"; v: parent.parent.live.swapTotal ? Theme.bytes(parent.parent.live.swapUsed) + " / " + Theme.bytes(parent.parent.live.swapTotal) : "none" }
            }
            SectionLabel { visible: parent.mods.length > 0; text: "Slots · " + parent.mods.filter(x => x.present).length + " of " + parent.mods.length + " used" }
            GridLayout {
                visible: parent.mods.length > 0
                Layout.fillWidth: true
                columns: Math.min(4, Math.max(1, parent.mods.length))
                columnSpacing: 6; rowSpacing: 6
                Repeater {
                    model: parent.mods
                    Rectangle {
                        required property var modelData
                        Layout.fillWidth: true
                        implicitHeight: 42
                        radius: Theme.radiusSmall + 2
                        color: modelData.present ? Qt.rgba(Theme.c.mMemory.r, Theme.c.mMemory.g, Theme.c.mMemory.b, 0.1) : "transparent"
                        border.color: modelData.present ? Qt.rgba(Theme.c.mMemory.r, Theme.c.mMemory.g, Theme.c.mMemory.b, 0.55) : Theme.c.border
                        Column {
                            anchors.centerIn: parent
                            Text { anchors.horizontalCenter: parent.horizontalCenter; text: modelData.slot; color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall }
                            Text { anchors.horizontalCenter: parent.horizontalCenter; text: modelData.present ? page.gb(modelData.size_bytes).replace(".0", "") : "empty"; color: modelData.present ? Theme.c.text : Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall + 1; font.weight: Font.DemiBold }
                        }
                    }
                }
            }
            readonly property var first: mods.find(x => x.present) || ({})
            KV { k: "Modules"; v: parent.first.part_number ? parent.mods.filter(x => x.present).length + " × " + [parent.first.manufacturer, parent.first.part_number].filter(x => x).join(" ") : "" }
            KV { k: "Speed"; v: parent.first.speed_mts ? parent.first.speed_mts + " MT/s" + (parent.first.configured_speed_mts && parent.first.configured_speed_mts !== parent.first.speed_mts ? " · running " + parent.first.configured_speed_mts : "") : "" }
            KV { k: "Voltage"; v: parent.first.voltage_mv ? (parent.first.voltage_mv / 1000).toFixed(2) + " V" : "" }
            KV { k: "Form factor"; v: parent.first.form_factor || "" }
            KV { k: "Maximum capacity"; v: parent.m.max_capacity_bytes ? page.gb(parent.m.max_capacity_bytes) : "" }
            Text { visible: !!parent.m.note; text: parent.m.note || ""; wrapMode: Text.WordWrap; Layout.fillWidth: true; color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall + 1 }
            Text { text: "Module data from SMBIOS via udev (no administrator rights needed)"; color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall; Layout.topMargin: Theme.s1 }
        }
    }

    Component {
        id: gpuCard
        ColumnLayout {
            spacing: Theme.s2
            Text { visible: (page.hw.gpus || []).length === 0; text: "No GPU is exposed to this system (virtual machine or no DRM device)."; wrapMode: Text.WordWrap; Layout.fillWidth: true; color: Theme.c.textSecondary; font.family: Theme.fontFamily }
            Repeater {
                model: page.hw.gpus || []
                ColumnLayout {
                    required property var modelData
                    required property int index
                    Layout.fillWidth: true
                    spacing: Theme.s2
                    SectionLabel { visible: index > 0; text: modelData.integrated ? "Integrated" : "Additional GPU" }
                    RowLayout {
                        Text { text: modelData.name; color: Theme.c.text; font.family: Theme.fontFamily; font.pixelSize: 14; font.weight: Font.DemiBold; Layout.fillWidth: true; elide: Text.ElideRight }
                        Text { text: [modelData.integrated ? "integrated" : "discrete", modelData.link].filter(x => x).join(" · "); color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall }
                    }
                    RowLayout {
                        visible: index === 0
                        spacing: Theme.s2
                        LiveCell { k: "Usage"; v: modelData.busy_percent !== null ? page.num(modelData.busy_percent) + " %" : "n/a" }
                        LiveCell { k: "VRAM"; v: modelData.vram_total_bytes ? Theme.bytes(modelData.vram_used_bytes) + " / " + Theme.bytes(modelData.vram_total_bytes) : "shared" }
                        LiveCell { k: "Power"; v: modelData.power_w ? page.num(modelData.power_w) + (modelData.power_limit_w ? " / " + page.num(modelData.power_limit_w) : "") + " W" : "n/a" }
                    }
                    KV { k: "Driver"; v: [modelData.driver, modelData.driver_version].filter(x => x).join(" ") }
                    KV { k: "Temperature"; v: modelData.temperature_c !== null && modelData.temperature_c !== undefined ? page.num(modelData.temperature_c) + " °C" : "" }
                    KV { k: "PCI slot"; v: modelData.pci_slot || "" }
                }
            }
            Text { text: "From DRM sysfs and lspci; nvidia-smi when the NVIDIA driver is installed"; color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall; Layout.topMargin: Theme.s1 }
        }
    }

    Component {
        id: storageCard
        ColumnLayout {
            readonly property var drives: page.hw.drives || []
            spacing: Theme.s2
            RowLayout {
                Text { text: parent.parent.drives.length + (parent.parent.drives.length === 1 ? " drive · " : " drives · ") + page.gb(parent.parent.drives.reduce((a, x) => a + x.size_bytes, 0)); color: Theme.c.text; font.family: Theme.fontFamily; font.pixelSize: 14; font.weight: Font.DemiBold; Layout.fillWidth: true }
                Text { text: "I/O " + page.rate(page.t.storage ? page.t.storage.bps : null); color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall }
            }
            Repeater {
                model: parent.drives
                ColumnLayout {
                    required property var modelData
                    Layout.fillWidth: true
                    spacing: 3
                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: modelData.model || modelData.name; color: Theme.c.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; font.weight: Font.DemiBold; elide: Text.ElideRight; Layout.maximumWidth: 210 }
                        Rectangle {
                            implicitWidth: tag.implicitWidth + 10; implicitHeight: 17; radius: 4; color: Theme.c.background
                            Text { id: tag; anchors.centerIn: parent; text: modelData.kind; color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: 10; font.weight: Font.DemiBold }
                        }
                        Item { Layout.fillWidth: true }
                        Text {
                            text: modelData.usage_mount ? modelData.usage_mount + " · " + page.num(modelData.usage_percent) + " %" : (modelData.mounts.length ? modelData.mounts[0] : "not mounted")
                            color: modelData.usage_percent >= 90 ? Theme.c.warning : Theme.c.textSecondary
                            font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall + 1
                        }
                    }
                    Text {
                        text: [page.gb(modelData.size_bytes), modelData.link, modelData.temperature_c ? page.num(modelData.temperature_c) + " °C" : "", modelData.name].filter(x => x).join(" · ")
                        color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall + 1
                    }
                    Rectangle {
                        visible: modelData.usage_percent !== null && modelData.usage_percent !== undefined
                        Layout.fillWidth: true; height: 4; radius: 2; color: Theme.c.border
                        Rectangle { width: parent.width * Math.min(1, (modelData.usage_percent || 0) / 100); height: 4; radius: 2; color: modelData.usage_percent >= 90 ? Theme.c.warning : Theme.c.mDisk }
                    }
                }
            }
            Text { text: "lsblk, NVMe/SATA link from sysfs · SMART wear and health: Storage (administrator)"; wrapMode: Text.WordWrap; Layout.fillWidth: true; color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall; Layout.topMargin: Theme.s1 }
        }
    }

    Component {
        id: vulnCard
        ColumnLayout {
            readonly property var v: page.t.vulnerabilities || ({})
            spacing: Theme.s2
            Text { text: !parent.v.known ? "Checking APT for security fixes…" : (parent.v.count || 0) + " installed packages have security fixes available"; color: Theme.c.text; font.family: Theme.fontFamily; font.pixelSize: 14; font.weight: Font.DemiBold; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            Text { text: (parent.v.packages || []).join(", ") + ((parent.v.count || 0) > (parent.v.packages || []).length ? " …" : ""); color: Theme.c.textSecondary; font.family: Theme.monoFamily; font.pixelSize: Theme.fontSmall; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            Text { text: "From the Ubuntu security pocket (resolute-security). CVE severities are not shown yet."; color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall; wrapMode: Text.WordWrap; Layout.fillWidth: true }
            NxButton { admin: true; text: "Review updates"; variant: "primary"; onClicked: { infoPop.close(); page.go("packages", "packages.upgrade") } }
        }
    }

    // ------------------------------------------------------------------ layout
    readonly property int fixedHeight: 56 + 236 + 172 + gap * 3 + Theme.s5 * 2 + (wide ? 0 : 150)
    ScrollView {
        anchors.fill: parent
        contentWidth: availableWidth
        ColumnLayout {
            x: Theme.s5
            y: Theme.s4
            width: parent.width - Theme.s5 * 2
            spacing: page.gap

            // header
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.s2
                ColumnLayout {
                    spacing: 2
                    Layout.fillWidth: true
                    Text { text: "Overview"; color: Theme.c.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontDisplay; font.weight: Font.DemiBold }
                    Text {
                        text: [page.d.system ? page.d.system.hostname : "", page.d.system ? page.d.system.os : "", page.d.uptime ? "up " + Theme.duration(page.d.uptime) : "", page.d.processes ? page.d.processes + " processes" : ""].filter(x => x).join("  ·  ")
                        color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; elide: Text.ElideRight; Layout.fillWidth: true
                    }
                }
                Rectangle {
                    readonly property color tone: page.d.health === "ok" ? Theme.c.positive : page.d.health === "degraded" ? Theme.c.negative : Theme.c.warning
                    visible: !!page.d.loaded
                    implicitWidth: healthText.implicitWidth + 34; implicitHeight: 30; radius: 15
                    color: Qt.rgba(tone.r, tone.g, tone.b, 0.12)
                    border.color: Qt.rgba(tone.r, tone.g, tone.b, 0.45)
                    Rectangle { x: 12; anchors.verticalCenter: parent.verticalCenter; width: 8; height: 8; radius: 4; color: parent.tone }
                    Text {
                        id: healthText
                        x: 26; anchors.verticalCenter: parent.verticalCenter
                        text: page.d.health === "ok" ? "All systems normal" : (page.d.attention || []).length + ((page.d.attention || []).length === 1 ? " issue needs attention" : " issues need attention")
                        color: parent.tone; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; font.weight: Font.DemiBold
                    }
                }
                NxButton { text: "Refresh"; onClicked: controller.refreshAll() }
            }

            // tiles (+ attention column when wide)
            GridLayout {
                Layout.fillWidth: true
                columns: page.wide ? 5 : 4
                columnSpacing: page.gap
                rowSpacing: page.gap

                Tile {
                    Layout.row: 0; Layout.column: 0
                    kind: "cpu"; label: "CPU"; icon: "cpu"; k: Theme.c.mCpu; info: true
                    readonly property var x_: page.t.cpu || ({})
                    meta: [page.ghz(x_.mhz), x_.temp !== null && x_.temp !== undefined ? page.num(x_.temp) + " °C" : ""].filter(s => s).join(" · ")
                    value: page.num(x_.percent); unit: "%"
                    spark: x_.spark || []; sparkMin: 0; sparkMax: 100
                    foot: page.hw.cpu ? "<b><font color='" + Theme.c.text + "'>" + page.cpuModelShort(page.hw.cpu.model) + "</font></b>&nbsp;&nbsp;" + (page.hw.cpu.cores || "?") + "C / " + (page.hw.cpu.threads || "?") + "T" : ""
                }
                Tile {
                    Layout.row: 0; Layout.column: 1
                    kind: "memory"; label: "Memory"; icon: "memory"; k: Theme.c.mMemory; info: true
                    readonly property var x_: page.t.memory || ({})
                    meta: x_.total ? (x_.used / 2 ** 30).toFixed(1) + " / " + (x_.total / 2 ** 30).toFixed(0) + " GiB" : ""
                    value: page.num(x_.percent); unit: "%"
                    spark: x_.spark || []; sparkMin: 0; sparkMax: 100
                    foot: page.hw.memory && page.hw.memory.summary ? "<b><font color='" + Theme.c.text + "'>" + page.hw.memory.summary.split(" · ")[0] + "</font></b>&nbsp;&nbsp;" + page.hw.memory.summary.split(" · ").slice(1).join(" · ") : "module details not exposed"
                }
                Tile {
                    Layout.row: 0; Layout.column: 2
                    kind: "gpu"; label: "GPU"; icon: "gpu"; k: Theme.c.mGpu; info: true
                    readonly property var x_: page.t.gpu || ({})
                    readonly property var g0: (page.hw.gpus || [])[0]
                    meta: [x_.vramTotal ? (x_.vramUsed / 2 ** 30).toFixed(1) + " / " + (x_.vramTotal / 2 ** 30).toFixed(0) + " GiB" : "", x_.temp ? page.num(x_.temp) + " °C" : ""].filter(s => s).join(" · ")
                    value: x_.present ? page.num(x_.percent) : "–"; unit: x_.present && x_.percent !== null ? "%" : ""
                    spark: x_.spark || []; sparkMin: 0; sparkMax: 100
                    foot: g0 ? "<b><font color='" + Theme.c.text + "'>" + g0.name.replace(/^NVIDIA GeForce /, "").replace(/^AMD /, "") + "</font></b>&nbsp;&nbsp;" + (g0.vram_total_bytes ? page.gb(g0.vram_total_bytes).replace(".0", "") : g0.integrated ? "integrated" : "") : "no GPU exposed"
                }
                Tile {
                    Layout.row: 0; Layout.column: 3
                    kind: "storage"; label: "Storage  " + (page.t.storage && page.t.storage.mount ? page.t.storage.mount : ""); icon: "disk"; k: Theme.c.mDisk; info: true
                    readonly property var x_: page.t.storage || ({})
                    readonly property var dr: page.hw.drives || []
                    meta: x_.free !== null && x_.free !== undefined ? page.gb(x_.free) + " free" : ""
                    value: page.num(x_.percent); unit: "%"
                    spark: x_.spark || []
                    foot: dr.length ? "<b><font color='" + Theme.c.text + "'>" + dr.length + (dr.length === 1 ? " drive" : " drives") + "</font></b>&nbsp;&nbsp;" + page.gb(dr.reduce((a, x) => a + x.size_bytes, 0)) + (dr.filter(x => x.kind === "NVMe").length ? " · " + dr.filter(x => x.kind === "NVMe").length + " NVMe" : "") : ""
                }
                Tile {
                    Layout.row: 1; Layout.column: 0
                    kind: "vuln"; label: "Vulnerabilities"; icon: "shield"; k: Theme.c.mVuln; info: true
                    readonly property var x_: page.t.vulnerabilities || ({})
                    value: x_.known ? String(x_.count) : "…"
                    foot: !x_.known ? "checking APT…" : x_.count ? "<font color='" + Theme.c.negative + "'>packages with security fixes</font>" : "<font color='" + Theme.c.positive + "'>no known fixes pending</font>"
                }
                Tile {
                    Layout.row: 1; Layout.column: 1
                    kind: "updates"; label: "Updates"; icon: "update"; k: Theme.c.mUpdates; target: "packages"; targetIntent: "packages.upgrade"
                    readonly property var x_: page.t.updates || ({})
                    value: x_.known ? String(x_.total) : (x_.error ? "?" : "…")
                    unit: x_.known ? " pending" : ""
                    foot: x_.known ? "<font color='" + Theme.c.warning + "'>" + x_.security + " security</font> · " + (x_.total - x_.security) + " regular · checked " + x_.checked : (x_.error || "checking APT…")
                }
                Tile {
                    Layout.row: 1; Layout.column: 2
                    kind: "network"; label: "Network"; icon: "network"; k: Theme.c.mNetwork; target: "network"
                    readonly property var x_: page.t.network || ({})
                    value: x_.online === true ? "Online" : x_.online === false ? "Offline" : "–"
                    spark: x_.spark || []
                    foot: "↓ " + page.rate(x_.rx) + "  ·  ↑ " + page.rate(x_.tx)
                }
                Tile {
                    Layout.row: 1; Layout.column: 3
                    kind: "mounts"; label: "Mount points"; icon: "mount"; k: Theme.c.mMounts; target: "storage"
                    readonly property var x_: page.t.mounts || ({})
                    value: x_.count !== undefined ? String(x_.count) : "–"
                    foot: x_.worst ? (x_.worst.percent >= 90 ? "<font color='" + Theme.c.warning + "'>" : "<font>") + x_.worst.mount + " " + page.num(x_.worst.percent) + " % used</font>" : ""
                }

                // System attention
                Panel {
                    id: attentionPanel
                    Layout.row: page.wide ? 0 : 2
                    Layout.column: page.wide ? 4 : 0
                    Layout.rowSpan: page.wide ? 2 : 1
                    Layout.columnSpan: page.wide ? 1 : 4
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.preferredWidth: page.wide ? 118 : 400
                    Layout.preferredHeight: page.wide ? -1 : 138
                    title: "System attention"
                    readonly property var issues: page.d.attention || []
                    Rectangle {
                        visible: attentionPanel.issues.length > 0
                        Layout.fillWidth: true
                        implicitHeight: 36
                        radius: Theme.radius
                        color: Qt.rgba(Theme.c.negative.r, Theme.c.negative.g, Theme.c.negative.b, 0.14)
                        border.color: Qt.rgba(Theme.c.negative.r, Theme.c.negative.g, Theme.c.negative.b, 0.35)
                        RowLayout {
                            anchors.fill: parent; anchors.leftMargin: Theme.s3
                            NxIcon { name: "alert"; color: Theme.c.warning; size: 18 }
                            Text {
                                Layout.fillWidth: true; text: attentionPanel.issues.length + (attentionPanel.issues.length === 1 ? " issue needs attention" : " issues need attention"); color: Theme.c.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody + 1; font.weight: Font.DemiBold }
                        }
                    }
                    GridLayout {
                        Layout.fillWidth: true
                        Layout.topMargin: Theme.s1
                        columns: page.wide ? 1 : 2
                        rowSpacing: 0
                        columnSpacing: Theme.s4
                        Repeater {
                            model: (attentionPanel.issues || []).slice(0, page.wide ? 5 : 4)
                            RowLayout {
                                required property var modelData
                                Layout.fillWidth: true
                                implicitHeight: 30
                                spacing: Theme.s2
                                Rectangle { width: 8; height: 8; radius: 4; color: modelData.severity === "critical" ? Theme.c.negative : Theme.c.warning }
                                Text { text: modelData.title; color: Theme.c.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody }
                                Text { text: modelData.detail; color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall; elide: Text.ElideRight; Layout.fillWidth: true }
                                NxIcon { name: "chevron"; size: 14 }
                                TapHandler { onTapped: page.go(modelData.page, modelData.intent) }
                                HoverHandler { cursorShape: Qt.PointingHandCursor }
                            }
                        }
                    }
                    ColumnLayout {
                        visible: !!page.d.loaded && (attentionPanel.issues || []).length === 0
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        NxIcon { Layout.alignment: Qt.AlignHCenter; name: "check"; color: Theme.c.positive; size: 30 }
                        Text { Layout.alignment: Qt.AlignHCenter; text: "Nothing needs attention"; color: Theme.c.text; font.family: Theme.fontFamily; font.weight: Font.DemiBold }
                        Text { Layout.alignment: Qt.AlignHCenter; text: "Failed services, low disk space, security fixes,\nexpiring certificates and overdue backups appear here."; horizontalAlignment: Text.AlignHCenter; color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall }
                    }
                    Item { Layout.fillHeight: true }
                }
            }

            // middle: 24 h chart · services + infrastructure · recent activity
            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: Math.max(270, page.height - page.fixedHeight)
                spacing: page.gap
                Panel {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.preferredWidth: 155
                    title: "Resource usage"
                    subtitle: page.d.chart && page.d.chart.source === "sar" ? "last 24 hours (sysstat)" : "since the Command Center started"
                    icon: "chart"
                    RowLayout {
                        Layout.fillWidth: true
                        Item { Layout.fillWidth: true }
                        Rectangle {
                            implicitWidth: tabRow.implicitWidth + 4; implicitHeight: 28; radius: Theme.radius; color: Theme.c.background; border.color: Theme.c.border
                            Row {
                                id: tabRow
                                anchors.centerIn: parent
                                Repeater {
                                    model: [["cpu", "CPU"], ["memory", "Memory"], ["disk", "Disk I/O"], ["network", "Network"]]
                                    Rectangle {
                                        required property var modelData
                                        readonly property bool on: (page.d.chartTab || "cpu") === modelData[0]
                                        width: tabLabel.implicitWidth + 22; height: 24; radius: Theme.radiusSmall + 2
                                        color: on ? Theme.c.backgroundSecondary : "transparent"
                                        border.color: on ? Qt.rgba(Theme.c.accent.r, Theme.c.accent.g, Theme.c.accent.b, 0.5) : "transparent"
                                        Text { id: tabLabel; anchors.centerIn: parent; text: modelData[1]; color: parent.on ? Theme.c.text : Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall + 1; font.weight: Font.Medium }
                                        TapHandler { onTapped: controller.setChartTab(modelData[0]) }
                                    }
                                }
                            }
                        }
                    }
                    UsageChart {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        points: page.d.chart ? page.d.chart.points : []
                        percent: (page.d.chartTab || "cpu") === "cpu" || page.d.chartTab === "memory"
                        lineColor: ({ cpu: Theme.c.mCpu, memory: Theme.c.mMemory, disk: Theme.c.mDisk, network: Theme.c.mUpdates })[page.d.chartTab || "cpu"]
                        formatValue: v => percent ? v.toFixed(0) + " %" : page.rate(v)
                    }
                }
                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.preferredWidth: 100
                    spacing: page.gap
                    Panel {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        title: "System services"
                    id: servicesPanel; icon: "services"; target: "settings"; targetIntent: "native:services"
                        readonly property var s: page.d.services || ({})
                        Row2 { icon: "check"; iconColor: Theme.c.positive; label: "Running"; value: servicesPanel.s.running !== undefined ? String(servicesPanel.s.running) : "–" }
                        Row2 { icon: "cross"; iconColor: Theme.c.negative; label: "Failed"; value: servicesPanel.s.failed ? (servicesPanel.s.failed.length ? servicesPanel.s.failed.length + " · " + servicesPanel.s.failed[0].replace(".service", "") : "0") : "–"; valueColor: servicesPanel.s.failed && servicesPanel.s.failed.length ? Theme.c.negative : Theme.c.text }
                        Row2 { icon: "warn"; iconColor: Theme.c.warning; label: "Starting / stopping"; value: servicesPanel.s.starting !== undefined ? String(servicesPanel.s.starting) : "–" }
                    }
                    Panel {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        title: "Infrastructure"
                    id: infraPanel; icon: "infra"; target: "containers"
                        readonly property var i: page.d.infra || ({})
                        Row2 { icon: "docker"; label: "Containers"; value: !infraPanel.i.docker_access ? "no access" : infraPanel.i.containers_total === null || infraPanel.i.containers_total === undefined ? "–" : infraPanel.i.containers_running + " / " + infraPanel.i.containers_total + " running"; valueColor: infraPanel.i.docker_access ? Theme.c.text : Theme.c.textSecondary }
                        Row2 { icon: "vm"; label: "Virtual machines"; value: !infraPanel.i.libvirt_access ? "no access" : infraPanel.i.vms_total === null || infraPanel.i.vms_total === undefined ? "libvirt not running" : infraPanel.i.vms_running + " / " + infraPanel.i.vms_total + " running"; valueColor: infraPanel.i.vms_total !== null && infraPanel.i.vms_total !== undefined ? Theme.c.text : Theme.c.textSecondary }
                        Row2 { icon: "apps"; label: "Nexus applications"; value: (infraPanel.i.apps || []).length ? (infraPanel.i.apps.filter(a => a.health === "healthy").length + " / " + infraPanel.i.apps.length + " healthy") : "none installed"; valueColor: (infraPanel.i.apps || []).length ? Theme.c.text : Theme.c.textSecondary }
                    }
                }
                Panel {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.preferredWidth: 100
                    title: "Recent activity"; icon: "activity"; action: "View all"; target: "activity"
                    Repeater {
                        model: (page.d.activity || []).slice(0, 8)
                        RowLayout {
                            required property var modelData
                            required property int index
                            Layout.fillWidth: true
                            Layout.preferredHeight: 32
                            spacing: Theme.s2
                            NxIcon { name: modelData.outcome === "ok" ? "check" : modelData.outcome === "failed" ? "cross" : "info"; color: modelData.outcome === "ok" ? Theme.c.positive : modelData.outcome === "failed" ? Theme.c.negative : Theme.c.mUpdates; size: 16 }
                            Text { text: modelData.action + "  " + modelData.target; color: Theme.c.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody; elide: Text.ElideRight; Layout.fillWidth: true }
                            Text { text: page.ago(modelData.ts); color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall }
                        }
                    }
                    ColumnLayout {
                        visible: (page.d.activity || []).length === 0
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Text { Layout.alignment: Qt.AlignCenter; text: "No activity yet"; color: Theme.c.textSecondary; font.family: Theme.fontFamily }
                    }
                    Item { Layout.fillHeight: true }
                }
            }

            // bottom: history · backups · certificates
            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 172
                spacing: page.gap
                Panel {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.preferredWidth: 155
                    title: "Historical health"
                    id: sarPanel; subtitle: "sar · 7 days"; icon: "chart"
                    readonly property var sar: page.d.sar || ({})
                    RowLayout {
                        visible: !!sarPanel.sar.available
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        spacing: Theme.s2
                        Repeater {
                            model: [["cpu", "CPU avg", true], ["memory", "Memory avg", true], ["disk", "Disk I/O", false], ["network", "Network", false]]
                            Rectangle {
                                required property var modelData
                                readonly property var series: ((page.d.sar || {}).daily || []).map(x => x[modelData[0]]).filter(x => x !== null && x !== undefined)
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                radius: Theme.radius
                                color: Theme.c.surfaceElevated
                                border.color: Theme.c.border
                                ColumnLayout {
                                    anchors.fill: parent; anchors.margins: Theme.s2
                                    spacing: 0
                                    Text { text: modelData[1]; color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall + 1 }
                                    Text {
                                        readonly property var avg: parent.parent.series.length ? parent.parent.series.reduce((a, b) => a + b, 0) / parent.parent.series.length : null
                                        text: avg === null ? "–" : modelData[2] ? avg.toFixed(0) + " %" : page.rate(avg)
                                        color: Theme.c.text; font.family: Theme.fontFamily; font.pixelSize: 18; font.weight: Font.DemiBold
                                    }
                                    NxSparkline { Layout.fillWidth: true; Layout.fillHeight: true; values: parent.parent.series; color: [Theme.c.mCpu, Theme.c.mUpdates, Theme.c.mGpu, Theme.c.mDisk][index] ; property int index: ["cpu", "memory", "disk", "network"].indexOf(modelData[0]) }
                                }
                            }
                        }
                    }
                    ColumnLayout {
                        visible: !sarPanel.sar.available
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        spacing: Theme.s1
                        Item { Layout.fillHeight: true }
                        Text { Layout.alignment: Qt.AlignHCenter; text: page.d.sar ? (page.d.sar.reason || "") : "Loading…"; color: Theme.c.text; font.family: Theme.fontFamily; font.weight: Font.DemiBold }
                        Text { Layout.alignment: Qt.AlignHCenter; text: "sysstat keeps CPU, memory, disk and network history (sar) with a few kB per day."; color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall }
                        NxButton { Layout.alignment: Qt.AlignHCenter; admin: true; visible: !!(page.d.sar && page.d.sar.reason === "sysstat is not installed") && App.canAdmin; text: "Install sysstat…"; onClicked: page.go("packages", "details:sysstat") }
                        Item { Layout.fillHeight: true }
                    }
                }
                Panel {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.preferredWidth: 100
                    title: "Backups & protection"
                    id: backupPanel; icon: "backup"
                    readonly property var b: page.d.backups || ({})
                    readonly property var job: (b.jobs || [])[0] || ({})
                    Row2 { visible: !!backupPanel.b.configured; icon: backupPanel.job.result === "success" ? "check" : "warn"; iconColor: backupPanel.job.result === "success" ? Theme.c.positive : Theme.c.warning; label: "Last run"; value: backupPanel.job.last || "never" }
                    Row2 { visible: !!backupPanel.b.configured; icon: "calendar"; label: "Next run"; value: backupPanel.job.next || "–" }
                    Row2 { visible: !!backupPanel.b.configured; icon: "backup"; label: (backupPanel.b.jobs || []).length > 1 ? (backupPanel.b.jobs.length + " jobs") : (backupPanel.job.unit || ""); value: backupPanel.b.overdue ? "Overdue" : !backupPanel.job.last ? "Not run yet" : "Healthy"; valueColor: backupPanel.b.overdue ? Theme.c.warning : !backupPanel.job.last ? Theme.c.textSecondary : Theme.c.positive }
                    ColumnLayout {
                        visible: page.d.backups !== undefined && !backupPanel.b.configured
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        Item { Layout.fillHeight: true }
                        Text { Layout.alignment: Qt.AlignHCenter; text: "No backup jobs found"; color: Theme.c.text; font.family: Theme.fontFamily; font.weight: Font.DemiBold }
                        Text { Layout.alignment: Qt.AlignHCenter; horizontalAlignment: Text.AlignHCenter; text: "systemd timers for restic, borg, Timeshift,\nDéjà Dup or rsnapshot appear here."; color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall }
                        Item { Layout.fillHeight: true }
                    }
                }
                Panel {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.preferredWidth: 100
                    title: "Certificates"
                    id: certPanel; subtitle: "gateway"; icon: "cert"; target: "gateway"
                    readonly property var c: page.d.certs || ({})
                    Row2 { icon: "check"; iconColor: Theme.c.positive; label: "Valid"; value: String(certPanel.c.valid || 0) }
                    Row2 { icon: "alert"; iconColor: Theme.c.warning; label: "Expiring (≤ 30 days)"; value: String(certPanel.c.expiring || 0); valueColor: certPanel.c.expiring ? Theme.c.warning : Theme.c.text }
                    Row2 { icon: "cross"; iconColor: Theme.c.textSecondary; label: "Expired"; value: String(certPanel.c.expired || 0); valueColor: certPanel.c.expired ? Theme.c.negative : Theme.c.text }
                }
            }
            Item { Layout.preferredHeight: Theme.s3 }
        }
    }

    // 24 h / session chart with axis labels and a hover read-out.
    component UsageChart: Item {
        id: chart
        property var points: []
        property bool percent: true
        property color lineColor: Theme.c.mCpu
        property var formatValue: v => v
        property int hoverIndex: -1
        readonly property int padLeft: 44
        readonly property int padBottom: 20
        readonly property real maxValue: percent ? 100 : Math.max(1, ...(points.length ? points.map(p => p[1]) : [1])) * 1.15
        function px(i) { return padLeft + (width - padLeft - 6) * (points.length > 1 ? (points[i][0] - points[0][0]) / Math.max(1, points[points.length - 1][0] - points[0][0]) : 0) }
        function py(v) { return 6 + (height - padBottom - 6) * (1 - Math.min(v, maxValue) / maxValue) }
        onPointsChanged: canvas.requestPaint()
        onLineColorChanged: canvas.requestPaint()
        onWidthChanged: canvas.requestPaint()
        onHeightChanged: canvas.requestPaint()
        Canvas {
            id: canvas
            anchors.fill: parent
            renderStrategy: Canvas.Cooperative
            onPaint: {
                const ctx = getContext("2d")
                ctx.reset()
                ctx.font = "11px " + Theme.canvasFontFamily
                ctx.fillStyle = Theme.c.textSecondary
                ctx.strokeStyle = Theme.c.border
                ctx.lineWidth = 1
                for (let s = 0; s <= 4; s++) {
                    const v = chart.maxValue * s / 4
                    const y = Math.round(chart.py(v)) + 0.5
                    ctx.globalAlpha = 0.6
                    ctx.beginPath(); ctx.moveTo(chart.padLeft, y); ctx.lineTo(width - 6, y); ctx.stroke()
                    ctx.globalAlpha = 1
                    ctx.textAlign = "right"
                    ctx.fillText(chart.formatValue(v), chart.padLeft - 8, y + 4)
                }
                const p = chart.points
                if (!p || p.length < 2) {
                    ctx.textAlign = "center"
                    ctx.fillText("collecting data…", (chart.padLeft + width) / 2, height / 2)
                    return
                }
                const span = p[p.length - 1][0] - p[0][0]
                const ticks = 6
                ctx.textAlign = "center"
                for (let t = 0; t <= ticks; t++) {
                    const ts = p[0][0] + span * t / ticks
                    const d = new Date(ts * 1000)
                    const label = ("0" + d.getHours()).slice(-2) + ":" + ("0" + d.getMinutes()).slice(-2)
                    ctx.textAlign = t === 0 ? "left" : t === ticks ? "right" : "center"
                    ctx.fillText(label, chart.padLeft + (width - chart.padLeft - 6) * t / ticks, height - 4)
                }
                ctx.beginPath()
                ctx.moveTo(chart.px(0), chart.py(p[0][1]))
                for (let i = 1; i < p.length; i++) ctx.lineTo(chart.px(i), chart.py(p[i][1]))
                ctx.save()
                ctx.lineTo(chart.px(p.length - 1), chart.py(0))
                ctx.lineTo(chart.px(0), chart.py(0))
                ctx.closePath()
                const g = ctx.createLinearGradient(0, 0, 0, height)
                g.addColorStop(0, Qt.rgba(chart.lineColor.r, chart.lineColor.g, chart.lineColor.b, 0.35))
                g.addColorStop(1, Qt.rgba(chart.lineColor.r, chart.lineColor.g, chart.lineColor.b, 0.0))
                ctx.fillStyle = g
                ctx.fill()
                ctx.restore()
                ctx.beginPath()
                ctx.moveTo(chart.px(0), chart.py(p[0][1]))
                for (let j = 1; j < p.length; j++) ctx.lineTo(chart.px(j), chart.py(p[j][1]))
                ctx.strokeStyle = chart.lineColor
                ctx.lineWidth = 2
                ctx.lineJoin = "round"
                ctx.stroke()
            }
        }
        MouseArea {
            anchors.fill: parent
            hoverEnabled: true
            onExited: chart.hoverIndex = -1
            onPositionChanged: mouse => {
                const p = chart.points
                if (!p || p.length < 2) { chart.hoverIndex = -1; return }
                let best = 0, dist = 1e9
                for (let i = 0; i < p.length; i++) { const dd = Math.abs(chart.px(i) - mouse.x); if (dd < dist) { dist = dd; best = i } }
                chart.hoverIndex = best
            }
        }
        Rectangle {
            visible: chart.hoverIndex >= 0
            x: chart.hoverIndex >= 0 ? chart.px(chart.hoverIndex) : 0
            y: 6; width: 1; height: chart.height - chart.padBottom - 6
            color: chart.lineColor; opacity: 0.6
        }
        Rectangle {
            visible: chart.hoverIndex >= 0
            readonly property var pt: chart.hoverIndex >= 0 ? chart.points[chart.hoverIndex] : [0, 0]
            x: Math.min(chart.width - width - 4, (chart.hoverIndex >= 0 ? chart.px(chart.hoverIndex) : 0) + 8)
            y: Math.max(0, (chart.hoverIndex >= 0 ? chart.py(pt[1]) : 0) - height - 6)
            width: tip.implicitWidth + 16; height: tip.implicitHeight + 10
            radius: Theme.radiusSmall + 2
            color: Theme.c.surfaceElevated
            border.color: Theme.c.border
            Text {
                id: tip
                anchors.centerIn: parent
                readonly property var d: new Date(parent.pt[0] * 1000)
                text: ("0" + d.getHours()).slice(-2) + ":" + ("0" + d.getMinutes()).slice(-2) + "   " + chart.formatValue(parent.pt[1])
                color: Theme.c.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall + 1; font.weight: Font.DemiBold
            }
        }
    }
}
