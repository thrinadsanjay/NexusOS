import QtQuick
import QtQuick.Controls.Basic as B
import QtQuick.Layouts

// Floating sudo password box. Shown when an administrative task needs the logged-in
// user's password (sudo without NOPASSWD). The password goes straight to sudo through
// App.submitPassword() and the field is cleared immediately; nothing is stored.
// A modal layer inside the window (scrim + card) rather than a Popup, so it also appears in
// `nexus-center --screenshots` captures.
Rectangle {
    id: prompt
    property string user: ""
    property string action: ""
    property string detail: ""
    property string error: ""
    property int attempt: 1
    signal submitted(string password)
    signal cancelled()

    readonly property bool opened: visible
    anchors.fill: parent
    visible: false
    z: 1000
    color: Qt.rgba(0, 0, 0, Theme.dark ? 0.55 : 0.3)
    MouseArea { anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.AllButtons; onWheel: wheel => wheel.accepted = true }  // modal
    function open() { visible = true }
    function close() { visible = false; field.text = "" }

    function ask(request) {
        user = request.user
        action = request.action
        detail = request.detail
        error = request.error
        attempt = request.attempt
        field.text = ""
        open()
        field.forceActiveFocus()
    }
    function finish(ok) {
        const value = field.text
        field.text = ""          // never keep the password in the UI
        close()
        if (ok) submitted(value); else cancelled()
    }

    Rectangle {
    id: card
    anchors.centerIn: parent
    width: 420
    implicitHeight: body.implicitHeight
    height: implicitHeight
    color: Theme.c.surfaceElevated
    radius: Theme.radius * 1.5
    border.color: Theme.c.border
    ColumnLayout {
        id: body
        width: parent.width
        spacing: 0
        RowLayout {
            Layout.fillWidth: true
            Layout.margins: Theme.s4
            spacing: Theme.s3
            Rectangle {
                width: 40; height: 40; radius: Theme.radius
                color: Qt.rgba(Theme.c.accent.r, Theme.c.accent.g, Theme.c.accent.b, 0.14)
                border.color: Qt.rgba(Theme.c.accent.r, Theme.c.accent.g, Theme.c.accent.b, 0.4)
                Item {  // padlock
                    anchors.centerIn: parent; width: 16; height: 18
                    Rectangle { x: 3; y: 0; width: 10; height: 12; radius: 5; color: "transparent"; border.color: Theme.c.accent; border.width: 2 }
                    Rectangle { x: 0; y: 7; width: 16; height: 11; radius: 2; color: Theme.c.accent }
                }
            }
            ColumnLayout {
                spacing: 2
                Layout.fillWidth: true
                Text { text: "Administrator password"; color: Theme.c.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontTitle; font.weight: Font.DemiBold }
                Text { text: "sudo · " + prompt.user; color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall }
            }
        }
        Rectangle { Layout.fillWidth: true; height: 1; color: Theme.c.border }
        ColumnLayout {
            Layout.fillWidth: true
            Layout.margins: Theme.s4
            spacing: Theme.s3
            Text {
                Layout.fillWidth: true
                wrapMode: Text.WordWrap
                textFormat: Text.StyledText
                text: "<b>" + prompt.action + "</b> needs administrator rights. Enter the password of <b>" + prompt.user + "</b>."
                color: Theme.c.text; font.family: Theme.fontFamily; font.pixelSize: Theme.fontBody
            }
            Rectangle {
                Layout.fillWidth: true
                implicitHeight: opText.implicitHeight + Theme.s2 * 2
                radius: Theme.radiusSmall
                color: Theme.c.background
                border.color: Theme.c.border
                Text { id: opText; anchors.fill: parent; anchors.margins: Theme.s2; text: "operation: " + prompt.detail; color: Theme.c.textSecondary; font.family: Theme.monoFamily; font.pixelSize: Theme.fontSmall; elide: Text.ElideRight }
            }
            NxTextField {
                id: field
                Layout.fillWidth: true
                echoMode: TextInput.Password
                passwordCharacter: "•"
                placeholderText: "Password"
                invalid: prompt.error.length > 0
                inputMethodHints: Qt.ImhSensitiveData | Qt.ImhNoPredictiveText | Qt.ImhNoAutoUppercase
                onAccepted: if (text.length) prompt.finish(true)
                Keys.onEscapePressed: prompt.finish(false)
            }
            Text {
                visible: prompt.error.length > 0
                text: prompt.error + (prompt.attempt > 1 ? "  (attempt " + prompt.attempt + " of 3)" : "")
                color: Theme.c.negative; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall
            }
            RowLayout {
                Layout.fillWidth: true
                Layout.topMargin: Theme.s1
                Text { text: "Verified by sudo; not stored."; color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall; Layout.fillWidth: true }
                NxButton { text: "Cancel"; onClicked: prompt.finish(false) }
                NxButton { text: "Authenticate"; variant: "primary"; enabled: field.text.length > 0; onClicked: prompt.finish(true) }
            }
        }
    }
}
}
