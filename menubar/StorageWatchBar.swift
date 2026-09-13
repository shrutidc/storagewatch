// StorageWatch menu bar app.
//
// Reads ~/.storagewatch/status.json, which the collector rewrites every cycle,
// so it shows this Mac's storage without signing in to anything: the collector
// already holds the credentials. Build with ./build.sh.
import AppKit
import SwiftUI

struct Status: Decodable {
    struct Volume: Decodable {
        let filesystem: String
        let filesystem_type: String
        let total_bytes: Double
        let used_bytes: Double
        let free_bytes: Double
        let used_percent: Double
    }
    struct Alert: Decodable {
        let id: Int
        let alert_type: String
        let severity: String
        let message: String
    }
    struct Disk: Decodable {
        let model: String
        let smart_status: String
    }
    let hostname: String
    let dashboard_url: String
    let read_bytes_per_sec: Double
    let write_bytes_per_sec: Double
    let volumes: [Volume]
    let alerts: [Alert]
    let disks: [Disk]
    let filevault_enabled: Bool?
    let snapshot_count: Int?

    /// The boot volume, which the menu bar title summarises.
    var boot: Volume? { volumes.first { $0.filesystem == "/" } ?? volumes.first }
}

@MainActor
final class Monitor: ObservableObject {
    @Published var status: Status?
    @Published var age: TimeInterval = .infinity
    private let file = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent(".storagewatch/status.json")
    private var timer: Timer?

    init() {
        refresh()
        timer = Timer.scheduledTimer(withTimeInterval: 5, repeats: true) { [weak self] _ in
            Task { @MainActor in self?.refresh() }
        }
    }

    func refresh() {
        guard let data = try? Data(contentsOf: file) else { status = nil; return }
        status = try? JSONDecoder().decode(Status.self, from: data)
        let modified = (try? file.resourceValues(forKeys: [.contentModificationDateKey]))?
            .contentModificationDate
        age = modified.map { Date().timeIntervalSince($0) } ?? .infinity
    }

    /// The collector writes every ~5 s; silence means it stopped.
    var stale: Bool { age > 30 }
    var needsAttention: Bool { stale || !(status?.alerts.isEmpty ?? true) }
}

func gb(_ bytes: Double) -> String { String(format: "%.1f GB", bytes / 1e9) }
func mbps(_ bytes: Double) -> String { String(format: "%.1f MB/s", bytes / 1e6) }

@main
struct StorageWatchBar: App {
    @StateObject private var monitor = Monitor()

    var body: some Scene {
        MenuBarExtra {
            Panel(monitor: monitor)
        } label: {
            HStack {
                Image(systemName: monitor.needsAttention ? "exclamationmark.triangle.fill" : "internaldrive")
                Text(monitor.status?.boot.map { String(format: "%.0f%%", $0.used_percent) } ?? "–")
            }
        }
        .menuBarExtraStyle(.window)
    }
}

struct Panel: View {
    @ObservedObject var monitor: Monitor

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let s = monitor.status {
                HStack {
                    Text(s.hostname).font(.headline)
                    Spacer()
                    Text(monitor.stale ? "Collector not reporting" : "Live")
                        .font(.caption)
                        .foregroundStyle(monitor.stale ? .red : .green)
                }

                ForEach(s.volumes, id: \.filesystem) { v in
                    VStack(alignment: .leading, spacing: 4) {
                        HStack {
                            Text("\(v.filesystem) · \(v.filesystem_type)").font(.subheadline)
                            Spacer()
                            Text(String(format: "%.1f%%", v.used_percent))
                                .font(.subheadline.monospacedDigit())
                        }
                        ProgressView(value: min(v.used_percent, 100), total: 100)
                            .tint(v.used_percent >= 90 ? .red : v.used_percent >= 80 ? .orange : .accentColor)
                        Text("\(gb(v.used_bytes)) used · \(gb(v.free_bytes)) free · \(gb(v.total_bytes))")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }

                Divider()
                HStack {
                    Label(mbps(s.read_bytes_per_sec), systemImage: "arrow.down.circle")
                    Spacer()
                    Label(mbps(s.write_bytes_per_sec), systemImage: "arrow.up.circle")
                }
                .font(.subheadline.monospacedDigit())

                ForEach(Array(s.disks.enumerated()), id: \.offset) { _, d in
                    Label("\(d.model): SMART \(d.smart_status)",
                          systemImage: d.smart_status == "Verified" ? "checkmark.seal" : "exclamationmark.octagon")
                        .font(.caption)
                }
                if let fv = s.filevault_enabled {
                    Label("FileVault \(fv ? "on" : "off")", systemImage: fv ? "lock.fill" : "lock.open")
                        .font(.caption)
                }
                if let n = s.snapshot_count {
                    Label("\(n) local snapshot\(n == 1 ? "" : "s")", systemImage: "clock.arrow.circlepath")
                        .font(.caption)
                }

                Divider()
                if s.alerts.isEmpty {
                    Label("No active alerts", systemImage: "checkmark.circle").foregroundStyle(.green)
                } else {
                    ForEach(s.alerts, id: \.id) { a in
                        VStack(alignment: .leading, spacing: 2) {
                            Text(a.alert_type.replacingOccurrences(of: "_", with: " "))
                                .font(.caption.bold())
                                .foregroundStyle(a.severity == "critical" ? .red : .orange)
                            Text(a.message).font(.caption)
                        }
                    }
                }

                Divider()
                Button("Open Dashboard") {
                    if let url = URL(string: s.dashboard_url) { NSWorkspace.shared.open(url) }
                }
            } else {
                Text("No data yet").font(.headline)
                Text("Run the StorageWatch installer to start the collector on this Mac.")
                    .font(.caption)
            }
            Button("Quit StorageWatch") { NSApplication.shared.terminate(nil) }
        }
        .padding(14)
        .frame(width: 320)
    }
}
