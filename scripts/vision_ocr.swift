import AppKit
import Foundation
import Vision

struct OCRWord: Codable {
    let text: String
    let x0: Double
    let y0: Double
    let x1: Double
    let y1: Double
    let confidence: Float
}

guard CommandLine.arguments.count == 2 else {
    fputs("usage: vision_ocr IMAGE\n", stderr)
    exit(2)
}

let imageURL = URL(fileURLWithPath: CommandLine.arguments[1])
guard
    let image = NSImage(contentsOf: imageURL),
    let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil)
else {
    fputs("unable to load image\n", stderr)
    exit(1)
}

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.recognitionLanguages = ["zh-Hans", "en-US"]
request.usesLanguageCorrection = false

try VNImageRequestHandler(cgImage: cgImage).perform([request])

let words = (request.results ?? []).compactMap { observation -> OCRWord? in
    guard let candidate = observation.topCandidates(1).first else { return nil }
    let box = observation.boundingBox
    return OCRWord(
        text: candidate.string,
        x0: box.minX,
        y0: 1 - box.maxY,
        x1: box.maxX,
        y1: 1 - box.minY,
        confidence: candidate.confidence
    )
}

let encoder = JSONEncoder()
let data = try encoder.encode(words)
FileHandle.standardOutput.write(data)
