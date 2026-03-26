import SwiftUI

struct ServerListView: View {
    @EnvironmentObject var store: ServerStore
    @State private var showAdd = false

    var body: some View {
        List {
            ForEach(store.servers) { server in
                Button {
                    store.setActive(server)
                } label: {
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

    private enum AuthTab: String { case email, apiKey }

    @State private var name = ""
    @State private var url = ""
    @State private var checking = false
    @State private var error: String?
    @State private var needsAuth = true
    @State private var authTab: AuthTab = .apiKey
    @State private var email = ""
    @State private var code = ""
    @State private var codeSent = false
    @State private var apiKey = ""

    var body: some View {
        NavigationStack {
            Form {
                Section("Server") {
                    TextField("Name", text: $name)
                        .textContentType(.organizationName)
                    TextField("URL", text: $url)
                        .textContentType(.URL)
                        .keyboardType(.URL)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                }

                Section {
                    Toggle("Requires authentication", isOn: $needsAuth)
                }

                if needsAuth {
                    Section("Authentication") {
                        Picker("Method", selection: $authTab) {
                            Text("API Key").tag(AuthTab.apiKey)
                            Text("Email Code").tag(AuthTab.email)
                        }
                        .pickerStyle(.segmented)

                        if authTab == .apiKey {
                            SecureField("API Key", text: $apiKey)
                                .textInputAutocapitalization(.never)
                                .autocorrectionDisabled()
                            Text("Paste a personal API key from your Crow dashboard settings.")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        } else {
                            TextField("Email", text: $email)
                                .textContentType(.emailAddress)
                                .keyboardType(.emailAddress)
                                .textInputAutocapitalization(.never)

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
                    Button(confirmButtonTitle) {
                        Task { await addServer() }
                    }
                    .disabled(name.isEmpty || url.isEmpty || checking)
                }
            }
        }
    }

    private var confirmButtonTitle: String {
        guard needsAuth else { return "Add" }
        return authTab == .apiKey ? "Validate & Add" : (codeSent ? "Verify & Add" : "Add")
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

        // Handle auth
        if needsAuth {
            if authTab == .apiKey && !apiKey.isEmpty {
                do {
                    try await api.validateApiKey(apiKey)
                    config.authMethod = .apiKey
                    config.authToken = apiKey
                } catch {
                    self.error = "API key validation failed: \(error.localizedDescription)"
                    checking = false
                    return
                }
            } else if authTab == .email && codeSent && !code.isEmpty {
                do {
                    let (result, sessionToken) = try await api.verify(email: email, code: code)
                    if result.status == "ok", let token = sessionToken {
                        config.authMethod = .sessionToken
                        config.authToken = token
                    } else if result.status == "ok" {
                        self.error = "Verification succeeded but no session token received"
                        checking = false
                        return
                    }
                } catch {
                    self.error = "Verification failed: \(error.localizedDescription)"
                    checking = false
                    return
                }
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
