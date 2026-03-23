import SwiftUI

enum MainTab: Hashable {
    case chats
    case agents
    case learnings
}

struct MainView: View {
    let api: CrowAPI

    @EnvironmentObject var store: ServerStore
    @State private var selectedTab: MainTab = .chats

    var body: some View {
        TabView(selection: $selectedTab) {
            ChatsTab(api: api)
                .environmentObject(store)
                .tabItem {
                    Label("Chats", systemImage: "bubble.left.and.bubble.right")
                }
                .tag(MainTab.chats)

            AgentsTab(api: api)
                .tabItem {
                    Label("Agents", systemImage: "cpu")
                }
                .tag(MainTab.agents)

            NavigationStack {
                LearningsView(api: api)
            }
            .tabItem {
                Label("Learnings", systemImage: "lightbulb")
            }
            .tag(MainTab.learnings)
        }
    }
}

// MARK: - Chats Tab

struct ChatsTab: View {
    let api: CrowAPI

    @EnvironmentObject var store: ServerStore
    @State private var conversations: [Conversation] = []
    @State private var agents: [Agent] = []
    @State private var selectedConversation: Conversation?
    @State private var showNewChat = false
    @State private var showServerPicker = false
    @State private var loading = true
    @State private var errorMessage: String?

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

            if let errorMessage {
                Section {
                    Label(errorMessage, systemImage: "exclamationmark.triangle")
                        .font(.caption)
                        .foregroundStyle(.red)
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
        errorMessage = nil
        do {
            async let c = api.listConversations()
            async let a = api.listAgents()
            conversations = try await c
            agents = try await a
        } catch {
            errorMessage = "Cannot connect: \(error.localizedDescription)"
        }
        loading = false
    }
}

// MARK: - Agents Tab

struct AgentsTab: View {
    let api: CrowAPI

    @State private var agents: [Agent] = []
    @State private var loading = true
    @State private var showCreate = false
    @State private var editingAgent: String?

    var body: some View {
        NavigationStack {
            List {
                ForEach(agents) { agent in
                    Button {
                        editingAgent = agent.name
                    } label: {
                        HStack(spacing: 12) {
                            Image(systemName: iconForAgent(agent.name))
                                .font(.title3)
                                .frame(width: 36, height: 36)
                                .background(Color.accentColor.opacity(0.15))
                                .clipShape(Circle())

                            VStack(alignment: .leading, spacing: 3) {
                                Text(agent.name)
                                    .font(.headline)
                                    .foregroundStyle(.primary)
                                Text(agent.description)
                                    .font(.caption)
                                    .foregroundStyle(.secondary)
                                    .lineLimit(2)

                                if let tools = agent.tools, !tools.isEmpty {
                                    Text(tools.joined(separator: " · "))
                                        .font(.caption2)
                                        .foregroundStyle(.tertiary)
                                        .lineLimit(1)
                                }
                            }
                        }
                        .padding(.vertical, 4)
                    }
                    .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                        Button(role: .destructive) {
                            Task {
                                _ = try? await api.deleteAgent(name: agent.name)
                                await load()
                            }
                        } label: {
                            Label("Delete", systemImage: "trash")
                        }
                    }
                }
            }
            .overlay {
                if loading {
                    ProgressView()
                } else if agents.isEmpty {
                    ContentUnavailableView(
                        "No agents",
                        systemImage: "cpu",
                        description: Text("Create an agent to get started")
                    )
                }
            }
            .navigationTitle("Agents")
            .toolbar {
                Button(action: { showCreate = true }) {
                    Image(systemName: "plus")
                }
            }
            .sheet(isPresented: $showCreate) {
                AgentDetailView(api: api, agentName: nil) { await load() }
            }
            .sheet(item: $editingAgent) { name in
                AgentDetailView(api: api, agentName: name) { await load() }
            }
            .task { await load() }
            .refreshable { await load() }
        }
    }

    private func load() async {
        do {
            agents = try await api.listAgents()
        } catch {
            // TODO: error handling
        }
        loading = false
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

// Make String work as sheet item
extension String: @retroactive Identifiable {
    public var id: String { self }
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
    @State private var error: String?

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                // To: row — like iMessage
                HStack(spacing: 8) {
                    Text("To:")
                        .foregroundStyle(.secondary)
                    ScrollView(.horizontal, showsIndicators: false) {
                        HStack(spacing: 8) {
                            toChip(name: "Auto", agent: nil)
                            ForEach(agents) { agent in
                                toChip(name: agent.name, agent: agent)
                            }
                        }
                    }
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 10)

                Divider()

                // Empty conversation area
                Spacer()

                if let error {
                    Text(error)
                        .font(.caption)
                        .foregroundStyle(.red)
                        .padding(.horizontal, 16)
                        .padding(.bottom, 8)
                }

                // iMessage-style input bar at bottom
                Divider()
                HStack(alignment: .bottom, spacing: 10) {
                    TextField("iMessage", text: $text, axis: .vertical)
                        .textFieldStyle(.plain)
                        .lineLimit(1...8)
                        .submitLabel(.send)
                        .padding(.horizontal, 12)
                        .padding(.vertical, 8)
                        .background(Color(.systemGray6))
                        .clipShape(RoundedRectangle(cornerRadius: 20))
                        .onSubmit { Task { await send() } }

                    Button { Task { await send() } } label: {
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
            .navigationTitle("New Message")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
            }
        }
    }

    private var canSend: Bool {
        !text.trimmingCharacters(in: .whitespaces).isEmpty && !sending
    }

    private func toChip(name: String, agent: Agent?) -> some View {
        let isSelected = selectedAgent?.id == agent?.id
        return Button {
            selectedAgent = agent
        } label: {
            Text(name)
                .font(.subheadline)
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .background(isSelected ? Color.accentColor : Color(.systemGray5))
                .foregroundStyle(isSelected ? .white : .primary)
                .clipShape(Capsule())
        }
        .buttonStyle(.plain)
    }

    private func send() async {
        let trimmed = text.trimmingCharacters(in: .whitespaces)
        guard !trimmed.isEmpty, !sending else { return }
        sending = true
        error = nil

        do {
            let result = try await api.sendMessage(
                text: trimmed,
                agent: selectedAgent?.name
            )
            let conversations = try await api.listConversations()
            if let conv = conversations.first(where: { $0.gateway_thread_id == result.thread_id }) {
                await onCreated(conv)
            }
            dismiss()
        } catch {
            self.error = "Failed to send: \(error.localizedDescription)"
        }
        sending = false
    }
}
