import Foundation

/// Lightweight SSE client for streaming conversation updates.
final class SSEClient: NSObject, URLSessionDataDelegate {
    private var task: URLSessionDataTask?
    private var session: URLSession?
    private var buffer = ""
    private let onMessage: (SSEMessage) -> Void

    struct SSEMessage {
        let id: String?
        let event: String?
        let data: String
    }

    init(onMessage: @escaping (SSEMessage) -> Void) {
        self.onMessage = onMessage
        super.init()
    }

    func connect(url: URL, server: ServerConfig? = nil) {
        disconnect()
        session = URLSession(configuration: .default, delegate: self, delegateQueue: nil)
        var request = URLRequest(url: url)
        request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
        if let server = server, let token = server.authToken {
            switch server.authMethod {
            case .apiKey:
                request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
            case .sessionToken:
                request.setValue("crow_session=\(token)", forHTTPHeaderField: "Cookie")
            case .none:
                break
            }
        }
        task = session?.dataTask(with: request)
        task?.resume()
    }

    func disconnect() {
        task?.cancel()
        task = nil
        session?.invalidateAndCancel()
        session = nil
        buffer = ""
    }

    // MARK: - URLSessionDataDelegate

    func urlSession(_ session: URLSession, dataTask: URLSessionDataTask, didReceive data: Data) {
        guard let text = String(data: data, encoding: .utf8) else { return }
        buffer += text
        parseBuffer()
    }

    // MARK: - Parse

    private func parseBuffer() {
        let blocks = buffer.components(separatedBy: "\n\n")
        // Last element is incomplete if buffer didn't end with \n\n
        buffer = blocks.last ?? ""
        for block in blocks.dropLast() {
            let trimmed = block.trimmingCharacters(in: .whitespacesAndNewlines)
            if trimmed.isEmpty || trimmed.hasPrefix(":") { continue }
            var id: String?
            var event: String?
            var dataLines: [String] = []
            for line in trimmed.components(separatedBy: "\n") {
                if line.hasPrefix("id: ") {
                    id = String(line.dropFirst(4))
                } else if line.hasPrefix("event: ") {
                    event = String(line.dropFirst(7))
                } else if line.hasPrefix("data: ") {
                    dataLines.append(String(line.dropFirst(6)))
                }
            }
            if !dataLines.isEmpty {
                onMessage(SSEMessage(id: id, event: event, data: dataLines.joined(separator: "\n")))
            }
        }
    }
}
