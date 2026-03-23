import SwiftUI

@main
struct CrowApp: App {
    @StateObject private var serverStore = ServerStore()

    var body: some Scene {
        WindowGroup {
            NavigationStack {
                ServerListView()
            }
            .environmentObject(serverStore)
        }
    }
}
