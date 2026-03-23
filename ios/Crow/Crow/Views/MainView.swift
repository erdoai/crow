import SwiftUI

struct MainView: View {
    let api: CrowAPI

    @EnvironmentObject var store: ServerStore
    @State private var conversations: [Conversation] = []
    @State private var agents: [Agent] = []
    @State private var selectedConversation: Conversation?
    @State private var showNewChat = false
    @State private var showServerPicker = false
    @State private var loading = true

    var body: some View {
        NavigationSplitView {
            sidebar
        } detail: {
            if let conv = selectedConversation {
                ChatView(
                    api: api,
                    conversationId: conv.id,
                    threadId: conv.gateway_thread_id
                )
            } else {
                ContentUnavailableView(
                    "Select a conversation",
                    systemImage: "bubble.left.and.text.bubble.right",
                    description: Text("Pick a conversation or start a new one")
                )
            }
        }
        .task { await load() }
        .sheet(isPresented: $showNewChat) {
            NewChatSheet(api: api, agents: agents) { conv in
                selectedConversation = conv
                await load()
            }
        }
        .sheet(isPresented: $showServerPicker) {
            NavigationStack {
                ServerListView()
            }
            .environmentObject(store)
        }
    }

    private var sidebar: some View {
        List(selection: $selectedConversation) {
            if !agents.isEmpty {
                Section("Agents") {
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 10) {
                            ForEach(agents) { agent in
                                AgentChip(agent: agent) {
                                    showNewChat = true
                                }
                            }
                        }
                        .padding(.horizontal, 4)
                        .padding(.vertical, 8)
                    }
                    .listRowInsets(EdgeInsets(top: 0, leading: 8, bottom: 0, trailing: 8))
                }
            }

            Section("Conversations") {
                if loading {
                    HStack {
                        Spacer()
                        ProgressView()
                        Spacer()
                    }
                    .listRowBackground(Color.clear)
                } else if conversations.isEmpty {
                    Text("No conversations yet")
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, alignment: .center)
                        .listRowBackground(Color.clear)
                } else {
                    ForEach(conversations) { conv in
                        ConversationRow(conversation: conv)
                            .tag(conv)
                    }
                }
            }
        }
        .listStyle(.sidebar)
        .navigationTitle(api.server.name)
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button(action: { showNewChat = true }) {
                    Image(systemName: "square.and.pencil")
                }
            }
            ToolbarItem(placement: .navigation) {
                if store.servers.count > 1 {
                    Menu {
                        ForEach(store.servers) { server in
                            Button {
                                store.setActive(server)
                            } label: {
                                Label(
                                    server.name,
                                    systemImage: server.id == store.activeServer?.id
                                        ? "checkmark.circle.fill"
                                        : "server.rack"
                                )
                            }
                        }
                        Divider()
                        Button("Manage Servers...") { showServerPicker = true }
                    } label: {
                        Image(systemName: "server.rack")
                    }
                }
            }
        }
        .refreshable { await load() }
    }

    private func load() async {
        do {
            async let c = api.listConversations()
            async let a = api.listAgents()
            conversations = try await c
            agents = try await a
        } catch {
            // TODO: error handling
        }
        loading = false
    }
}

// MARK: - Subviews

struct ConversationRow: View {
    let conversation: Conversation

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(conversation.gateway_thread_id)
                .font(.body)
                .fontWeight(.medium)
                .lineLimit(1)
            Text(relativeTime(conversation.updated_at))
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding(.vertical, 2)
    }

    private func relativeTime(_ isoString: String) -> String {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        guard let date = formatter.date(from: isoString) else { return isoString }
        let relative = RelativeDateTimeFormatter()
        relative.unitsStyle = .abbreviated
        return relative.localizedString(for: date, relativeTo: Date())
    }
}

struct AgentChip: View {
    let agent: Agent
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            VStack(spacing: 6) {
                Image(systemName: iconForAgent(agent.name))
                    .font(.title3)
                    .frame(width: 40, height: 40)
                    .background(Color.accentColor.opacity(0.15))
                    .clipShape(Circle())
                Text(agent.name)
                    .font(.caption2)
                    .lineLimit(1)
            }
            .frame(width: 64)
        }
        .buttonStyle(.plain)
    }

    private func iconForAgent(_ name: String) -> String {
        switch name {
        case "pa": return "person.crop.circle"
        case "devbot": return "chevron.left.forwardslash.chevron.right"
        case "pilot": return "airplane"
        default: return "cpu"
        }
    }
}

// MARK: - New Chat

struct NewChatSheet: View {
    let api: CrowAPI
    let agents: [Agent]
    let onCreated: (Conversation) async -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var text = ""
    @State private var selectedAgent: Agent?
    @State private var sending = false

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // Agent picker
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 12) {
                        agentButton(name: "Auto", icon: "sparkles", agent: nil)
                        ForEach(agents) { agent in
                            agentButton(
                                name: agent.name,
                                icon: iconForAgent(agent.name),
                                agent: agent
                            )
                        }
                    }
                    .padding()
                }

                Divider()

                // Message input
                VStack(spacing: 12) {
                    TextEditor(text: $text)
                        .frame(minHeight: 100)
                        .overlay(alignment: .topLeading) {
                            if text.isEmpty {
                                Text("What do you need?")
                                    .foregroundStyle(.tertiary)
                                    .padding(.top, 8)
                                    .padding(.leading, 4)
                                    .allowsHitTesting(false)
                            }
                        }
                        .scrollContentBackground(.hidden)

                    if let agent = selectedAgent {
                        Text("Sending to **\(agent.name)**: \(agent.description)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
                .padding()

                Spacer()
            }
            .navigationTitle("New Chat")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button {
                        Task { await send() }
                    } label: {
                        if sending {
                            ProgressView()
                        } else {
                            Image(systemName: "arrow.up.circle.fill")
                                .font(.title2)
                        }
                    }
                    .disabled(text.trimmingCharacters(in: .whitespaces).isEmpty || sending)
                }
            }
        }
    }

    private func agentButton(name: String, icon: String, agent: Agent?) -> some View {
        let isSelected = selectedAgent?.id == agent?.id
        return Button {
            selectedAgent = agent
        } label: {
            VStack(spacing: 6) {
                Image(systemName: icon)
                    .font(.title3)
                    .frame(width: 44, height: 44)
                    .background(isSelected ? Color.accentColor : Color.accentColor.opacity(0.1))
                    .foregroundStyle(isSelected ? .white : .primary)
                    .clipShape(Circle())
                Text(name)
                    .font(.caption)
                    .foregroundStyle(isSelected ? .primary : .secondary)
            }
        }
        .buttonStyle(.plain)
    }

    private func iconForAgent(_ name: String) -> String {
        switch name {
        case "pa": return "person.crop.circle"
        case "devbot": return "chevron.left.forwardslash.chevron.right"
        case "pilot": return "airplane"
        default: return "cpu"
        }
    }

    private func send() async {
        let trimmed = text.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty else { return }
        sending = true

        do {
            let result = try await api.sendMessage(
                text: trimmed,
                agent: selectedAgent?.name
            )
            // Fetch conversation list to get the new one
            let conversations = try await api.listConversations()
            if let conv = conversations.first(where: { $0.gateway_thread_id == result.thread_id }) {
                await onCreated(conv)
            }
            dismiss()
        } catch {
            // TODO: show error
        }
        sending = false
    }
}
