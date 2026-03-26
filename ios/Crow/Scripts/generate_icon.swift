import Cocoa

// MARK: - Shared helpers

let colorSpace = CGColorSpaceCreateDeviceRGB()

func purpleGradientBg(_ ctx: CGContext, size: CGFloat) {
    let gradColors = [
        CGColor(red: 0.30, green: 0.12, blue: 0.48, alpha: 1.0),
        CGColor(red: 0.12, green: 0.04, blue: 0.22, alpha: 1.0)
    ] as CFArray
    if let gradient = CGGradient(colorsSpace: colorSpace, colors: gradColors, locations: [0, 1]) {
        ctx.drawLinearGradient(gradient,
            start: CGPoint(x: size/2, y: size),
            end: CGPoint(x: size/2, y: 0), options: [])
    }
}

func writePNG(_ rep: NSBitmapImageRep, to path: String) {
    let data = rep.representation(using: .png, properties: [:])!
    try! data.write(to: URL(fileURLWithPath: path))
}

func makeRep(size: Int) -> NSBitmapImageRep {
    let rep = NSBitmapImageRep(
        bitmapDataPlanes: nil, pixelsWide: size, pixelsHigh: size,
        bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
        colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)!
    rep.size = NSSize(width: size, height: size)
    return rep
}

func stripAlpha(from rep: NSBitmapImageRep) -> NSBitmapImageRep {
    let w = rep.pixelsWide, h = rep.pixelsHigh
    let ctx = CGContext(data: nil, width: w, height: h, bitsPerComponent: 8, bytesPerRow: 0,
        space: CGColorSpaceCreateDeviceRGB(),
        bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue)!
    ctx.draw(rep.cgImage!, in: CGRect(x: 0, y: 0, width: w, height: h))
    return NSBitmapImageRep(cgImage: ctx.makeImage()!)
}

// MARK: - Bird drawing

struct Bird {
    let x: CGFloat, y: CGFloat, span: CGFloat, angle: CGFloat, alpha: CGFloat
}

func drawBird(ctx: CGContext, bird: Bird, size: CGFloat) {
    let bx = bird.x * size
    let by = bird.y * size
    let span = bird.span * size

    ctx.saveGState()
    ctx.translateBy(x: bx, y: by)
    ctx.rotate(by: bird.angle)

    let path = CGMutablePath()
    let wingDroop = span * 0.22
    let bodyDrop = span * 0.16
    let thickness = span * 0.09

    path.move(to: CGPoint(x: -span/2, y: wingDroop))
    path.addQuadCurve(to: CGPoint(x: 0, y: thickness),
                      control: CGPoint(x: -span * 0.20, y: wingDroop + thickness * 0.5))
    path.addQuadCurve(to: CGPoint(x: span/2, y: wingDroop),
                      control: CGPoint(x: span * 0.20, y: wingDroop + thickness * 0.5))
    path.addQuadCurve(to: CGPoint(x: span * 0.06, y: -thickness * 0.3),
                      control: CGPoint(x: span * 0.22, y: wingDroop - thickness * 0.8))
    path.addLine(to: CGPoint(x: 0, y: -bodyDrop))
    path.addLine(to: CGPoint(x: -span * 0.06, y: -thickness * 0.3))
    path.addQuadCurve(to: CGPoint(x: -span/2, y: wingDroop),
                      control: CGPoint(x: -span * 0.22, y: wingDroop - thickness * 0.8))
    path.closeSubpath()

    ctx.setFillColor(CGColor(red: 1, green: 1, blue: 1, alpha: bird.alpha))
    ctx.addPath(path)
    ctx.fillPath()

    ctx.restoreGState()
}

// MARK: - Mesh flock

