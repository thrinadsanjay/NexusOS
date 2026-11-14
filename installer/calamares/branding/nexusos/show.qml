/* NexusOS installer slideshow (shown while the system is being installed).
 * Drawn in QML with the design tokens: no raster slides to maintain or translate as images. */
import QtQuick
import calamares.slideshow 1.0

Presentation {
    id: presentation

    readonly property color bg: "#0B171B"
    readonly property color surface: "#142328"
    readonly property color border: "#29434A"
    readonly property color text: "#E8F1F2"
    readonly property color muted: "#9EB3B7"
    readonly property color accent: "#31C6BD"
    readonly property color copper: "#C47750"

    Timer {
        interval: 12000
        running: presentation.activatedInCalamares
        repeat: true
        onTriggered: presentation.goToNextSlide()
    }

    component NexusSlide: Slide {
        id: slide
        property string kicker
        property string heading
        property var points: []
        Rectangle {
            anchors.fill: parent
            color: presentation.bg
            Column {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.margins: 48
                spacing: 14
                Text { text: slide.kicker; color: presentation.accent; font.family: "Inter"; font.pixelSize: 13; font.weight: Font.DemiBold; font.letterSpacing: 2; font.capitalization: Font.AllUppercase }
                Text { text: slide.heading; color: presentation.text; font.family: "Inter"; font.pixelSize: 28; font.weight: Font.DemiBold; wrapMode: Text.WordWrap; width: parent.width }
                Rectangle { width: 48; height: 3; radius: 1.5; color: presentation.copper }
                Repeater {
                    model: slide.points
                    Row {
                        required property string modelData
                        spacing: 12
                        Rectangle { width: 6; height: 6; radius: 3; color: presentation.accent; anchors.verticalCenter: parent.verticalCenter }
                        Text { text: modelData; color: presentation.muted; font.family: "Inter"; font.pixelSize: 16; wrapMode: Text.WordWrap; width: slide.width - 140 }
                    }
                }
            }
        }
    }

    NexusSlide {
        kicker: "Welcome to NexusOS"
        heading: "An engineering workstation built on Ubuntu 26.04 LTS"
        points: ["KDE Plasma 6 on Wayland with the Nexus theme", "Ubuntu's packages, kernel and security updates, unchanged", "Everything here is open source — crafted by Sanjay"]
    }
    NexusSlide {
        kicker: "Command Center"
        heading: "One native place to run the machine"
        points: ["Operations dashboard: CPU, memory, GPU, drives, updates and security fixes", "Software, services, storage, network, containers and the gateway", "Press Ctrl+K anywhere to search settings, packages and actions"]
    }
    NexusSlide {
        kicker: "Your account, your rights"
        heading: "Administrative tasks use your own sudo access"
        points: ["The account you create now is the administrator", "A password box appears when a task needs administrator rights", "Every administrative task is audited; nothing runs as root in the background"]
    }
    NexusSlide {
        kicker: "Build · Automate · Deploy"
        heading: "Development, infrastructure and local AI, when you want them"
        points: ["Terminal & SSH workspace with saved profiles and KDE Wallet credentials", "Docker, virtual machines and a native NGINX gateway with certificates", "Local AI with Ollama: nothing is downloaded unless you ask"]
    }
    NexusSlide {
        kicker: "Almost there"
        heading: "After the restart"
        points: ["Sign in, then open the Command Center from the dock", "Check Overview → System attention for updates", "Documentation: github.com/thrinadsanjay/NexusOS", "Thank you for trying NexusOS — Sanjay"]
    }

    function onActivate() { presentation.currentSlide = 0 }
    function onLeave() { }
}
