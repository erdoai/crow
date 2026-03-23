import Foundation

struct Agent: Codable, Identifiable, Hashable {
    var id: String { name }
    let name: String
    let description: String
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
