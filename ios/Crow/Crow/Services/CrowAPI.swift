import Foundation

final class CrowAPI {
    let server: ServerConfig
    private let session: URLSession
    private let decoder = JSONDecoder()

    init(server: ServerConfig, session: URLSession = .shared) {
        self.server = server
        self.session = session
    }

    // MARK: - Health

    func health() async throws -> HealthResponse {
        try await get("/healthz")
    }

    // MARK: - Agents

    func listAgents() async throws -> [Agent] {
        try await get("/agents")
    }

    func getAgent(name: String) async throws -> Agent {
        try await get("/agents/\(name)")
    }

    @discardableResult
    func upsertAgent(
        name: String,
        description: String,
        promptTemplate: String,
        tools: [String],
        mcpServers: [String],
        knowledgeAreas: [String]
    ) async throws -> [String: String] {
        let body = AgentUpsertRequest(
            name: name,
            description: description,
            prompt_template: promptTemplate,
            tools: tools,
            mcp_servers: mcpServers,
            knowledge_areas: knowledgeAreas
        )
        return try await post("/agents", body: body)
    }

    @discardableResult
    func deleteAgent(name: String) async throws -> [String: String] {
        try await delete("/agents/\(name)")
    }

    // MARK: - Conversations

    func listConversations() async throws -> [Conversation] {
        try await get("/conversations")
    }

    func getMessages(conversationId: String) async throws -> [Message] {
        try await get("/conversations/\(conversationId)/messages")
    }

    // MARK: - Messages

    @discardableResult
    func sendMessage(text: String, threadId: String = "default", agent: String? = nil) async throws -> SendMessageResponse {
        let body = SendMessageRequest(text: text, thread_id: threadId, agent: agent)
        return try await post("/messages", body: body)
    }

    // MARK: - Knowledge / Learnings

    func listLearnings() async throws -> [KnowledgeEntry] {
        try await get("/agents/_user/knowledge?category=learnings")
    }

    @discardableResult
    func addLearning(title: String, content: String, tags: [String]) async throws -> [String: String] {
        let body = KnowledgeWriteRequest(
            category: "learnings",
            title: title,
            content: content,
            tags: tags
        )
        return try await post("/agents/_user/knowledge", body: body)
    }

    // MARK: - Auth

    func sendCode(email: String) async throws {
        let body = AuthSendCodeRequest(email: email)
        let _: [String: String] = try await post("/auth/send-code", body: body)
    }

    func verify(email: String, code: String) async throws -> (AuthVerifyResponse, String?) {
        var request = try makeRequest(path: "/auth/verify", method: "POST")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(AuthVerifyRequest(email: email, code: code))

        // Don't let URLSession swallow the Set-Cookie header
        request.httpShouldHandleCookies = false

        let (data, response) = try await session.data(for: request)
        try checkResponse(response)
        let decoded = try decoder.decode(AuthVerifyResponse.self, from: data)

        // Extract crow_session JWT from Set-Cookie
        var sessionToken: String?
        if let http = response as? HTTPURLResponse,
           let setCookie = http.value(forHTTPHeaderField: "Set-Cookie") {
            for part in setCookie.components(separatedBy: ",") {
                let trimmed = part.trimmingCharacters(in: .whitespaces)
                if trimmed.hasPrefix("crow_session=") {
                    sessionToken = trimmed
                        .components(separatedBy: ";").first?
                        .replacingOccurrences(of: "crow_session=", with: "")
                }
            }
        }
        return (decoded, sessionToken)
    }

    /// Validate an API key by calling /api/me
    func validateApiKey(_ key: String) async throws {
        guard let base = server.baseURL else { throw CrowAPIError.invalidURL }
        let url = base.appendingPathComponent("/api/me")
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.setValue("Bearer \(key)", forHTTPHeaderField: "Authorization")
        let (_, response) = try await session.data(for: request)
        try checkResponse(response)
    }

    // MARK: - Jobs

    func listJobs(limit: Int = 50) async throws -> [Job] {
        try await get("/jobs?limit=\(limit)")
    }

    func listScheduledJobs() async throws -> [ScheduledJob] {
        try await get("/scheduled-jobs")
    }

    func listWorkers() async throws -> [WorkerInfo] {
        try await get("/workers")
    }

    @discardableResult
    func cancelScheduledJob(id: String) async throws -> [String: String] {
        try await delete("/scheduled-jobs/\(id)")
    }

    // MARK: - Push Notifications

    @discardableResult
    func registerDeviceToken(_ token: String) async throws -> [String: String] {
        let body = DeviceTokenRequest(device_token: token, platform: "apns")
        return try await post("/push/register", body: body)
    }

    @discardableResult
    func unregisterDeviceToken(_ token: String) async throws -> [String: String] {
        try await delete("/push/register/\(token)")
    }

    // MARK: - SSE

    func stateStream() -> URL? {
        guard let base = server.baseURL else { return nil }
        return base.appendingPathComponent("/api/state/stream")
    }

    func messageStream(conversationId: String) -> URL? {
        guard let base = server.baseURL else { return nil }
        return base.appendingPathComponent("/conversations/\(conversationId)/stream")
    }

    // MARK: - HTTP helpers

    private func get<T: Decodable>(_ path: String) async throws -> T {
        let request = try makeRequest(path: path, method: "GET")
        let (data, response) = try await session.data(for: request)
        try checkResponse(response)
        return try decoder.decode(T.self, from: data)
    }

    private func post<T: Decodable, B: Encodable>(_ path: String, body: B) async throws -> T {
        var request = try makeRequest(path: path, method: "POST")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(body)
        let (data, response) = try await session.data(for: request)
        try checkResponse(response)
        return try decoder.decode(T.self, from: data)
    }

    private func delete<T: Decodable>(_ path: String) async throws -> T {
        let request = try makeRequest(path: path, method: "DELETE")
        let (data, response) = try await session.data(for: request)
        try checkResponse(response)
        return try decoder.decode(T.self, from: data)
    }

    private func makeRequest(path: String, method: String) throws -> URLRequest {
        guard let base = server.baseURL else {
            throw CrowAPIError.invalidURL
        }
        let url = base.appendingPathComponent(path)
        var request = URLRequest(url: url)
        request.httpMethod = method
        if let token = server.authToken {
            switch server.authMethod {
            case .apiKey:
                request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
            case .sessionToken:
                request.setValue("crow_session=\(token)", forHTTPHeaderField: "Cookie")
            case .none:
                break
            }
        }
        return request
    }

    private func checkResponse(_ response: URLResponse) throws {
        guard let http = response as? HTTPURLResponse else {
            throw CrowAPIError.invalidResponse
        }
        guard (200..<300).contains(http.statusCode) else {
            throw CrowAPIError.httpError(http.statusCode)
        }
    }
}

enum CrowAPIError: LocalizedError {
    case invalidURL
    case invalidResponse
    case httpError(Int)

    var errorDescription: String? {
        switch self {
        case .invalidURL: "Invalid server URL"
        case .invalidResponse: "Invalid response"
        case .httpError(let code): "HTTP \(code)"
        }
    }
}
