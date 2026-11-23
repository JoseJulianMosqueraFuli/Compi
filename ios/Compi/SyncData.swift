import Foundation

enum SampleKind: String, Codable, CaseIterable {
    case workout, sleep
    case heartRate = "heart_rate"
    case bodyMass = "body_mass"

    var label: String {
        switch self {
        case .workout: return "Entrenamientos"
        case .sleep: return "Sueño"
        case .heartRate: return "Frecuencia cardiaca"
        case .bodyMass: return "Peso corporal"
        }
    }
}

enum Reading: Encodable {
    case number(Double), category(String)

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .number(let value): try container.encode(value)
        case .category(let value): try container.encode(value)
        }
    }
}

struct Observation: Encodable {
    let sampleID: UUID
    let sourceBundle: String
    let start: String
    let end: String
    let value: Reading
    var durationSeconds: Double? = nil

    enum CodingKeys: String, CodingKey {
        case sampleID = "sample_id", sourceBundle = "source_bundle"
        case start, end, value
        case durationSeconds = "duration_s"
    }
}

struct Changes {
    let anchor: Data
    let samples: [Observation]
    let deletions: [UUID]
}

private struct Batch: Encodable {
    let stream_id: UUID
    let kind: SampleKind
    let sequence: Int
    let upserts: [Observation]
    let deletions: [UUID]
}

struct PendingBatch: Codable {
    let body: Data
    let nextAnchor: Data
}

struct Acknowledgement: Decodable {
    let sequence: Int
    let applied: Bool
}

enum SyncError: Error {
    case endpoint, credential, healthUnavailable, unreadableSample, acknowledgement, conflict
    case unauthorized, invalidBatch, serverUnavailable, incompatibleReceiver, receiverNotReady, tls, network

    init(transportError: URLError) {
        switch transportError.code {
        case .secureConnectionFailed, .serverCertificateHasBadDate, .serverCertificateUntrusted,
             .serverCertificateHasUnknownRoot, .serverCertificateNotYetValid, .clientCertificateRejected,
             .clientCertificateRequired, .appTransportSecurityRequiresSecureConnection:
            self = .tls
        default:
            self = .network
        }
    }

    var message: String {
        switch self {
        case .endpoint: return "Escribe una dirección HTTPS del equipo local (.local o IP privada)."
        case .credential: return "Revisa el token de conexión y que el iPhone esté desbloqueado."
        case .healthUnavailable: return "Salud no está disponible en este dispositivo."
        case .unreadableSample: return "Salud no pudo leer esta categoría. Revisa los permisos y desbloquea el iPhone."
        case .acknowledgement: return "El servidor devolvió una confirmación inesperada. Se conserva el lote."
        case .conflict: return "La secuencia difiere en el servidor. Comprueba el destino y su copia de la base de datos."
        case .unauthorized: return "El servidor rechazó el token. Revisa la conexión guardada."
        case .invalidBatch: return "El servidor rechazó el formato del lote. Comprueba la versión de Compi."
        case .serverUnavailable: return "El receptor no pudo completar la solicitud. Comprueba su estado en el Mac e inténtalo de nuevo."
        case .incompatibleReceiver: return "Comprueba la dirección y el puerto del receptor móvil y que ambas versiones de Compi sean compatibles."
        case .receiverNotReady: return "Comprueba en el Mac el token del receptor, la conexión a la base de datos y las migraciones."
        case .tls: return "Falló la conexión segura. Verifica el nombre y la vigencia del certificado del Mac y la confianza en su autoridad local en el iPhone."
        case .network: return "Comprueba que ambos equipos estén en la misma Wi-Fi, el permiso de red local y que el receptor esté encendido."
        }
    }
}

struct StreamState: Codable {
    var streamID = UUID()
    private(set) var sequence = 0
    private(set) var anchor: Data?
    private(set) var pending: PendingBatch?

    mutating func stage(_ changes: Changes, kind: SampleKind) throws {
        guard pending == nil else { return }
        let removed = Set(changes.deletions)
        let samples = changes.samples.filter { !removed.contains($0.sampleID) }
        guard !samples.isEmpty || !removed.isEmpty else { return }
        let batch = Batch(stream_id: streamID, kind: kind, sequence: sequence + 1,
                          upserts: samples, deletions: removed.sorted { $0.uuidString < $1.uuidString })
        pending = PendingBatch(body: try JSONEncoder().encode(batch), nextAnchor: changes.anchor)
    }

    mutating func acknowledge(_ ack: Acknowledgement) throws {
        // An acknowledged replay (applied == false) commits the same local checkpoint.
        guard let pending, ack.sequence == sequence + 1 else { throw SyncError.acknowledgement }
        sequence = ack.sequence
        anchor = pending.nextAnchor
        self.pending = nil
    }
}

struct StateFiles {
    let directory: URL

    init(directory: URL) throws {
        var directory = directory
        let manager = FileManager.default
        try manager.createDirectory(at: directory, withIntermediateDirectories: true)
        var values = URLResourceValues()
        values.isExcludedFromBackup = true
        try directory.setResourceValues(values)
        self.directory = directory
    }

    func load(_ kind: SampleKind) throws -> StreamState {
        let file = directory.appendingPathComponent(kind.rawValue)
        do {
            return try JSONDecoder().decode(StreamState.self, from: Data(contentsOf: file))
        } catch let error as CocoaError where error.code == .fileReadNoSuchFile {
            return StreamState()
        }
    }

    func save(_ state: StreamState, _ kind: SampleKind) throws {
        let data = try JSONEncoder().encode(state)
        let file = directory.appendingPathComponent(kind.rawValue)
        #if os(iOS)
        try data.write(to: file, options: [.atomic, .completeFileProtection])
        #else
        try data.write(to: file, options: .atomic)
        #endif
    }

    func reset(_ kind: SampleKind) throws {
        do {
            try FileManager.default.removeItem(at: directory.appendingPathComponent(kind.rawValue))
        } catch let error as CocoaError where error.code == .fileNoSuchFile {
            return
        }
    }
}
