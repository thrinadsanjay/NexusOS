import QtQuick

// Small trend line with a soft area fill. values: list of numbers (oldest first).
// minValue/maxValue fix the scale (e.g. 0..100 for percentages); otherwise it auto-scales.
Canvas {
    id: spark
    property var values: []
    property color color: Theme.c.accent
    property real minValue: NaN
    property real maxValue: NaN
    property bool fill: true
    implicitHeight: 26
    implicitWidth: 120
    renderStrategy: Canvas.Cooperative
    onValuesChanged: requestPaint()
    onColorChanged: requestPaint()
    onWidthChanged: requestPaint()
    onHeightChanged: requestPaint()
    onPaint: {
        const ctx = getContext("2d")
        ctx.reset()
        const v = values || []
        if (v.length < 2 || width < 4)
            return
        let lo = isNaN(minValue) ? Math.min.apply(null, v) : minValue
        let hi = isNaN(maxValue) ? Math.max.apply(null, v) : maxValue
        if (isNaN(minValue)) lo = lo * 0.85
        if (hi - lo < 1e-9) hi = lo + 1
        const step = width / (v.length - 1)
        const y = val => 1 + (height - 2) * (1 - (Math.min(Math.max(val, lo), hi) - lo) / (hi - lo))
        ctx.beginPath()
        ctx.moveTo(0, y(v[0]))
        for (let i = 1; i < v.length; i++)
            ctx.lineTo(i * step, y(v[i]))
        if (fill) {
            ctx.save()
            ctx.lineTo(width, height)
            ctx.lineTo(0, height)
            ctx.closePath()
            const g = ctx.createLinearGradient(0, 0, 0, height)
            g.addColorStop(0, Qt.rgba(spark.color.r, spark.color.g, spark.color.b, 0.32))
            g.addColorStop(1, Qt.rgba(spark.color.r, spark.color.g, spark.color.b, 0.0))
            ctx.fillStyle = g
            ctx.fill()
            ctx.restore()
            ctx.beginPath()
            ctx.moveTo(0, y(v[0]))
            for (let j = 1; j < v.length; j++)
                ctx.lineTo(j * step, y(v[j]))
        }
        ctx.lineWidth = 1.6
        ctx.lineJoin = "round"
        ctx.strokeStyle = spark.color
        ctx.stroke()
    }
}
