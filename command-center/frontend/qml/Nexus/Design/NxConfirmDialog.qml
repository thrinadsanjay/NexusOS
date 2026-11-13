import QtQuick
import QtQuick.Controls.Basic as B
import QtQuick.Layouts

// Confirmation for administrative/destructive actions. Shows exactly what will happen
// (details lines, e.g. the APT plan or the command), and can require a typed token.
B.Dialog {
    id: dialog
    property string message: ""
    property var details: []
    property string confirmText: "Confirm"
    property bool danger: false
    property string requiredToken: ""
    property var onAccept: null
    property var onCancel: null
    modal: true
    anchors.centerIn: parent
    width: Math.min(parent ? parent.width - 80 : 640, 640)
    padding: Theme.s4
    background: Rectangle { color: Theme.c.surfaceElevated; radius: Theme.radius; border.color: Theme.c.border }
    header: Text {
        text: dialog.title
        padding: Theme.s4
        color: Theme.c.text
        font.pixelSize: Theme.fontTitle
        font.family: Theme.fontFamily
        font.weight: Font.DemiBold
    }
    function ask(title, message, details, confirmText, danger, callback, token, cancelCallback) {
        dialog.onCancel = cancelCallback || null
        dialog.title = title
        dialog.message = message
        dialog.details = details || []
        dialog.confirmText = confirmText || "Confirm"
        dialog.danger = !!danger
        dialog.onAccept = callback
        dialog.requiredToken = token || ""
        tokenField.text = ""
        open()
    }
    contentItem: ColumnLayout {
        spacing: Theme.s3
        Text { text: dialog.message; wrapMode: Text.WordWrap; color: Theme.c.text; font.pixelSize: Theme.fontBody; font.family: Theme.fontFamily; Layout.fillWidth: true }
        Rectangle {
            visible: dialog.details.length > 0
            Layout.fillWidth: true
            Layout.preferredHeight: Math.min(detailsText.implicitHeight + Theme.s3 * 2, 260)
            color: Theme.c.background
            radius: Theme.radiusSmall
            border.color: Theme.c.border
            B.ScrollView {
                anchors.fill: parent
                anchors.margins: Theme.s2
                Text {
                    id: detailsText
                    text: dialog.details.join("\n")
                    color: Theme.c.text
                    font.family: Theme.monoFamily
                    font.pixelSize: Theme.fontSmall
                }
            }
        }
        Text {
            visible: dialog.requiredToken.length > 0
            text: "Type <b>" + dialog.requiredToken + "</b> to confirm."
            textFormat: Text.StyledText
            color: Theme.c.warning
            font.pixelSize: Theme.fontBody
            font.family: Theme.fontFamily
        }
        NxTextField { id: tokenField; visible: dialog.requiredToken.length > 0; Layout.fillWidth: true; placeholderText: dialog.requiredToken }
        RowLayout {
            Layout.alignment: Qt.AlignRight
            NxButton { text: "Cancel"; onClicked: { const cb = dialog.onCancel; dialog.reject(); if (cb) cb() } }
            NxButton {
                text: dialog.confirmText
                variant: dialog.danger ? "danger" : "primary"
                enabled: dialog.requiredToken.length === 0 || tokenField.text === dialog.requiredToken
                onClicked: { const cb = dialog.onAccept; dialog.accept(); if (cb) cb(tokenField.text) }
            }
        }
    }
}
