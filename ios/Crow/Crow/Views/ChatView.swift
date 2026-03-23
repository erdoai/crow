import SwiftUI

struct ChatView: View {
    let api: CrowAPI
    let conversationId: String
    let threadId: String

    @State private var messages: [Message] = []
    @State private var input = ""
    @State private var loading = true
    @State private var waitingForReply = false
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
                            TypingIndicator()
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
                .onKeyPress(.return) {
                    // Hardware keyboard: Return sends, Shift+Return inserts newline
                    send()
                    return .handled
                }

            Button(action: send) {
                Image(systemName: "arrow.up.circle.fill")
                    .font(.system(size: 30))
                    .foregroundStyle(canSend ? Color.accentColor : Color(.systemGray4))
            }
            .disabled(!canSend)
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
                waitingForReply = false
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

// MARK: - Typing Indicator

struct TypingIndicator: View {
    @State private var phase = 0.0

    var body: some View {
        HStack(alignment: .top, spacing: 0) {
            HStack(spacing: 5) {
                ForEach(0..<3) { i in
                    Circle()
                        .fill(Color(.systemGray3))
                        .frame(width: 8, height: 8)
                        .scaleEffect(dotScale(for: i))
                        .opacity(dotOpacity(for: i))
                }
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 14)
            .background(Color(.systemGray6))
            .clipShape(RoundedRectangle(cornerRadius: 18))

            Spacer(minLength: 48)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 2)
        .onAppear {
            withAnimation(.easeInOut(duration: 1.2).repeatForever(autoreverses: false)) {
                phase = 1.0
            }
        }
    }

    private func dotScale(for index: Int) -> Double {
        let offset = Double(index) * 0.33
        let t = (phase + offset).truncatingRemainder(dividingBy: 1.0)
        return 0.6 + 0.4 * sin(t * .pi)
    }

    private func dotOpacity(for index: Int) -> Double {
        let offset = Double(index) * 0.33
        let t = (phase + offset).truncatingRemainder(dividingBy: 1.0)
        return 0.4 + 0.6 * sin(t * .pi)
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
