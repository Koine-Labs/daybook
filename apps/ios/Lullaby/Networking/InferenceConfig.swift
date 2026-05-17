import Foundation

enum InferenceConfig {
    #if DEBUG
    /// Local development — change to your Mac's WiFi IP for testing.
    static let baseURL = "ws://192.168.1.100:8000"
    #else
    /// Production — Railway deployment URL.
    static let baseURL = "wss://lullaby-inference.up.railway.app"
    #endif

    static let websocketPath = "/ws"

    static var websocketURL: URL {
        URL(string: "\(baseURL)\(websocketPath)")!
    }
}
