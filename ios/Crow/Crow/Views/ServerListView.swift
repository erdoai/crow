import SwiftUI

struct ServerListView: View {
    @EnvironmentObject var store: ServerStore
    @State private var showAdd = false

    var body: some View {
        List {
            ForEach(store.servers) { server in
                NavigationLink(
                    destination: ConversationListView(api: CrowAPI(server: server))
                ) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(server.name)
                            .font(.headline)
                        Text(server.url)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                        if server.isAuthenticated {
                            Label("Authenticated", systemImage: "checkmark.shield")
                                .font(.caption2)
                                .foregroundStyle(.green)
                        }
                    }
                    .padding(.vertical, 4)
                }
                .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                    Button(role: .destructive) {
                        store.remove(server)
                    } label: {
                        Label("Delete", systemImage: "trash")
                    }
                }
            }
        }
        .overlay {
            if store.servers.isEmpty {
                ContentUnavailableView(
                    "No servers",
                    systemImage: "server.rack",
                    description: Text("Add a Crow instance to get started")
                )
            }
        }
        .navigationTitle("Crow")
        .toolbar {
            Button(action: { showAdd = true }) {
                Image(systemName: "plus")
            }
        }
        .sheet(isPresented: $showAdd) {
            AddServerSheet()
                .environmentObject(store)
        }
    }
}

struct AddServerSheet: View {
    @EnvironmentObject var store: ServerStore
    @Environment(\.dismiss) private var dismiss

    @State private var name = ""
    @State private var url = ""
    @State private var checking = false
    @State private var error: String?
    @State private var needsAuth = false
    @State private var email = ""
    @State private var code = ""
    @State private var codeSent = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Server") {
                    TextField("Name", text: $name)
                        .textContentType(.organizationName)
                    TextField("URL", text: $url)
                        .textContentType(.URL)
                        .keyboardType(.URL)
                        .autocapitalization(.none)
                        .autocorrectionDisabled()
                }

                if needsAuth {
                    Section("Authentication") {
                        TextField("Email", text: $email)
                            .textContentType(.emailAddress)
                            .keyboardType(.emailAddress)
                            .autocapitalization(.none)

                        if codeSent {
                            TextField("Verification code", text: $code)
                                .keyboardType(.numberPad)
                        }

                        Button(codeSent ? "Resend code" : "Send code") {
                            Task { await sendCode() }
                        }
                        .disabled(email.isEmpty)
                    }
                }

                if let error {
                    Section {
                        Text(error)
                            .foregroundStyle(.red)
                    }
                }
            }
            .navigationTitle("Add Server")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button(needsAuth && codeSent ? "Verify & Add" : "Add") {
                        Task { await addServer() }
                    }
                    .disabled(name.isEmpty || url.isEmpty || checking)
                }
            }
        }
    }

    private func addServer() async {
        checking = true
        error = nil

        var config = ServerConfig(name: name, url: url.trimmingCharacters(in: .init(charactersIn: "/")))
        let api = CrowAPI(server: config)

        // Check connectivity
        do {
            _ = try await api.health()
        } catch {
            self.error = "Cannot reach server: \(error.localizedDescription)"
            checking = false
            return
        }

        // If auth is needed and we have a code, verify
        if needsAuth && codeSent && !code.isEmpty {
            do {
                let result = try await api.verify(email: email, code: code)
                if result.status == "ok" {
                    // In a full implementation we'd extract the session cookie
                    // For now, store a marker that auth succeeded
                    config.sessionToken = "authenticated"
                }
            } catch {
                self.error = "Verification failed: \(error.localizedDescription)"
                checking = false
                return
            }
        }

        store.add(config)
        checking = false
        dismiss()
    }

    private func sendCode() async {
        let api = CrowAPI(server: ServerConfig(name: name, url: url))
        do {
            try await api.sendCode(email: email)
            codeSent = true
        } catch {
            self.error = "Failed to send code: \(error.localizedDescription)"
        }
    }
}
