import SwiftUI

struct ChatView: View {
    let api: CrowAPI
    let conversationId: String
    let threadId: String

    @State private var messages: [Message] = []
    @State private var input = ""
    @State private var loading = true
    @State private var waitingForReply = false
    @State private var activityText: String?
    @State private var sseClient: SSEClient?
    @FocusState private var inputFocused: Bool

    var body: some View {
        VStack(spacing: 0) {
            messageList
            Divider()
            inputBar
        }
        .navigationTitle(threadId)
        .navigationBarTitleDisplayMode(.inline)
        .task { await loadMessages() }
        .onAppear { connectSSE() }
        .onDisappear { sseClient?.disconnect() }
    }

    // MARK: - Message List

    private var messageList: some View {
        ScrollViewReader { proxy in
            ScrollView {
                if loading {
                    ProgressView()
                        .padding(.top, 40)
                } else if messages.isEmpty {
                    Text("Send a message to get started")
                        .foregroundStyle(.tertiary)
                        .padding(.top, 40)
                } else {
                    LazyVStack(spacing: 2) {
                        ForEach(messages) { msg in
                            MessageRow(message: msg)
                                .id(msg.id)
                        }
                        if waitingForReply {
                            TypingIndicator(activityText: activityText)
                                .id("typing")
                        }
                    }
                    .padding(.vertical, 12)
                }
            }
            .onChange(of: messages.count) {
                scrollToBottom(proxy)
            }
            .onChange(of: waitingForReply) {
                scrollToBottom(proxy)
            }
        }
    }

    private func scrollToBottom(_ proxy: ScrollViewProxy) {
        let target = waitingForReply ? "typing" : messages.last?.id
        if let target {
            withAnimation(.easeOut(duration: 0.2)) {
                proxy.scrollTo(target, anchor: .bottom)
            }
        }
    }

    // MARK: - Input Bar

    private var inputBar: some View {
        HStack(alignment: .bottom, spacing: 10) {
            TextField("Message", text: $input, axis: .vertical)
                .textFieldStyle(.plain)
                .lineLimit(1...8)
                .submitLabel(.send)
                .focused($inputFocused)
                .padding(.horizontal, 12)
                .padding(.vertical, 8)
                .background(Color(.systemGray6))
                .clipShape(RoundedRectangle(cornerRadius: 20))
                .onSubmit { send() }

            Button(action: send) {
                Image(systemName: "arrow.up.circle.fill")
                    .font(.system(size: 30))
                    .foregroundStyle(canSend ? Color.accentColor : Color(.systemGray4))
            }
            .disabled(!canSend)
            .keyboardShortcut(.return, modifiers: .command)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
    }

    private var canSend: Bool {
        !input.trimmingCharacters(in: .whitespaces).isEmpty && !waitingForReply
    }

    // MARK: - Actions

    private func loadMessages() async {
        do {
            messages = try await api.getMessages(conversationId: conversationId)
        } catch {
            // TODO: show error
        }
        loading = false
    }

    private func send() {
        let text = input.trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty, !waitingForReply else { return }
        input = ""
        waitingForReply = true

        // Optimistic insert
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
                waitingForReply = false
            }
        }
    }

    private func connectSSE() {
        guard let url = api.messageStream(conversationId: conversationId) else { return }
        let client = SSEClient { sseMessage in
            guard let data = sseMessage.data.data(using: .utf8) else { return }

            switch sseMessage.event {
            case "chunk":
                // Tool call or text chunk — update activity indicator
                if let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                    let type = payload["type"] as? String
                    let toolName = payload["tool_name"] as? String
                    DispatchQueue.main.async {
                        if type == "tool_call", let name = toolName {
                            activityText = "calling \(name)..."
                        } else if type == "text" {
                            activityText = "generating response..."
                        }
                    }
                }

            case "progress":
                // Progress update — show status text
                if let payload = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                   let status = payload["status"] as? String {
                    DispatchQueue.main.async {
                        activityText = status
                    }
                }

            case "message":
                // Final message
                guard let payload = try? JSONDecoder().decode(SSEMessagePayload.self, from: data) else { return }
                let msg = Message(
                    id: sseMessage.id ?? UUID().uuidString,
                    conversation_id: conversationId,
                    role: "assistant",
                    content: payload.text,
                    agent_name: payload.agent_name,
                    created_at: payload.timestamp
                )
                DispatchQueue.main.async {
                    waitingForReply = false
                    activityText = nil
                    messages.append(msg)
                }

            default:
                break
            }
        }
        client.connect(url: url, server: api.server)
        sseClient = client
    }
}

private struct SSEMessagePayload: Decodable {
    let text: String
    let agent_name: String?
    let timestamp: String
}

// MARK: - Typing Indicator

struct TypingIndicator: View {
    var activityText: String?
    @State private var isPulsing = false

    var body: some View {
        HStack(alignment: .top, spacing: 0) {
            HStack(spacing: 8) {
                // Pulse indicator
                Circle()
                    .fill(Color.accentColor)
                    .frame(width: 8, height: 8)
                    .scaleEffect(isPulsing ? 1.3 : 0.8)
                    .opacity(isPulsing ? 1.0 : 0.5)

                Text(activityText ?? "thinking...")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            .background(Color(.systemGray6))
            .clipShape(RoundedRectangle(cornerRadius: 18))

            Spacer(minLength: 48)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 2)
        .onAppear {
            withAnimation(.easeInOut(duration: 1.0).repeatForever(autoreverses: true)) {
                isPulsing = true
            }
        }
    }
}

// MARK: - Message Row

struct MessageRow: View {
    let message: Message

    var body: some View {
        HStack(alignment: .top, spacing: 0) {
            if message.isUser {
                Spacer(minLength: 48)
                userBubble
            } else {
                assistantMessage
                Spacer(minLength: 48)
            }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 2)
    }

    private var userBubble: some View {
        Text(message.content)
            .padding(.horizontal, 14)
            .padding(.vertical, 10)
            .background(Color.accentColor)
            .foregroundStyle(.white)
            .clipShape(RoundedRectangle(cornerRadius: 18))
    }

    private var assistantMessage: some View {
        VStack(alignment: .leading, spacing: 4) {
            if let agent = message.agent_name {
                HStack(spacing: 4) {
                    Image(systemName: "cpu")
                        .font(.caption2)
                    Text(agent)
                        .font(.caption)
                        .fontWeight(.medium)
                }
                .foregroundStyle(.secondary)
            }
            Text(message.content)
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .background(Color(.systemGray6))
                .clipShape(RoundedRectangle(cornerRadius: 18))
        }
    }
}
