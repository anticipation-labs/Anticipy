import SwiftUI
import AppKit

// The REAL "Anticipy Execute" shell. Opening the app boots the local engine + web UI
// (boot.sh) and then opens the actual owner interface in the default browser. This
// replaces the inert scaffold — opening the app now delivers the working flow (input
// doors, task board, approve/do, receipts).
//
// (An embedded native webview would need full Xcode/WebKit; this machine has only the
// Command Line Tools, so the interface opens in the browser. The flow is identical.)

private let UI_URL = "http://127.0.0.1:3000"

@MainActor
final class Booter: ObservableObject {
    enum Phase { case booting, ready, failed }
    @Published var phase: Phase = .booting
    @Published var status = "Starting Anticipy Execute…"
    private var opened = false

    func boot() {
        Task.detached(priority: .userInitiated) { [weak self] in
            await self?.set("Starting the engine and interface…")
            if await Booter.reachable(UI_URL) { await self?.ready(); return }
            if let path = Bundle.main.url(forResource: "boot", withExtension: "sh")?.path {
                let p = Process()
                p.executableURL = URL(fileURLWithPath: "/bin/bash")
                p.arguments = [path]
                try? p.run()
                p.waitUntilExit()
            }
            for _ in 0..<60 {
                if await Booter.reachable(UI_URL) { await self?.ready(); return }
                try? await Task.sleep(nanoseconds: 1_000_000_000)
            }
            await self?.fail()
        }
    }

    func openInterface() {
        if let u = URL(string: UI_URL) { NSWorkspace.shared.open(u) }
    }

    private func set(_ s: String) { status = s }
    private func ready() {
        phase = .ready
        status = "Anticipy Execute is running — your interface is open in your browser."
        if !opened { opened = true; openInterface() }
    }
    private func fail() {
        phase = .failed
        status = "Couldn't start the interface automatically. The engine + UI launch from the repo on this Mac; check that it's present, then reopen."
    }

    static func reachable(_ url: String) async -> Bool {
        guard let u = URL(string: url) else { return false }
        var req = URLRequest(url: u); req.timeoutInterval = 2
        return await withCheckedContinuation { cont in
            URLSession.shared.dataTask(with: req) { _, resp, _ in
                cont.resume(returning: ((resp as? HTTPURLResponse)?.statusCode ?? 0) > 0)
            }.resume()
        }
    }
}

struct WebRoot: View {
    @StateObject private var booter = Booter()

    var body: some View {
        VStack(spacing: 18) {
            HStack(spacing: 10) {
                Circle().fill(DS.accent).frame(width: 12, height: 12)
                Text("Anticipy Execute").font(DS.title()).foregroundColor(DS.textPrimary)
            }
            if booter.phase == .booting { ProgressView().controlSize(.small) }
            Text(booter.status)
                .font(DS.body(.regular))
                .foregroundColor(DS.textSecondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 460)
            if booter.phase == .ready {
                Button("Open interface") { booter.openInterface() }
                    .controlSize(.large)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(DS.bg)
        .preferredColorScheme(.dark)
        .onAppear { booter.boot() }
    }
}
