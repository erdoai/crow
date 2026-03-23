import SwiftUI

struct LearningsView: View {
    let api: CrowAPI

    @State private var learnings: [KnowledgeEntry] = []
    @State private var loading = true
    @State private var showAdd = false
    @State private var searchText = ""

    var filtered: [KnowledgeEntry] {
        if searchText.isEmpty { return learnings }
        return learnings.filter {
            $0.title.localizedCaseInsensitiveContains(searchText) ||
            $0.content.localizedCaseInsensitiveContains(searchText)
        }
    }

    var body: some View {
        List {
            ForEach(filtered) { entry in
                LearningRow(entry: entry)
            }
        }
        .searchable(text: $searchText, prompt: "Search learnings")
        .overlay {
            if loading {
                ProgressView()
            } else if learnings.isEmpty {
                ContentUnavailableView(
                    "No learnings yet",
                    systemImage: "lightbulb",
                    description: Text("Capture things you learn as you go")
                )
            }
        }
        .navigationTitle("Learnings")
        .toolbar {
            Button(action: { showAdd = true }) {
                Image(systemName: "plus")
            }
        }
        .sheet(isPresented: $showAdd) {
            AddLearningSheet(api: api) { await load() }
        }
        .task { await load() }
        .refreshable { await load() }
    }

    private func load() async {
        do {
            learnings = try await api.listLearnings()
        } catch {
            // TODO: show error
        }
        loading = false
    }
}

struct LearningRow: View {
    let entry: KnowledgeEntry

    @State private var expanded = false

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(entry.title)
                    .font(.headline)
                Spacer()
                if !entry.tags.isEmpty {
                    Text(entry.tags.joined(separator: ", "))
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 2)
                        .background(Color.accentColor.opacity(0.1))
                        .clipShape(Capsule())
                }
            }

            Text(entry.content)
                .font(.body)
                .foregroundStyle(.secondary)
                .lineLimit(expanded ? nil : 3)

            Text(entry.created_at)
                .font(.caption2)
                .foregroundStyle(.tertiary)
        }
        .padding(.vertical, 4)
        .contentShape(Rectangle())
        .onTapGesture { expanded.toggle() }
    }
}

struct AddLearningSheet: View {
    let api: CrowAPI
    let onSaved: () async -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var title = ""
    @State private var content = ""
    @State private var tags = ""
    @State private var saving = false

    var body: some View {
        NavigationStack {
            Form {
                Section("What did you learn?") {
                    TextField("Title", text: $title)
                    TextEditor(text: $content)
                        .frame(minHeight: 120)
                        .scrollContentBackground(.hidden)
                }

                Section {
                    TextField("e.g. swift, architecture, debugging", text: $tags)
                        .textInputAutocapitalization(.never)
                } header: {
                    Text("Tags")
                } footer: {
                    Text("Comma-separated, optional")
                }
            }
            .navigationTitle("New Learning")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") {
                        Task { await save() }
                    }
                    .disabled(title.isEmpty || content.isEmpty || saving)
                }
            }
        }
    }

    private func save() async {
        saving = true
        do {
            try await api.addLearning(
                title: title,
                content: content,
                tags: tags.split(separator: ",")
                    .map { $0.trimmingCharacters(in: .whitespaces) }
                    .filter { !$0.isEmpty }
            )
            await onSaved()
            dismiss()
        } catch {
            // TODO: show error
        }
        saving = false
    }
}