func drawMeshFlock(ctx: CGContext, size: CGFloat) {
    purpleGradientBg(ctx, size: size)

    let s = size

    let birds: [Bird] = [
        // Core cluster
        Bird(x: 0.45, y: 0.58, span: 0.19, angle: 0.04, alpha: 1.0),
        Bird(x: 0.62, y: 0.52, span: 0.15, angle: 0.08, alpha: 0.95),
        Bird(x: 0.35, y: 0.48, span: 0.14, angle: -0.06, alpha: 0.90),
        Bird(x: 0.55, y: 0.42, span: 0.13, angle: 0.02, alpha: 0.88),
        Bird(x: 0.40, y: 0.68, span: 0.13, angle: -0.03, alpha: 0.85),
        // Outer ring
        Bird(x: 0.75, y: 0.42, span: 0.10, angle: 0.12, alpha: 0.70),
        Bird(x: 0.22, y: 0.58, span: 0.10, angle: -0.10, alpha: 0.70),
        Bird(x: 0.58, y: 0.72, span: 0.10, angle: 0.05, alpha: 0.68),
        Bird(x: 0.28, y: 0.38, span: 0.09, angle: -0.14, alpha: 0.60),
        Bird(x: 0.72, y: 0.65, span: 0.09, angle: 0.10, alpha: 0.60),
        // Distant outliers
        Bird(x: 0.15, y: 0.45, span: 0.06, angle: -0.08, alpha: 0.40),
        Bird(x: 0.85, y: 0.55, span: 0.06, angle: 0.15, alpha: 0.40),
        Bird(x: 0.50, y: 0.30, span: 0.07, angle: 0.0, alpha: 0.42),
        Bird(x: 0.68, y: 0.30, span: 0.06, angle: 0.06, alpha: 0.38),
        Bird(x: 0.25, y: 0.72, span: 0.06, angle: -0.05, alpha: 0.38),
    ]

    // Mesh lines
    let birdCenters = birds.map { CGPoint(x: $0.x * s, y: $0.y * s) }
    let maxDist = s * 0.25

    for i in 0..<birdCenters.count {
        for j in (i+1)..<birdCenters.count {
            let dx = birdCenters[i].x - birdCenters[j].x
            let dy = birdCenters[i].y - birdCenters[j].y
            let dist = sqrt(dx*dx + dy*dy)
            if dist < maxDist {
                let falloff = 1.0 - dist / maxDist
                let lineAlpha = falloff * falloff * 0.35
                ctx.setStrokeColor(CGColor(red: 0.75, green: 0.58, blue: 1.0, alpha: lineAlpha))
                ctx.setLineWidth(s * 0.003 * falloff + s * 0.001)
                ctx.move(to: birdCenters[i])
                ctx.addLine(to: birdCenters[j])
                ctx.strokePath()
            }
        }
    }

    // Dots at nodes
    for (idx, bird) in birds.enumerated() {
        let dotR = s * 0.006 + bird.span * s * 0.03
        let dotAlpha = bird.alpha * 0.5
        ctx.setFillColor(CGColor(red: 0.82, green: 0.68, blue: 1.0, alpha: dotAlpha))
        let p = birdCenters[idx]
        ctx.fillEllipse(in: CGRect(x: p.x - dotR, y: p.y - dotR, width: dotR * 2, height: dotR * 2))
    }

    // Birds on top
    for bird in birds {
        drawBird(ctx: ctx, bird: bird, size: s)
    }
}

// MARK: - Rendering helpers

/// Render edge-to-edge (iOS style)
func renderEdgeToEdge(pixelSize: Int) -> NSBitmapImageRep {
    let rep = makeRep(size: pixelSize)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
    if let ctx = NSGraphicsContext.current?.cgContext {
        ctx.setAllowsAntialiasing(true)
        ctx.setShouldAntialias(true)
        ctx.interpolationQuality = .high
        drawMeshFlock(ctx: ctx, size: CGFloat(pixelSize))
    }
    NSGraphicsContext.restoreGraphicsState()
    return rep
}

