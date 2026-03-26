import Foundation

enum AuthMethod: String, Codable {
    case none
    case sessionToken
    case apiKey
}

struct ServerConfig: Codable, Identifiable, Hashable {
    var id: UUID = UUID()
    var name: String
    var url: String
    var authMethod: AuthMethod = .none
    var authToken: String?

    var baseURL: URL? { URL(string: url) }
    var isAuthenticated: Bool { authToken != nil && authMethod != .none }
}

@MainActor
final class ServerStore: ObservableObject {
    @Published var servers: [ServerConfig] = []
    @Published var activeServer: ServerConfig?

    private let key = "crow_servers"
    private let activeKey = "crow_active_server"

    init() {
        load()
    }

    func add(_ server: ServerConfig) {
        servers.append(server)
        if activeServer == nil { activeServer = server }
        save()
    }

    func remove(_ server: ServerConfig) {
        servers.removeAll { $0.id == server.id }
        if activeServer?.id == server.id {
            activeServer = servers.first
        }
        save()
    }

    func update(_ server: ServerConfig) {
        if let idx = servers.firstIndex(where: { $0.id == server.id }) {
            servers[idx] = server
        }
        if activeServer?.id == server.id { activeServer = server }
        save()
    }

    func setActive(_ server: ServerConfig) {
        activeServer = server
        save()
    }

    private func save() {
        if let data = try? JSONEncoder().encode(servers) {
            UserDefaults.standard.set(data, forKey: key)
        }
        if let data = try? JSONEncoder().encode(activeServer) {
            UserDefaults.standard.set(data, forKey: activeKey)
        }
    }

    private func load() {
        if let data = UserDefaults.standard.data(forKey: key),
           let decoded = try? JSONDecoder().decode([ServerConfig].self, from: data) {
            servers = decoded
        }
        if let data = UserDefaults.standard.data(forKey: activeKey),
           let decoded = try? JSONDecoder().decode(ServerConfig.self, from: data) {
            activeServer = decoded
        }
    }
}
