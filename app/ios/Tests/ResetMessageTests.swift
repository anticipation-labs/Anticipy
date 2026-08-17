import Foundation

// Checks that a refusal from the password-reset route reaches the person with
// the SERVER's sentence on it. AnticipyBackend.swift is pure Foundation, so the
// real file compiles and runs here — no simulator, no scheme, no signing. The
// network is the only thing stubbed, by a URLProtocol that URLSession.shared
// honours. See app/ios/Tests/run_reset_message_tests.sh.
//
// /auth/reset/confirm has three different refusals and only one of them is
// about the code. Collapsing them is how a person holding a code that arrived
// seconds ago gets told the code is wrong, asks for another, and after five
// requests in an hour hits the silent throttle — locked out, with every screen
// naming the wrong reason.

/// Answers every request with whatever the current case set up.
final class StubServer: URLProtocol {
    static var status = 200
    static var body = Data()

    static func answer(_ status: Int, _ body: String) {
        StubServer.status = status
        StubServer.body = Data(body.utf8)
    }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let response = HTTPURLResponse(url: request.url!, statusCode: StubServer.status,
                                       httpVersion: "HTTP/1.1", headerFields: nil)!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: StubServer.body)
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@main
enum Cases {
    static var failures: [String] = []
    static var checks = 0

    static func expect(_ actual: String?, _ wanted: String?, _ why: String) {
        checks += 1
        if actual != wanted {
            failures.append("\(why)\n      wanted: \(wanted ?? "nil")\n      got:    \(actual ?? "nil")")
        }
    }

    /// What confirmPasswordReset would put on the screen for this reply.
    static func shownFor(_ status: Int, _ body: String) async -> String? {
        StubServer.answer(status, body)
        let backend = AnticipyBackend(baseURL: URL(string: "https://stub.invalid")!,
                                      deviceID: "test", authToken: "t", accountID: "a")
        do {
            try await backend.confirmPasswordReset(email: "a@b.co", code: "123456",
                                                   password: "hunter2hunter2")
            return nil
        } catch let e as AnticipyBackend.MessageError {
            return e.message
        } catch {
            return "TRANSPORT: \(error)"
        }
    }

    static func main() async {
        URLProtocol.registerClass(StubServer.self)
        let canned = "That code isn't right, or it has expired. Ask for a new one."

        // The 500: the code was RIGHT and the owners record failed to save.
        // Telling this person their code is wrong sends them round the loop
        // that ends in the throttle.
        expect(await shownFor(500, #"{"ok":false,"message":"Something went wrong on my end. Try again."}"#),
               "Something went wrong on my end. Try again.",
               "a server-side save failure must not be reported as a bad code")

        // The 400 that is about the PASSWORD, not the code. The old copy sent
        // them back to ask for another code, which could never help.
        expect(await shownFor(400, #"{"ok":false,"message":"Pick a password with at least 8 characters."}"#),
               "Pick a password with at least 8 characters.",
               "a too-short password must say so")

        // The genuine bad code still reads exactly as it always did.
        expect(await shownFor(400, "{\"ok\":false,\"message\":\"\(canned)\"}"),
               canned,
               "a genuinely wrong code keeps its sentence")

        // A proxy that answers in HTML has no sentence worth showing, so the
        // canned line is still the right fallback — never a scrap of markup.
        expect(await shownFor(502, "<html><head><title>502 Bad Gateway</title></head></html>"),
               canned,
               "an HTML gateway page falls back to the canned line")
        expect(await shownFor(400, ""), canned,
               "an empty body falls back to the canned line")
        expect(await shownFor(400, #"{"ok":false}"#), canned,
               "JSON with no message falls back to the canned line")

        // A 200 is a success and throws nothing.
        expect(await shownFor(200, #"{"ok":true,"message":"Done — sign in with your new password."}"#),
               nil,
               "a 200 must not surface as an error")

        print("\(checks - failures.count)/\(checks) checks passed")
        if !failures.isEmpty {
            for f in failures { print("FAIL  \(f)") }
            exit(1)
        }
        print("reset messages: all green")
        exit(0)
    }
}
