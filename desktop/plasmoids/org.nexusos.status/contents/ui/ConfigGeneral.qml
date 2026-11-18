import QtQuick
import QtQuick.Controls as QQC2
import org.kde.kirigami as Kirigami
import org.kde.kcmutils as KCM

KCM.SimpleKCM {
    property alias cfg_showPercentages: percentages.checked
    property alias cfg_use24h: clock24.checked
    property alias cfg_pinned: pinned.checked
    property alias cfg_statusInterval: interval.value

    Kirigami.FormLayout {
        QQC2.CheckBox { id: percentages; Kirigami.FormData.label: i18n("Rail:"); text: i18n("Show CPU, memory and disk percentages") }
        QQC2.CheckBox { id: clock24; text: i18n("24-hour clock") }
        QQC2.CheckBox { id: pinned; Kirigami.FormData.label: i18n("Panel:"); text: i18n("Keep the expanded panel open (pinned)") }
        QQC2.SpinBox {
            id: interval
            Kirigami.FormData.label: i18n("Health check every:")
            from: 60; to: 3600; stepSize: 60
            textFromValue: v => i18np("%1 minute", "%1 minutes", Math.round(v / 60))
        }
    }
}
