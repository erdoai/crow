import SwiftUI

struct ChatView: View {
    let api: CrowAPI
    let conversationId: String
    let threadId: String

    @State private var messages: [Message] = []
    @State private var input = ""
    @State private var loading = false
    @State private var sseClient: SSEClient?

    var body: some View {
        VStack(spacing: 0) {
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 12) {
                        ForEach(messages) { msg in
                            MessageBubble(message: msg)
                                .id(msg.id)
                        }
                    }
                    .padding()
                }
                .onChange(of: messages.count) {
                    if let last = messages.last {
                        withAnimation {
                            proxy.scrollTo(last.id, anchor: .bottom)
                        }
                    }
                }
            }

            Divider()

            HStack(spacing: 12) {
                TextField("Message", text: $input, axis: .vertical)
                    .textFieldStyle(.plain)
                    .lineLimit(1...5)
                    .onSubmit { send() }

                Button(action: send) {
                    Image(systemName: "arrow.up.circle.fill")
                        .font(.title2)
                }
                .disabled(input.trimmingCharacters(in: .whitespaces).isEmpty || loading)
            }
            .padding()
        }
        .navigationTitle("Chat")
        .navigationBarTitleDisplayMode(.inline)
        .task { await loadMessages() }
        .onAppear { connectSSE() }
        .onDisappear { sseClient?.disconnect() }
    }

    private func loadMessages() async {
        do {
            messages = try await api.getMessages(conversationId: conversationId)
        } catch {
            // TODO: show error
        }
    }

    private func send() {
        let text = input.trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty else { return }
        input = ""
        loading = true

        // Optimistic local insert
        let local = Message(
            id: UUID().uuidString,
            conversation_id: conversationId,
            role: "user",
            content: text,
            agent_name: nil,
            created_at: ISO8601DateFormatter().string(from: Date())
        )
        messages.append(local)

        Task {
            do {
                try await api.sendMessage(text: text, threadId: threadId)
            } catch {
                // TODO: show error
            }
            loading = false
        }
    }

    private func connectSSE() {
        guard let url = api.messageStream(conversationId: conversationId) else { return }
        let client = SSEClient { sseMessage in
            guard let data = sseMessage.data.data(using: .utf8),
                  let payload = try? JSONDecoder().decode(SSEPayload.self, from: data) else { return }
            let msg = Message(
                id: sseMessage.id ?? UUID().uuidString,
                conversation_id: conversationId,
                role: "assistant",
                content: payload.text,
                agent_name: payload.agent_name,
                created_at: payload.timestamp
            )
            DispatchQueue.main.async {
                messages.append(msg)
            }
        }
        client.connect(url: url, sessionToken: api.server.sessionToken)
        sseClient = client
    }
}

private struct SSEPayload: Decodable {
    let text: String
    let agent_name: String?
    let timestamp: String
}

struct MessageBubble: View {
    let message: Message

    var body: some View {
        HStack {
            if message.isUser { Spacer(minLength: 60) }
            VStack(alignment: message.isUser ? .trailing : .leading, spacing: 4) {
                if let agent = message.agent_name {
                    Text(agent)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                Text(message.content)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 10)
                    .background(message.isUser ? Color.accentColor : Color(.systemGray5))
                    .foregroundStyle(message.isUser ? .white : .primary)
                    .clipShape(RoundedRectangle(cornerRadius: 16))
            }
            if !message.isUser { Spacer(minLength: 60) }
        }
    }
}
