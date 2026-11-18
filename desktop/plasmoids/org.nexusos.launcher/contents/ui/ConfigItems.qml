/*
 * Launcher settings: which shortcuts this rail shows and in which order.
 */
import QtQuick
import QtQuick.Layouts
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami
import org.kde.kcmutils as KCM

KCM.SimpleKCM {
    id: page
    property var cfg_items: []
    property var cfg_itemsDefault: []
    property var cfg_hiddenItems: []
    property var cfg_hiddenItemsDefault: []
    readonly property var names: ({
        logo: i18n("NexusOS (Command Center)"), home: i18n("Show Desktop"), files: i18n("Files"), terminal: i18n("Terminal"),
        containers: i18n("Containers"), vms: i18n("Virtual Machines"), cloud: i18n("Cloud Platform"), ai: i18n("AI Assistant"),
        browser: i18n("Web Browser"), editor: i18n("Text Editor"), monitor: i18n("System Monitor"), settings: i18n("System Settings"),
        more: i18n("All shortcuts (expand)")
    })
    readonly property var all: Object.keys(names)
    function move(id, delta) {
        const list = cfg_items.slice()
        const i = list.indexOf(id), j = i + delta
        if (i < 0 || j < 0 || j >= list.length) return
        list.splice(i, 1); list.splice(j, 0, id)
        cfg_items = list
    }
    function setShown(id, shown) {
        let list = cfg_items.slice()
        if (shown && list.indexOf(id) < 0) list.push(id)
        if (!shown) list = list.filter(x => x !== id)
        cfg_items = list
    }

    ColumnLayout {
        QQC2.Label { Layout.fillWidth: true; wrapMode: Text.Wrap; text: i18n("Shortcuts for tools that are not installed stay hidden until they are.") }
        Repeater {
            model: page.cfg_items.concat(page.all.filter(id => page.cfg_items.indexOf(id) < 0))
            RowLayout {
                required property string modelData
                required property int index
                QQC2.CheckBox { checked: page.cfg_items.indexOf(modelData) >= 0; text: page.names[modelData] || modelData; Layout.fillWidth: true; onToggled: page.setShown(modelData, checked) }
                QQC2.ToolButton { icon.name: "go-up"; enabled: page.cfg_items.indexOf(modelData) > 0; onClicked: page.move(modelData, -1); QQC2.ToolTip.text: i18n("Move up"); QQC2.ToolTip.visible: hovered }
                QQC2.ToolButton { icon.name: "go-down"; enabled: page.cfg_items.indexOf(modelData) >= 0 && page.cfg_items.indexOf(modelData) < page.cfg_items.length - 1; onClicked: page.move(modelData, 1); QQC2.ToolTip.text: i18n("Move down"); QQC2.ToolTip.visible: hovered }
            }
        }
    }
}
