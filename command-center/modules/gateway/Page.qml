import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Dialogs
import QtQuick.Layouts
import Nexus.Design

Item {
    id: page
    property var controller
    property var confirm
    property string intent: ""
    readonly property var d: controller ? controller.data : ({})
    readonly property var st: d.status || null
    readonly property var route: routeTable.currentRow
    Component.onCompleted: { if (intent === "gateway.apply") Qt.callLater(askApply); else if (intent === "gateway.test") controller.testNginx() }
    function askApply() { confirm.ask("Apply gateway configuration", "Approved routes are rendered, the previous configuration is backed up, and NGINX is reloaded only if 'nginx -t' passes. On failure the previous configuration is restored automatically.", (d.routes || []).filter(r => r.approved && r.enabled).map(r => r.hostname + r.path_prefix + " → " + r.backend_host + ":" + r.backend_port + "  [" + r.tls + ", " + r.access + "]"), "Apply", false, () => controller.apply()) }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: Theme.s5
        spacing: Theme.s3
        NxPageHeader {
            title: "Gateway"
            subtitle: "Native NGINX on this host. Routes in /etc/nexusos/gateway/routes, generated configuration kept separately."
            NxButton { admin: true; text: "Test config"; enabled: d.agent; onClicked: controller.testNginx() }
            NxButton { admin: true; text: "Roll back"; enabled: d.agent; onClicked: confirm.ask("Roll back", "Restore the most recent backup of the generated configuration (only if it passes nginx -t).", [], "Roll back", true, () => controller.rollback()) }
            NxButton { admin: true; text: "Apply"; variant: "primary"; enabled: d.agent; onClicked: page.askApply() }
        }
        NxBanner { kind: "warning"; text: d.agent ? "" : "The management agent is not installed: routes can be viewed but not changed." }
        NxBanner { kind: "warning"; text: st && !st.nginx_installed ? "NGINX is not installed. Install the nexusos-gateway package (Private Cloud Host / Infrastructure profiles)." : "" }
        NxErrorState { message: controller ? controller.error : ""; onRetry: controller.refresh() }
        RowLayout {
            Layout.fillWidth: true
            NxMetric { label: "NGINX"; value: st ? st.nginx_state : "…"; status: st && st.nginx_state === "active" ? "ok" : "warn" }
            NxMetric { label: "Routes"; value: st ? st.routes_active + " active" : "…"; detail: st ? st.routes_pending + " pending approval" : ""; status: st && st.routes_pending ? "warn" : "" }
            NxMetric { label: "Certificates needing attention"; value: st ? String(st.certificates_expiring) : "…"; status: st && st.certificates_expiring ? "warn" : "ok" }
            NxMetric { label: "Last applied"; value: st && st.last_applied ? new Date(st.last_applied * 1000).toLocaleString(Qt.locale(), Locale.ShortFormat) : "never" }
        }
        NxTabBar { id: tabs; Layout.fillWidth: true; tabs: ["Routes", "Certificates", "Logs", "Output"] }
        StackLayout {
            currentIndex: tabs.currentIndex
            Layout.fillWidth: true
            Layout.fillHeight: true
            ColumnLayout {
                NxTable {
                    id: routeTable
                    Layout.fillWidth: true; Layout.fillHeight: true
                    rows: d.routes || []
                    emptyText: "No routes. Add one, or install a Nexus application and propose its route."
                    columns: [
                        { title: "Hostname", width: 0.25, format: r => r.hostname + (r.path_prefix !== "/" ? r.path_prefix : "") },
                        { title: "Backend", width: 0.22, format: r => r.backend_scheme + "://" + r.backend_host + ":" + r.backend_port, mono: true },
                        { title: "TLS", role: "tls", width: 0.12 },
                        { title: "Access", role: "access", width: 0.1 },
                        { title: "State", width: 0.16, format: r => !r.approved ? "pending approval" : r.enabled ? "approved" : "disabled" },
                        { title: "Backend check", width: 0.15, format: r => d.checks && d.checks[r.id] ? (d.checks[r.id].ok ? "ok " + d.checks[r.id].status_code + " (" + d.checks[r.id].latency_ms + " ms)" : (d.checks[r.id].error || "HTTP " + d.checks[r.id].status_code)) : "" }
                    ]
                }
                RowLayout {
                    NxButton { admin: true; text: "Add route"; enabled: d.agent; onClicked: { routeDialog.load(null); routeDialog.open() } }
                    NxButton { admin: true; text: "Edit"; enabled: !!(d.agent && !!page.route); onClicked: { routeDialog.load(page.route); routeDialog.open() } }
                    NxButton { admin: true; text: "Approve"; variant: "primary"; enabled: !!(d.agent && page.route && !page.route.approved); onClicked: confirm.ask("Approve route", "Serve " + page.route.hostname + " (" + page.route.access + " access, TLS " + page.route.tls + ") after the next Apply?", [], "Approve", false, () => controller.approve(page.route.id)) }
                    NxButton { text: "Test backend"; enabled: !!page.route; onClicked: controller.testBackend(page.route.id) }
                    NxButton { admin: true; text: "Delete"; variant: "danger"; enabled: !!(d.agent && !!page.route); onClicked: confirm.ask("Delete route", "Delete " + page.route.hostname + "? It stops being served after the next Apply.", [], "Delete", true, () => controller.deleteRoute(page.route.id)) }
                }
            }
            ColumnLayout {
                NxTable {
                    Layout.fillWidth: true; Layout.fillHeight: true
                    rows: d.certs || []
                    emptyText: "No certificates"
                    columns: [{ title: "Name", role: "name", width: 0.2 }, { title: "Source", role: "source", width: 0.13 }, { title: "Names", width: 0.3, format: r => r.sans.join(", ") }, { title: "Expires", width: 0.2, format: r => r.not_after.slice(0, 10) + " (" + r.days_left + " d)" }, { title: "Status", role: "status", width: 0.17 }]
                }
                RowLayout {
                    ComboBox { id: certMode; model: ["internal-ca", "self-signed", "letsencrypt"] }
                    NxTextField { id: certName; placeholderText: "certificate name"; Layout.preferredWidth: 160 }
                    NxTextField { id: certHosts; placeholderText: "hostnames (space separated)"; Layout.fillWidth: true }
                    NxTextField { id: certEmail; visible: certMode.currentText === "letsencrypt"; placeholderText: "contact e-mail" }
                    NxButton { admin: true; text: "Issue"; enabled: !!(d.agent && certName.text && certHosts.text); onClicked: controller.issueCertificate(certMode.currentText, certName.text, certHosts.text, certEmail.text) }
                    NxButton { admin: true; text: "Renew due"; enabled: d.agent; onClicked: controller.renew() }
                }
                Text { text: "Let's Encrypt only works for public DNS names reachable on port 80 (.local / .lan / .internal names are refused). Internal-CA certificates need the NexusOS CA (/etc/nexusos/gateway/ca/ca.crt) trusted on clients."; wrapMode: Text.WordWrap; Layout.fillWidth: true; color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall }
                RowLayout {
                    NxTextField { id: impName; placeholderText: "import as name"; Layout.preferredWidth: 160 }
                    NxButton { text: "Certificate…"; onClicked: certFile.open() }
                    NxButton { text: "Private key…"; onClicked: keyFile.open() }
                    NxButton { admin: true; text: "Import"; enabled: !!(d.agent && impName.text && certFile.selectedFile.toString() && keyFile.selectedFile.toString()); onClicked: controller.importCertificate(impName.text, certFile.selectedFile.toString(), keyFile.selectedFile.toString()) }
                    FileDialog { id: certFile; nameFilters: ["PEM (*.pem *.crt)"] }
                    FileDialog { id: keyFile; nameFilters: ["PEM key (*.pem *.key)"] }
                }
            }
            ColumnLayout {
                RowLayout { NxButton { text: "Error log"; onClicked: controller.loadLogs("error") } NxButton { text: "Access log"; onClicked: controller.loadLogs("access") } }
                NxLogView { Layout.fillWidth: true; Layout.fillHeight: true; text: d.logs || "" }
            }
            NxLogView { text: d.output || "" }
        }
    }

    Dialog {
        id: routeDialog
        title: "Gateway route"
        modal: true
        anchors.centerIn: parent
        width: Math.min(page.width - 60, 640)
        property var base: null
        function load(r) {
            base = r
            rId.text = r ? r.id : ""; rHost.text = r ? r.hostname : ""; rPath.text = r ? r.path_prefix : "/"; rScheme.currentIndex = r && r.backend_scheme === "https" ? 1 : 0
            rBHost.text = r ? r.backend_host : "127.0.0.1"; rBPort.value = r ? r.backend_port : 8080; rTls.currentIndex = Math.max(0, ["none", "internal-ca", "self-signed", "letsencrypt", "imported"].indexOf(r ? r.tls : "internal-ca"))
            rCert.text = r && r.certificate ? r.certificate : ""; rAccess.currentIndex = ["lan", "localhost", "public"].indexOf(r ? r.access : "lan"); rWs.checked = r ? r.websocket : false; rRedirect.checked = r ? r.redirect_http : true; rPublicBackend.checked = r ? r.allow_public_backend : false
        }
        ColumnLayout {
            width: parent.width
            NxFormRow { label: "Route id"; NxTextField { id: rId; width: parent.width; placeholderText: "e.g. private-cloud" } }
            NxFormRow { label: "Hostname"; NxTextField { id: rHost; width: parent.width; placeholderText: "cloud.nexus.lan or cloud.example.com" } }
            NxFormRow { label: "Path prefix"; NxTextField { id: rPath; width: parent.width } }
            NxFormRow { label: "Backend"; RowLayout { ComboBox { id: rScheme; model: ["http", "https"] } NxTextField { id: rBHost; Layout.fillWidth: true } SpinBox { id: rBPort; from: 1; to: 65535; editable: true } } }
            NxFormRow { label: "TLS"; RowLayout { ComboBox { id: rTls; model: ["none", "internal-ca", "self-signed", "letsencrypt", "imported"] } NxTextField { id: rCert; placeholderText: "certificate name (default: hostname)"; Layout.fillWidth: true } } }
            NxFormRow { label: "Access"; ComboBox { id: rAccess; model: ["lan", "localhost", "public"] } }
            Text { visible: rAccess.currentText === "public"; text: "Public access exposes the application to anyone who can reach this host. Make sure it has authentication."; color: Theme.c.warning; wrapMode: Text.WordWrap; Layout.fillWidth: true; font.family: Theme.fontFamily }
            NxFormRow { label: "Options"; ColumnLayout { CheckBox { id: rWs; text: "WebSocket" } CheckBox { id: rRedirect; text: "Redirect HTTP to HTTPS" } CheckBox { id: rPublicBackend; text: "Allow a public backend address (not recommended)" } } }
            Text { text: "New and edited routes need approval and an Apply before NGINX serves them."; color: Theme.c.textSecondary; font.family: Theme.fontFamily; font.pixelSize: Theme.fontSmall }
        }
        footer: DialogButtonBox {
            NxButton { text: "Cancel"; DialogButtonBox.buttonRole: DialogButtonBox.RejectRole }
            NxButton { text: "Save"; variant: "primary"; onClicked: {
                controller.saveRoute(JSON.stringify({ id: rId.text, hostname: rHost.text, path_prefix: rPath.text, backend_scheme: rScheme.currentText, backend_host: rBHost.text, backend_port: rBPort.value,
                    tls: rTls.currentText, certificate: rCert.text || null, access: rAccess.currentText, websocket: rWs.checked, redirect_http: rRedirect.checked, allow_public_backend: rPublicBackend.checked,
                    approved: false, enabled: true, app_id: routeDialog.base ? routeDialog.base.app_id : null, description: routeDialog.base ? routeDialog.base.description : "" }))
                routeDialog.close() } }
        }
    }
}
