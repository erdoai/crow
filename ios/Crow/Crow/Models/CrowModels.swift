import Foundation

struct Agent: Codable, Identifiable, Hashable {
    var id: String { name }
    let name: String
    let description: String
    let prompt_template: String?
    let tools: [String]?
    let mcp_servers: [String]?
    let knowledge_areas: [String]?
}

struct Conversation: Codable, Identifiable, Hashable {
    let id: String
    let gateway: String
    let gateway_thread_id: String
    let created_at: String
    let updated_at: String
}

struct Message: Codable, Identifiable {
    let id: String
    let conversation_id: String
    let role: String
    let content: String
    let agent_name: String?
    let created_at: String

    var isUser: Bool { role == "user" }
}

struct KnowledgeEntry: Codable, Identifiable {
    let id: String
    let agent_name: String?
    let category: String
    let title: String
    let content: String
    let source: String?
    let tags: [String]
    let created_at: String
    let updated_at: String
}

struct SendMessageRequest: Encodable {
    let text: String
    let thread_id: String
    let agent: String?
}

struct SendMessageResponse: Decodable {
    let status: String
    let thread_id: String
}

struct HealthResponse: Decodable {
    let status: String
}

struct AuthSendCodeRequest: Encodable {
    let email: String
}

struct AuthVerifyRequest: Encodable {
    let email: String
    let code: String
}

struct AuthVerifyResponse: Decodable {
    let status: String
    let redirect: String?
}

struct AgentUpsertRequest: Encodable {
    let name: String
    let description: String
    let prompt_template: String
    let tools: [String]
    let mcp_servers: [String]
    let knowledge_areas: [String]
}

struct KnowledgeWriteRequest: Encodable {
    let category: String
    let title: String
    let content: String
    let tags: [String]
}

// MARK: - Jobs

struct Job: Codable, Identifiable {
    let id: String
    let agent_name: String
    let status: String
    let source: String
    let input: String
    let output: String?
    let worker_id: String?
    let error: String?
    let created_at: String
    let started_at: String?
    let completed_at: String?

    var isActive: Bool { status == "running" || status == "pending" }
}

struct ScheduledJob: Codable, Identifiable {
    let id: String
    let agent_name: String
    let input: String
    let cron: String?
    let run_at: String
    let status: String
    let created_at: String
}

struct WorkerInfo: Codable, Identifiable {
    let id: String
    let name: String?
    let last_heartbeat: String
    let status: String
}

// MARK: - Push Notifications

struct DeviceTokenRequest: Encodable {
    let device_token: String
    let platform: String
}
