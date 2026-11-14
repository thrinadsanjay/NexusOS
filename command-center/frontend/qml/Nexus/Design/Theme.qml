pragma Singleton
import QtQuick

// NexusOS design system tokens (dark default + light). Dark values mirror
// branding/design-tokens.json and are checked by tests/command-center/test_design_system.py.
QtObject {
    id: theme
    property bool dark: typeof App !== "undefined" ? App.dark : true

    readonly property QtObject darkPalette: QtObject {
        readonly property color background: "#0B171B"
        readonly property color backgroundSecondary: "#123B40"
        readonly property color accent: "#31C6BD"
        readonly property color accentSecondary: "#C47750"
        readonly property color text: "#E8F1F2"
        readonly property color textSecondary: "#9EB3B7"
        readonly property color surface: "#142328"
        readonly property color surfaceElevated: "#1B3036"
        readonly property color border: "#29434A"
        readonly property color textOnAccent: "#0B171B"
        readonly property color positive: "#3DBE7A"
        readonly property color warning: "#D9A441"
        readonly property color negative: "#D9574F"
        // dashboard metric colours (categorical, tested for contrast on surface)
        readonly property color mCpu: "#31C6BD"
        readonly property color mMemory: "#3DBE7A"
        readonly property color mGpu: "#A38BF5"
        readonly property color mDisk: "#E0AE4A"
        readonly property color mVuln: "#E0625A"
        readonly property color mUpdates: "#5AA9E6"
        readonly property color mNetwork: "#3DBE7A"
        readonly property color mMounts: "#4FC3E0"
    }
    readonly property QtObject lightPalette: QtObject {
        readonly property color background: "#F4F8F9"
        readonly property color backgroundSecondary: "#E3EEF0"
        readonly property color accent: "#1E8F88"
        readonly property color accentSecondary: "#A85F3C"
        readonly property color text: "#0B171B"
        readonly property color textSecondary: "#4A6066"
        readonly property color surface: "#FFFFFF"
        readonly property color surfaceElevated: "#F9FCFC"
        readonly property color border: "#C9D8DB"
        readonly property color textOnAccent: "#FFFFFF"
        readonly property color positive: "#25864F"
        readonly property color warning: "#9A6B0F"
        readonly property color negative: "#B43C35"
        readonly property color mCpu: "#1E8F88"
        readonly property color mMemory: "#25864F"
        readonly property color mGpu: "#6E55D6"
        readonly property color mDisk: "#A87308"
        readonly property color mVuln: "#B9423A"
        readonly property color mUpdates: "#2B7BC0"
        readonly property color mNetwork: "#25864F"
        readonly property color mMounts: "#1B8FB0"
    }
    readonly property QtObject c: dark ? darkPalette : lightPalette

    // Typography (Inter UI, JetBrains Mono code; fallbacks resolved by fontconfig)
    readonly property string fontFamily: "Inter"
    readonly property string monoFamily: "JetBrains Mono"
    readonly property int fontSmall: 11
    readonly property int fontBody: 13
    readonly property int fontTitle: 16
    readonly property int fontDisplay: 22

    // Spacing scale (4 px grid), radii, sizes
    readonly property int s1: 4
    readonly property int s2: 8
    readonly property int s3: 12
    readonly property int s4: 16
    readonly property int s5: 24
    readonly property int s6: 32
    readonly property int radius: 8
    readonly property int radiusSmall: 4
    readonly property int controlHeight: 32
    readonly property int sidebarWidth: 232
    readonly property int animationMs: 120   // short, functional transitions only

    function statusColor(status) {
        switch (status) {
        case "ok": case "healthy": case "running": case "active": case "success": case "available": return c.positive
        case "warn": case "warning": case "partial": case "experimental": case "pending": return c.warning
        case "fail": case "error": case "failed": case "critical": case "expired": case "unhealthy": return c.negative
        case "info": return c.accent
        default: return c.textSecondary
        }
    }

    function bytes(n) {
        if (n === undefined || n === null || n < 0) return "n/a"
        const units = ["B", "KiB", "MiB", "GiB", "TiB"]
        let i = 0
        let v = n
        while (v >= 1024 && i < units.length - 1) { v /= 1024; i++ }
        return (i === 0 ? v : v.toFixed(1)) + " " + units[i]
    }

    function duration(seconds) {
        if (!seconds && seconds !== 0) return "n/a"
        const d = Math.floor(seconds / 86400), h = Math.floor(seconds % 86400 / 3600), m = Math.floor(seconds % 3600 / 60)
        return (d ? d + "d " : "") + h + "h " + m + "m"
    }
}
