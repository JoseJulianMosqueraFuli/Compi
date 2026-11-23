import Foundation

// Intercept all requests. Only this read-only contract may reach the synthetic receiver.
private final class ReceiverFixture: URLProtocol {
    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func stopLoading() {}

    override func startLoading() {
        guard let url = request.url, let host = url.host else { preconditionFailure("Missing target") }
        precondition(url.scheme == "https" && url.path == "/api/healthkit/connection" && url.query == nil)
        precondition(request.httpMethod == "GET" && request.httpBody == nil && request.httpBodyStream == nil)
        precondition(request.value(forHTTPHeaderField: "Authorization") == "Bearer synthetic-fixture")

        let status: Int
        let body: String
        switch host {
        case "ready.local": (status, body) = (200, #"{"status":"ready","protocol_version":1}"#)
        case "old.local": (status, body) = (200, #"{"status":"ready","protocol_version":2}"#)
        case "malformed.local": (status, body) = (200, "{}")
        case "waiting.local": (status, body) = (200, #"{"status":"waiting","protocol_version":1}"#)
        case "auth.local": (status, body) = (401, "")
        case "missing.local": (status, body) = (404, "")
        case "redirect.local": (status, body) = (307, "")
        case "db.local": (status, body) = (503, "")
        case "failure.local": (status, body) = (500, "")
        case "tls.local", "offline.local":
            let code: URLError.Code = host == "tls.local" ? .serverCertificateUntrusted : .cannotConnectToHost
            client?.urlProtocol(self, didFailWithError: URLError(code))
            return
        default: preconditionFailure("Unexpected destination")
        }
        let response = HTTPURLResponse(url: url, statusCode: status, httpVersion: "HTTP/1.1", headerFields: nil)!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(body.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
}

@main
struct SyncChecks {
    static func main() async throws {
        try endpointRestrictions()
        try await offlineReplay()
        print("Compi · conexión autenticada, destinos locales y reintentos verificados")
    }

    private static func endpointRestrictions() throws {
        let valid = [
            "https://gym.local:8443", "https://192.168.42.2",
            "https://10.1.2.3", "https://172.31.255.255", "https://[fd00::1]"
        ]
        for address in valid { _ = try LocalServer.origin(address) }
        let upper = try LocalServer.origin("https://GYM.local:443/")
        let normal = try LocalServer.origin("https://gym.local")
        precondition(upper == normal)
        for address in ["http://gym.local", "https://compi.example", "https://192.168.0.256",
                        "https://172.32.0.1", "https://user:pass@gym.local",
                        "https://gym.local/data", "https://gym.local?key=value", "https://[::1]"] {
            precondition((try? LocalServer.origin(address)) == nil)
        }
    }

    private static func checkReceiver() async throws {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [ReceiverFixture.self]
        let transport = BatchTransport(config: config)
        func pairing(_ host: String) throws -> Pairing {
            Pairing(origin: try LocalServer.origin("https://\(host).local"), token: "synthetic-fixture")
        }
        try await transport.checkConnection(to: pairing("ready"))
        let failures: [(String, SyncError)] = [
            ("old", .incompatibleReceiver), ("malformed", .incompatibleReceiver),
            ("waiting", .receiverNotReady), ("auth", .unauthorized), ("missing", .incompatibleReceiver),
            ("redirect", .incompatibleReceiver), ("db", .receiverNotReady), ("failure", .serverUnavailable),
            ("tls", .tls), ("offline", .network)
        ]
        for (host, expected) in failures {
            do {
                try await transport.checkConnection(to: pairing(host))
                preconditionFailure("Unexpected success for \(host)")
            } catch let error as SyncError {
                precondition(error == expected, "Unexpected receiver error for \(host)")
            } catch let error as URLError {
                precondition(SyncError(transportError: error) == expected, "Unexpected network error for \(host)")
            }
        }
    }

    private static func offlineReplay() async throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: directory) }
        let store = try StateFiles(directory: directory)
        let kind = SampleKind.workout
        var stream = try store.load(kind)
        let sample = Observation(sampleID: UUID(), sourceBundle: "test.synthetic",
                                 start: "2000-01-01T10:00:00Z", end: "2000-01-01T10:01:00Z",
                                 value: .category("walk"), durationSeconds: 60)
        let first = Changes(anchor: Data([1]), samples: [sample], deletions: [])
        try stream.stage(first, kind: kind)
        try store.save(stream, kind)
        let stateFile = directory.appendingPathComponent(kind.rawValue)
        let bytesBeforeChecks = try Data(contentsOf: stateFile)
        try await checkReceiver()
        let bytesAfterChecks = try Data(contentsOf: stateFile)
        precondition(bytesBeforeChecks == bytesAfterChecks)
        let staged = try store.load(kind)
        precondition(staged.sequence == 0 && staged.anchor == nil && staged.streamID == stream.streamID)
        let body = try JSONSerialization.jsonObject(with: staged.pending!.body) as! [String: Any]
        let samples = body["upserts"] as! [[String: Any]]
        precondition(body["sequence"] as? Int == 1 && body["kind"] as? String == "workout")
        precondition(samples.first?["source_bundle"] as? String == "test.synthetic")
        precondition(samples.first?["duration_s"] as? Double == 60)
        let second = Changes(anchor: Data([2]), samples: [sample], deletions: [sample.sampleID])
        try stream.stage(second, kind: kind)
        precondition(stream.pending?.body == staged.pending?.body)
        do {
            try stream.acknowledge(Acknowledgement(sequence: 2, applied: true))
            preconditionFailure("Mismatched sequence accepted")
        } catch SyncError.acknowledgement {}
        precondition(stream.anchor == nil && stream.pending != nil)
        // The first ACK was lost; a replay confirms the committed batch without applying it twice.
        try stream.acknowledge(Acknowledgement(sequence: 1, applied: false))
        try store.save(stream, kind)
        stream = try store.load(kind)
        precondition(stream.sequence == 1 && stream.anchor == first.anchor && stream.pending == nil)
        try stream.stage(second, kind: kind)
        let changes = try JSONSerialization.jsonObject(with: stream.pending!.body) as! [String: Any]
        precondition(changes["sequence"] as? Int == 2 && (changes["upserts"] as? [Any])?.isEmpty == true)
        precondition((changes["deletions"] as? [String]) == [sample.sampleID.uuidString])
        try stream.acknowledge(Acknowledgement(sequence: 2, applied: true))
        try stream.stage(Changes(anchor: Data([3]), samples: [], deletions: []), kind: kind)
        precondition(stream.sequence == 2 && stream.anchor == second.anchor && stream.pending == nil)

        let other = StreamState()
        try store.save(other, .sleep)
        try store.save(stream, kind)
        try store.reset(kind)
        try store.reset(kind)
        let fresh = try store.load(kind)
        let untouched = try store.load(.sleep)
        precondition(fresh.sequence == 0 && fresh.pending == nil && fresh.anchor == nil)
        precondition(fresh.streamID != stream.streamID && untouched.streamID == other.streamID)
    }
}
