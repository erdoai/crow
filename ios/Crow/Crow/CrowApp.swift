import SwiftUI

@main
struct CrowApp: App {
    @StateObject private var serverStore = ServerStore()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(serverStore)
        }
    }
}

/// If there's one server, go straight to it. If multiple, show picker.
struct RootView: View {
    @EnvironmentObject var store: ServerStore

    var body: some View {
        Group {
            if let server = store.activeServer {
                MainView(api: CrowAPI(server: server))
                    .id(server.id) // recreate when switching server
            } else {
                NavigationStack {
                    ServerListView()
                }
            }
        }
    }
}
