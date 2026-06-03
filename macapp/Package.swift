// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "AnticipyApp",
    platforms: [.macOS(.v13)],
    targets: [
        .executableTarget(
            name: "AnticipyApp",
            path: "Sources/AnticipyApp"
        )
    ]
)
