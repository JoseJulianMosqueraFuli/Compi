import SwiftUI

@main
struct CompiApp: App {
    var body: some Scene {
        WindowGroup { SyncView() }
    }
}

@MainActor
final class SyncModel: ObservableObject {
    @Published var address = "" {
        didSet { if address != oldValue { connectionMessage = "" } }
    }
    @Published var tokenInput = "" {
        didSet { if tokenInput != oldValue { connectionMessage = "" } }
    }
    @Published var selected: Set<SampleKind> {
        didSet { UserDefaults.standard.set(selected.map(\.rawValue), forKey: "enabledHealthCategories") }
    }
    @Published private(set) var connectedAddress: String?
    @Published private(set) var working = false
    @Published private(set) var connectionMessage = ""
    @Published private(set) var message = ""
    @Published var resetKind: SampleKind?

    private let health = HealthReader()
    private let transport = BatchTransport()

    init() {
        let saved = UserDefaults.standard.stringArray(forKey: "enabledHealthCategories") ?? []
        selected = Set(saved.compactMap(SampleKind.init(rawValue:)))
        do {
            connectedAddress = try Keychain.load()?.origin.absoluteString
            address = connectedAddress ?? ""
        } catch {
            message = SyncError.credential.message
        }
    }

    func saveConnection() {
        do {
            let pairing = try Keychain.save(origin: address, token: tokenInput)
            address = pairing.origin.absoluteString
            connectedAddress = address
            tokenInput = ""
            connectionMessage = "Conexión guardada. Puedes probar el receptor."
            message = ""
        } catch {
            connectionMessage = (error as? SyncError ?? .credential).message
        }
    }

    var canUseConnection: Bool {
        connectedAddress != nil && address == connectedAddress && tokenInput.isEmpty
    }

    func checkConnection() async {
        guard !working, canUseConnection else { return }
        working = true
        connectionMessage = "Comprobando el receptor… Si el iPhone pide acceso a la red local, pulsa Permitir."
        defer { working = false }
        do {
            guard let pairing = try Keychain.load() else { throw SyncError.credential }
            try await transport.checkConnection(to: pairing)
            connectionMessage = "Conexión verificada. El receptor está listo para sincronizar."
        } catch let error as SyncError {
            connectionMessage = error.message
        } catch let error as URLError {
            connectionMessage = SyncError(transportError: error).message
        } catch {
            connectionMessage = SyncError.credential.message
        }
    }

    private func files(for pairing: Pairing) throws -> StateFiles {
        let directory = URL.applicationSupportDirectory.appendingPathComponent("HealthSync", isDirectory: true)
            .appendingPathComponent(pairing.storageID, isDirectory: true)
        return try StateFiles(directory: directory)
    }

    func reset(_ kind: SampleKind) {
        guard !working else { return }
        do {
            guard let pairing = try Keychain.load() else { throw SyncError.credential }
            try files(for: pairing).reset(kind)
            selected.remove(kind)
            message = "Estado local de \(kind.label) borrado. Reinicia la categoría en el receptor antes de seleccionarla para importar de nuevo."
        } catch {
            message = "No se pudo borrar el estado local. Comprueba la conexión guardada y desbloquea el iPhone."
        }
    }

