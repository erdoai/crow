import SwiftUI

struct ConversationListView: View {
    let api: CrowAPI

    @State private var conversations: [Conversation] = []
    @State private var agents: [Agent] = []
    @State private var showNewChat = false
    @State private var loading = true

    var body: some View {
        List {
            ForEach(conversations) { conv in
                NavigationLink(
                    destination: ChatView(
                        api: api,
                        conversationId: conv.id,
                        threadId: conv.gateway_thread_id
                    )
                ) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(conv.gateway_thread_id)
                            .font(.headline)
                        Text(conv.updated_at)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                    .padding(.vertical, 4)
                }
            }
        }
        .overlay {
            if loading {
                ProgressView()
            } else if conversations.isEmpty {
                ContentUnavailableView("No conversations", systemImage: "bubble.left.and.bubble.right")
            }
        }
        .navigationTitle("Conversations")
        .toolbar {
            Button(action: { showNewChat = true }) {
                Image(systemName: "square.and.pencil")
            }
        }
        .sheet(isPresented: $showNewChat) {
            NewChatSheet(api: api, agents: agents)
        }
        .task { await load() }
        .refreshable { await load() }
    }

    private func load() async {
        do {
            async let c = api.listConversations()
            async let a = api.listAgents()
            conversations = try await c
            agents = try await a
        } catch {
            // TODO: show error
        }
        loading = false
    }
}

struct NewChatSheet: View {
    let api: CrowAPI
    let agents: [Agent]

    @Environment(\.dismiss) private var dismiss
    @State private var text = ""
    @State private var selectedAgent: Agent?

    var body: some View {
        NavigationStack {
            Form {
                Picker("Agent", selection: $selectedAgent) {
                    Text("Auto (PA)").tag(nil as Agent?)
                    ForEach(agents) { agent in
                        Text(agent.name).tag(agent as Agent?)
                    }
                }

                TextField("Message", text: $text, axis: .vertical)
                    .lineLimit(3...8)
            }
            .navigationTitle("New Chat")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Send") {
                        Task {
                            _ = try? await api.sendMessage(
                                text: text,
                                agent: selectedAgent?.name
                            )
                            dismiss()
                        }
                    }
                    .disabled(text.trimmingCharacters(in: .whitespaces).isEmpty)
                }
            }
        }
    }
}