/// Render with macOS inset (824/1024 ratio)
func renderMacIcon(pixelSize: Int) -> NSBitmapImageRep {
    let canvas = CGFloat(pixelSize)
    let iconSize = canvas * (824.0 / 1024.0)
    let inset = (canvas - iconSize) / 2.0

    let rep = makeRep(size: pixelSize)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
    if let ctx = NSGraphicsContext.current?.cgContext {
        ctx.setAllowsAntialiasing(true)
        ctx.setShouldAntialias(true)
        ctx.interpolationQuality = .high

        // Draw into inset area with clipped rounded rect
        let bgRect = CGRect(x: inset, y: inset, width: iconSize, height: iconSize)
        let cornerR = iconSize * 0.18
        let bgPath = CGPath(roundedRect: bgRect, cornerWidth: cornerR, cornerHeight: cornerR, transform: nil)

        // Drop shadow
        ctx.saveGState()
        ctx.setShadow(offset: CGSize(width: 0, height: -canvas * 0.01), blur: canvas * 0.03,
                      color: CGColor(red: 0, green: 0, blue: 0, alpha: 0.4))
        ctx.setFillColor(CGColor(red: 0.2, green: 0.08, blue: 0.35, alpha: 1.0))
        ctx.addPath(bgPath)
        ctx.fillPath()
        ctx.restoreGState()

        // Clip to rounded rect and draw icon
        ctx.saveGState()
        ctx.addPath(bgPath)
        ctx.clip()
        // Translate and scale to draw within the inset
        ctx.translateBy(x: inset, y: inset)
        ctx.scaleBy(x: iconSize / canvas, y: iconSize / canvas)
        drawMeshFlock(ctx: ctx, size: canvas)
        ctx.restoreGState()
    }
    NSGraphicsContext.restoreGraphicsState()
    return rep
}

// MARK: - Generate all icons

let baseDir = "/Users/niall/work/erdo/crow"
let appIconDir = "\(baseDir)/ios/Crow/Crow/Assets.xcassets/AppIcon.appiconset"
let webPublicDir = "\(baseDir)/web/public"

// Create web/public if needed
try! FileManager.default.createDirectory(atPath: webPublicDir, withIntermediateDirectories: true)

// --- iOS: 1024x1024 edge-to-edge, no alpha ---
let iosRep = stripAlpha(from: renderEdgeToEdge(pixelSize: 1024))
writePNG(iosRep, to: "\(appIconDir)/icon_1024x1024.png")
print("iOS: icon_1024x1024.png")

// --- macOS (Mac Catalyst): all standard sizes ---
let macSizes: [(pt: Int, scale: Int)] = [
    (16, 1), (16, 2),
    (32, 1), (32, 2),
    (128, 1), (128, 2),
    (256, 1), (256, 2),
    (512, 1), (512, 2),
]

for (pt, scale) in macSizes {
    let px = pt * scale
    let name = "icon_\(pt)x\(pt)@\(scale)x.png"
    let rep = renderMacIcon(pixelSize: px)
    writePNG(rep, to: "\(appIconDir)/\(name)")
    print("macOS: \(name) (\(px)x\(px)px)")
}

// --- Web: favicon.png (32x32) and apple-touch-icon (180x180) ---
let favicon32 = stripAlpha(from: renderEdgeToEdge(pixelSize: 32))
writePNG(favicon32, to: "\(webPublicDir)/favicon.png")
print("Web: favicon.png (32x32)")

let favicon16 = stripAlpha(from: renderEdgeToEdge(pixelSize: 16))
writePNG(favicon16, to: "\(webPublicDir)/favicon-16x16.png")
print("Web: favicon-16x16.png")

let appleTouchIcon = stripAlpha(from: renderEdgeToEdge(pixelSize: 180))
writePNG(appleTouchIcon, to: "\(webPublicDir)/apple-touch-icon.png")
print("Web: apple-touch-icon.png (180x180)")

let favicon192 = stripAlpha(from: renderEdgeToEdge(pixelSize: 192))
writePNG(favicon192, to: "\(webPublicDir)/icon-192.png")
print("Web: icon-192.png")

let favicon512 = stripAlpha(from: renderEdgeToEdge(pixelSize: 512))
writePNG(favicon512, to: "\(webPublicDir)/icon-512.png")
print("Web: icon-512.png")

print("\nDone! All icons generated.")
