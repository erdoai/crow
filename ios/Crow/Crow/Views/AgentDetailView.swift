import SwiftUI

struct AgentDetailView: View {
    let api: CrowAPI
    let agentName: String?
    let onSaved: () async -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var name = ""
    @State private var description = ""
    @State private var promptTemplate = ""
    @State private var toolsText = ""
    @State private var mcpServersText = ""
    @State private var knowledgeAreasText = ""
    @State private var saving = false
    @State private var error: String?
    @State private var loading = false

    private var isNew: Bool { agentName == nil }

    var body: some View {
        NavigationStack {
            Form {
                Section("Identity") {
                    if isNew {
                        TextField("Name (e.g. devbot)", text: $name)
                            .textInputAutocapitalization(.never)
                            .autocorrectionDisabled()
                    } else {
                        LabeledContent("Name", value: name)
                    }
                    TextField("Description", text: $description)
                }

                Section("System Prompt") {
                    TextEditor(text: $promptTemplate)
                        .frame(minHeight: 200)
                        .font(.system(.body, design: .monospaced))
                        .scrollContentBackground(.hidden)
                }

                Section {
                    TextField("e.g. delegate_to_agent, knowledge_search", text: $toolsText)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                } header: {
                    Text("Tools")
                } footer: {
                    Text("Comma-separated tool names")
                }

                Section {
                    TextField("e.g. devbot-mcp", text: $mcpServersText)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                } header: {
                    Text("MCP Servers")
                } footer: {
                    Text("Comma-separated MCP server names")
                }

                Section {
                    TextField("e.g. coding, architecture", text: $knowledgeAreasText)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                } header: {
                    Text("Knowledge Areas")
                } footer: {
                    Text("Comma-separated knowledge area tags")
                }

                if let error {
                    Section {
                        Text(error)
                            .foregroundStyle(.red)
                    }
                }
            }
            .navigationTitle(isNew ? "New Agent" : "Edit Agent")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        Task { await save() }
                    }
                    .disabled(name.isEmpty || saving)
                }
            }
            .task { await loadIfEditing() }
            .overlay { if loading { ProgressView() } }
        }
    }

    private func loadIfEditing() async {
        guard let agentName else { return }
        loading = true
        do {
            let agent = try await api.getAgent(name: agentName)
            name = agent.name
            description = agent.description
            promptTemplate = agent.prompt_template ?? ""
            toolsText = agent.tools?.joined(separator: ", ") ?? ""
            mcpServersText = agent.mcp_servers?.joined(separator: ", ") ?? ""
            knowledgeAreasText = agent.knowledge_areas?.joined(separator: ", ") ?? ""
        } catch {
            self.error = error.localizedDescription
        }
        loading = false
    }

    private func save() async {
        saving = true
        error = nil
        do {
            try await api.upsertAgent(
                name: name,
                description: description,
                promptTemplate: promptTemplate,
                tools: parseCSV(toolsText),
                mcpServers: parseCSV(mcpServersText),
                knowledgeAreas: parseCSV(knowledgeAreasText)
            )
            await onSaved()
            dismiss()
        } catch {
            self.error = error.localizedDescription
        }
        saving = false
    }

    private func parseCSV(_ text: String) -> [String] {
        text.split(separator: ",")
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
    }
}
