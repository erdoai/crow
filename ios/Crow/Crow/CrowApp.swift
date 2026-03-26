import SwiftUI
import UserNotifications

@main
struct CrowApp: App {
    @StateObject private var serverStore = ServerStore()
    @UIApplicationDelegateAdaptor(AppDelegate.self) var appDelegate

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(serverStore)
                .onAppear {
                    appDelegate.serverStore = serverStore
                    requestNotificationPermission()
                }
        }
    }

    private func requestNotificationPermission() {
        UNUserNotificationCenter.current().requestAuthorization(
            options: [.alert, .badge, .sound]
        ) { granted, _ in
            if granted {
                DispatchQueue.main.async {
                    UIApplication.shared.registerForRemoteNotifications()
                }
            }
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

// MARK: - App Delegate for Push Notifications

class AppDelegate: NSObject, UIApplicationDelegate {
    var serverStore: ServerStore?

    func application(
        _ application: UIApplication,
        didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data
    ) {
        let token = deviceToken.map { String(format: "%02.2hhx", $0) }.joined()
        // Register with the active server
        guard let server = serverStore?.activeServer else { return }
        let api = CrowAPI(server: server)
        Task {
            _ = try? await api.registerDeviceToken(token)
        }
    }

    func application(
        _ application: UIApplication,
        didFailToRegisterForRemoteNotificationsWithError error: Error
    ) {
        // Push not available — silently ignore
    }
}
