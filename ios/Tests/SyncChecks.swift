import Foundation

@main
struct SyncChecks {
    static func main() throws {
        try endpointRestrictions()
        try offlineReplay()
        print("Compi · destinos locales y reintentos verificados")
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

    private static func offlineReplay() throws {
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