    func synchronize() async {
        guard !working, !selected.isEmpty, canUseConnection else { return }
        working = true
        message = "Consultando Salud…"
        defer { working = false }
        do {
            guard let pairing = try Keychain.load() else { throw SyncError.credential }
            let files = try files(for: pairing)
            let kinds = SampleKind.allCases.filter { selected.contains($0) }
            try await health.authorize(kinds)
            var remaining = kinds
            var acknowledged = 0
            var readFailures: [String] = []
            while !remaining.isEmpty {
                var ready: [(SampleKind, StreamState)] = []
                // Save one page per selected category before attempting network I/O.
                for kind in remaining {
                    var state = try files.load(kind)
                    if state.pending == nil {
                        let page: Changes
                        do {
                            page = try await health.page(kind, after: state.anchor)
                        } catch SyncError.unreadableSample {
                            readFailures.append(kind.label)
                            continue
                        }
                        try state.stage(page, kind: kind)
                        if state.pending != nil { try files.save(state, kind) }
                    }
                    if state.pending != nil { ready.append((kind, state)) }
                }
                remaining = []
                for (kind, staged) in ready {
                    try Task.checkCancellation()
                    var state = staged
                    guard let pending = state.pending else { continue }
                    let ack = try await transport.send(pending, to: pairing)
                    try state.acknowledge(ack)
                    try files.save(state, kind)
                    remaining.append(kind)
                    acknowledged += 1
                    message = "Lotes confirmados: \(acknowledged)"
                }
            }
            message = acknowledged == 0
                ? "Sin cambios visibles. Puedes revisar el acceso a las categorías en Salud."
                : "Sincronización completa. Lotes confirmados: \(acknowledged)."
            if !readFailures.isEmpty {
                message = "Lotes confirmados: \(acknowledged). Lectura pendiente: \(readFailures.joined(separator: ", ")). Revisa Salud e inténtalo de nuevo."
            }
        } catch let error as SyncError {
            message = error.message
        } catch let error as URLError {
            message = SyncError(transportError: error).message
        } catch {
            message = "Sincronización interrumpida. Desbloquea el iPhone, revisa los permisos y vuelve a intentarlo."
        }
    }
}

private struct SyncView: View {
    @StateObject private var model = SyncModel()

    var body: some View {
        NavigationStack {
            Form {
                Section("Equipo local") {
                    TextField("https://mi-mac.local:8443", text: $model.address)
                        .autocorrectionDisabled()
                        #if os(iOS)
                        .textInputAutocapitalization(.never).keyboardType(.URL)
                        #endif
                    SecureField("Token de conexión", text: $model.tokenInput)
                    Button("Guardar conexión") { model.saveConnection() }
                        .disabled(model.address.isEmpty || model.tokenInput.isEmpty)
                    Button("Probar conexión") { Task { await model.checkConnection() } }
                        .disabled(!model.canUseConnection)
                    if !model.connectionMessage.isEmpty { Text(model.connectionMessage).font(.footnote) }
                }
                Section {
                    ForEach(SampleKind.allCases, id: \.self) { kind in
                        Toggle(kind.label, isOn: Binding(
                            get: { model.selected.contains(kind) },
                            set: { enabled in
                                if enabled { model.selected.insert(kind) } else { model.selected.remove(kind) }
                            }))
                    }
                } header: {
                    Text("Categorías a sincronizar")
                } footer: {
                    Text("Salud te pedirá permiso de lectura. Compi enviará al equipo local el historial disponible de las categorías elegidas.")
                }
                Section {
                    Button("Sincronizar ahora") { Task { await model.synchronize() } }
                        .disabled(model.selected.isEmpty || !model.canUseConnection)
                    if model.working { ProgressView() }
                    if !model.message.isEmpty { Text(model.message).font(.footnote) }
                }
                if model.connectedAddress != nil, model.connectedAddress == model.address {
                    Section("Recuperación") {
                        Menu("Reiniciar una categoría…") {
                            ForEach(SampleKind.allCases, id: \.self) { kind in
                                Button(kind.label) { model.resetKind = kind }
                            }
                        }
                    }
                }
            }
            .disabled(model.working)
            .navigationTitle("Compi")
            .confirmationDialog("¿Reiniciar \(model.resetKind?.label ?? "esta categoría")?",
                                isPresented: Binding(get: { model.resetKind != nil },
                                                     set: { if !$0 { model.resetKind = nil } }),
                                titleVisibility: .visible, presenting: model.resetKind) { kind in
                Button("Borrar su estado local", role: .destructive) { model.reset(kind) }
                Button("Cancelar", role: .cancel) {}
            } message: { _ in
                Text("Se perderán la posición y el lote pendiente de esta categoría en Compi. Salud conservará su historial. Antes de volver a importar, reinicia también la categoría en el receptor.")
            }
        }
    }
}
