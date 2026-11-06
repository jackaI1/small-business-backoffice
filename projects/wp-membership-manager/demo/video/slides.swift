import AppKit
let slides = [("Membership Manager", "A practical WordPress demo", "Members, renewals and campaigns"), ("Choose an audience", "Consent comes first", "Preview a renewal segment before sending."), ("Send and review", "HTML reminders in batches", "Track accepted messages and approximate opens."), ("Share the numbers", "Download an aggregate CSV", "Renewals, sponsorships and campaign results.")]
for (index, slide) in slides.enumerated() {
 let image = NSImage(size: NSSize(width: 1280, height: 720)); image.lockFocus()
 NSColor(red: 0.04, green: 0.12, blue: 0.18, alpha: 1).setFill(); NSRect(x: 0, y: 0, width: 1280, height: 720).fill()
 NSColor(red: 0.24, green: 0.82, blue: 0.67, alpha: 1).setFill(); NSRect(x: 95, y: 556, width: 90, height: 8).fill()
 func draw(_ text: String, _ y: CGFloat, _ size: CGFloat, _ color: NSColor, _ weight: NSFont.Weight) { (text as NSString).draw(at: NSPoint(x: 95, y: y), withAttributes: [.font: NSFont.systemFont(ofSize: size, weight: weight), .foregroundColor: color]) }
 draw("WP MEMBERSHIP MANAGER  /  0\(index + 1)", 600, 23, .white, .medium); draw(slide.0, 405, 64, .white, .bold); draw(slide.1, 328, 37, NSColor(red: 0.38, green: 0.91, blue: 0.75, alpha: 1), .medium); draw(slide.2, 237, 28, .white, .regular)
 image.unlockFocus(); let bitmap = NSBitmapImageRep(data: image.tiffRepresentation!)!; try! bitmap.representation(using: .png, properties: [:])!.write(to: URL(fileURLWithPath: "/tmp/wpmm-video-work/slide\(index).png"))
}
