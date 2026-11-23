import CryptoKit
import Darwin
import Foundation
import Security

enum LocalServer {
    static func origin(_ input: String) throws -> URL {
        guard var parts = URLComponents(string: input.trimmingCharacters(in: .whitespacesAndNewlines)),
              parts.scheme?.lowercased() == "https", let givenHost = parts.host,
              parts.user == nil, parts.password == nil, parts.query == nil, parts.fragment == nil,
              parts.path.isEmpty || parts.path == "/", (1...65535).contains(parts.port ?? 443)
        else { throw SyncError.endpoint }
        let host = givenHost.lowercased().trimmingCharacters(in: CharacterSet(charactersIn: "[]"))
        guard isLocal(host) else { throw SyncError.endpoint }
        parts.scheme = "https"
        parts.host = host.contains(":") ? "[\(host)]" : host
        parts.path = ""
        if parts.port == 443 { parts.port = nil }
        guard let url = parts.url else { throw SyncError.endpoint }
        return url
    }

    private static func isLocal(_ host: String) -> Bool {
        if host.hasSuffix(".local") {
            return host.range(of: #"^([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+local$"#,
                              options: .regularExpression) != nil
        }
        var ipv4 = in_addr()
        if inet_pton(AF_INET, host, &ipv4) == 1 {
            let bytes = withUnsafeBytes(of: ipv4) { Array($0) }
            return bytes[0] == 10 || (bytes[0] == 192 && bytes[1] == 168)
                || (bytes[0] == 172 && (16...31).contains(bytes[1]))
        }
        var ipv6 = in6_addr()
        guard inet_pton(AF_INET6, host, &ipv6) == 1 else { return false }
        return withUnsafeBytes(of: ipv6) { ($0[0] & 0xfe) == 0xfc }
    }
}

struct Pairing: Codable {
    let origin: URL
    let token: String

    // A different computer must never receive the pending bytes for this origin.
    var storageID: String {
        SHA256.hash(data: Data(origin.absoluteString.utf8)).map { String(format: "%02x", $0) }.joined()
    }
}

enum Keychain {
    private static var query: [String: Any] {
        [kSecClass as String: kSecClassGenericPassword,
         kSecAttrService as String: "compi.healthkit.connection",
         kSecAttrAccount as String: "paired-local-backend"]
    }

    static func load() throws -> Pairing? {
        var request = query
        request[kSecReturnData as String] = true
        var result: CFTypeRef?
        let status = SecItemCopyMatching(request as CFDictionary, &result)
        if status == errSecItemNotFound { return nil }
        guard status == errSecSuccess, let data = result as? Data else { throw SyncError.credential }
        return try JSONDecoder().decode(Pairing.self, from: data)
    }

    static func save(origin input: String, token: String) throws -> Pairing {
        let origin = try LocalServer.origin(input)
        let token = token.trimmingCharacters(in: .whitespacesAndNewlines)
        guard token.utf8.count >= 32, token.utf8.allSatisfy({ (33...126).contains($0) })
        else { throw SyncError.credential }
        let pairing = Pairing(origin: origin, token: token)
        let attributes: [String: Any] = [
            kSecValueData as String: try JSONEncoder().encode(pairing),
            kSecAttrAccessible as String: kSecAttrAccessibleWhenUnlockedThisDeviceOnly
        ]
        let status = SecItemUpdate(query as CFDictionary, attributes as CFDictionary)
        if status == errSecItemNotFound {
            let item = query.merging(attributes) { _, new in new }
            guard SecItemAdd(item as CFDictionary, nil) == errSecSuccess else { throw SyncError.credential }
        } else if status != errSecSuccess {
            throw SyncError.credential
        }
        return pairing
    }
}

private final class NoRedirects: NSObject, URLSessionTaskDelegate {
    func urlSession(_ session: URLSession, task: URLSessionTask,
                    willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest,
                    completionHandler: @escaping (URLRequest?) -> Void) {
        completionHandler(nil)
    }
}

final class BatchTransport {
    private let session: URLSession

    init() {
        let config = URLSessionConfiguration.ephemeral
        config.allowsCellularAccess = false
        config.waitsForConnectivity = false
        config.urlCache = nil
        config.urlCredentialStorage = nil
        config.httpShouldSetCookies = false
        config.timeoutIntervalForRequest = 15
        session = URLSession(configuration: config, delegate: NoRedirects(), delegateQueue: nil)
    }

    deinit { session.invalidateAndCancel() }

    func send(_ batch: PendingBatch, to pairing: Pairing) async throws -> Acknowledgement {
        let origin = try LocalServer.origin(pairing.origin.absoluteString)
        var request = URLRequest(url: origin.appendingPathComponent("api/healthkit/batches"))
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(String(batch.body.count), forHTTPHeaderField: "Content-Length")
        request.setValue("Bearer \(pairing.token)", forHTTPHeaderField: "Authorization")
        let (data, response) = try await session.upload(for: request, from: batch.body)
        switch (response as? HTTPURLResponse)?.statusCode {
        case 200:
            guard let ack = try? JSONDecoder().decode(Acknowledgement.self, from: data)
            else { throw SyncError.acknowledgement }
            return ack
        case 401, 403: throw SyncError.unauthorized
        case 409: throw SyncError.conflict
        case 422: throw SyncError.invalidBatch
        default: throw SyncError.serverUnavailable
        }
    }
}
