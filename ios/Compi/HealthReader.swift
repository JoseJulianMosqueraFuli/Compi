import Foundation
import HealthKit

private extension SampleKind {
    var sampleType: HKSampleType {
        switch self {
        case .workout: return HKObjectType.workoutType()
        case .sleep: return HKCategoryType(.sleepAnalysis)
        case .heartRate: return HKQuantityType(.heartRate)
        case .bodyMass: return HKQuantityType(.bodyMass)
        }
    }
}

struct HealthReader {
    private let store = HKHealthStore()

    func authorize(_ kinds: [SampleKind]) async throws {
        guard HKHealthStore.isHealthDataAvailable() else { throw SyncError.healthUnavailable }
        let types = Set<HKObjectType>(kinds.map { $0.sampleType })
        try await store.requestAuthorization(toShare: [], read: types)
    }

    func page(_ kind: SampleKind, after checkpoint: Data?) async throws -> Changes {
        let previous = try checkpoint.map { data in
            guard let anchor = try NSKeyedUnarchiver.unarchivedObject(ofClass: HKQueryAnchor.self, from: data)
            else { throw SyncError.unreadableSample }
            return anchor
        }
        return try await withCheckedThrowingContinuation { continuation in
            let query = HKAnchoredObjectQuery(type: kind.sampleType, predicate: nil, anchor: previous, limit: 100) {
                _, samples, deleted, next, error in
                guard error == nil, let next, let samples, let deleted else {
                    continuation.resume(throwing: SyncError.unreadableSample)
                    return
                }
                do {
                    let dates = ISO8601DateFormatter()
                    dates.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
                    let anchor = try NSKeyedArchiver.archivedData(withRootObject: next, requiringSecureCoding: true)
                    let values = try samples.map { try Self.observation($0, kind: kind, dates: dates) }
                    continuation.resume(returning: Changes(anchor: anchor, samples: values,
                                                           deletions: deleted.map { $0.uuid }))
                } catch {
                    continuation.resume(throwing: SyncError.unreadableSample)
                }
            }
            store.execute(query)
        }
    }

    private static func observation(_ sample: HKSample, kind: SampleKind,
                                    dates: ISO8601DateFormatter) throws -> Observation {
        let value: Reading
        var duration: Double?
        switch (kind, sample) {
        case (.heartRate, let sample as HKQuantitySample):
            let bpm = HKUnit.count().unitDivided(by: .minute())
            value = .number(sample.quantity.doubleValue(for: bpm))
        case (.bodyMass, let sample as HKQuantitySample):
            value = .number(sample.quantity.doubleValue(for: .gramUnit(with: .kilo)))
        case (.workout, let workout as HKWorkout):
            switch workout.workoutActivityType {
            case .running: value = .category("run")
            case .walking: value = .category("walk")
            case .traditionalStrengthTraining, .functionalStrengthTraining: value = .category("strength")
            default: value = .category("other")
            }
            duration = workout.duration
        case (.sleep, let sample as HKCategorySample):
            switch HKCategoryValueSleepAnalysis(rawValue: sample.value) {
            case .inBed: value = .category("in_bed")
            case .awake: value = .category("awake")
            case .asleepUnspecified: value = .category("asleep")
            case .asleepCore: value = .category("core")
            case .asleepDeep: value = .category("deep")
            case .asleepREM: value = .category("rem")
            default: value = .category("unknown")
            }
        default: throw SyncError.unreadableSample
        }
        return Observation(sampleID: sample.uuid, sourceBundle: sample.sourceRevision.source.bundleIdentifier,
                           start: dates.string(from: sample.startDate), end: dates.string(from: sample.endDate),
                           value: value, durationSeconds: duration)
    }
}
