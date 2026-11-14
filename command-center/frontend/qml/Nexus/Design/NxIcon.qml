import QtQuick

// Line icons (24×24, 1.8 px stroke) drawn from inline SVG paths, recoloured per theme.
Item {
    id: icon
    property string name: "info"
    property color color: Theme.c.textSecondary
    property int size: 18
    implicitWidth: size
    implicitHeight: size

    readonly property var paths: ({
        cpu: '<rect x="6" y="6" width="12" height="12" rx="2"/><rect x="9.5" y="9.5" width="5" height="5"/><path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3"/>',
        memory: '<rect x="3" y="7" width="18" height="10" rx="1.5"/><path d="M7 7v10M11 7v10M15 7v10M5 20v-3M19 20v-3"/>',
        gpu: '<rect x="2" y="6" width="20" height="12" rx="2"/><circle cx="15" cy="12" r="3"/><path d="M6 10h4M6 14h4M5 18v2M10 18v2"/>',
        disk: '<ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
        shield: '<path d="M12 3 4 6v6c0 4.5 3.4 8.2 8 9 4.6-.8 8-4.5 8-9V6z"/><path d="M12 8v5M12 16v.5"/>',
        update: '<path d="M12 3v12M7 10l5 5 5-5"/><path d="M4 17v3h16v-3"/>',
        network: '<rect x="9" y="3" width="6" height="5" rx="1"/><rect x="3" y="16" width="6" height="5" rx="1"/><rect x="15" y="16" width="6" height="5" rx="1"/><path d="M12 8v4M6 16v-4h12v4"/>',
        mount: '<path d="M4 6h16v5H4zM4 13h16v5H4z"/><path d="M7 8.5h.01M7 15.5h.01"/>',
        services: '<rect x="3" y="4" width="18" height="6" rx="1.5"/><rect x="3" y="14" width="18" height="6" rx="1.5"/><path d="M7 7h.01M7 17h.01"/>',
        infra: '<path d="M12 3 3 7.5v9L12 21l9-4.5v-9z"/><path d="M12 12 3 7.5M12 12l9-4.5M12 12v9"/>',
        activity: '<path d="M6 3h9l4 4v14H6z"/><path d="M14 3v5h5M9 12h7M9 16h5"/>',
        chart: '<path d="M4 20V10M9 20V4M14 20v-7M19 20v-11"/>',
        backup: '<path d="M12 3 4 6v6c0 4.5 3.4 8.2 8 9 4.6-.8 8-4.5 8-9V6z"/><path d="m9 12 2 2 4-4"/>',
        cert: '<circle cx="12" cy="9" r="5"/><path d="m9 13.5-2 7.5 5-3 5 3-2-7.5"/>',
        alert: '<path d="M12 3 2 20h20z"/><path d="M12 10v4M12 17v.5"/>',
        check: '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
        cross: '<circle cx="12" cy="12" r="9"/><path d="m9 9 6 6M15 9l-6 6"/>',
        warn: '<circle cx="12" cy="12" r="9"/><path d="M12 8v5M12 16h.01"/>',
        info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
        docker: '<path d="M3 12h16c1 0 2-.5 2.5-1.5M5 12c0 4 3 7 8 7 4 0 7-2.5 8-6"/><path d="M6 9h3v3H6zM9 9h3v3H9zM12 9h3v3h-3zM9 6h3v3H9z"/>',
        vm: '<rect x="3" y="4" width="18" height="12" rx="1.5"/><path d="M8 20h8M12 16v4M7 8h6"/>',
        apps: '<path d="M12 3 2 8l10 5 10-5z"/><path d="m2 13 10 5 10-5"/>',
        calendar: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
        chevron: '<path d="m9 6 6 6-6 6"/>',
        refresh: '<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/>',
        lock: '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>'
    })
    Image {
        anchors.fill: parent
        sourceSize: Qt.size(icon.size * 2, icon.size * 2)
        fillMode: Image.PreserveAspectFit
        smooth: true
        source: "data:image/svg+xml;charset=utf-8," + encodeURIComponent(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="' + icon.color
        + '" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">' + (icon.paths[icon.name] || icon.paths.info) + '</svg>')
    }
}
