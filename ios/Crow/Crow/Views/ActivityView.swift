import SwiftUI

struct ActivityView: View {
    let api: CrowAPI

    @State private var jobs: [Job] = []
    @State private var scheduledJobs: [ScheduledJob] = []
    @State private var workers: [WorkerInfo] = []
    @State private var loading = true
    @State private var sseClient: SSEClient?

    var body: some View {
        NavigationStack {
            List {
                // Running jobs section
                let activeJobs = jobs.filter { $0.isActive }
                if !activeJobs.isEmpty {
                    Section {
                        ForEach(activeJobs) { job in
                            JobRow(job: job)
                        }
                    } header: {
                        HStack {
                            Text("Running")
                            Spacer()
                            Text("\(activeJobs.count)")
                                .font(.caption)
                                .padding(.horizontal, 6)
                                .padding(.vertical, 2)
                                .background(Color.green.opacity(0.2))
                                .clipShape(Capsule())
                        }
                    }
                }

                // Recent jobs section
                let recentJobs = jobs.filter { !$0.isActive }.prefix(20)
                if !recentJobs.isEmpty {
                    Section("Recent") {
                        ForEach(Array(recentJobs)) { job in
                            JobRow(job: job)
                        }
                    }
                }

                // Scheduled section
                let activeScheduled = scheduledJobs.filter { $0.status == "active" }
                if !activeScheduled.isEmpty {
                    Section("Scheduled") {
                        ForEach(activeScheduled) { sj in
                            ScheduledJobRow(scheduledJob: sj)
                                .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                                    Button(role: .destructive) {
                                        Task { await cancelScheduled(sj.id) }
                                    } label: {
                                        Label("Cancel", systemImage: "xmark.circle")
                                    }
                                }
                        }
                    }
                }

                // Workers section
                if !workers.isEmpty {
                    Section("Workers") {
                        ForEach(workers) { worker in
                            WorkerRow(worker: worker)
                        }
                    }
                }
            }
            .overlay {
                if loading {
                    ProgressView()
                } else if jobs.isEmpty && scheduledJobs.isEmpty && workers.isEmpty {
                    ContentUnavailableView(
                        "No activity",
                        systemImage: "waveform",
                        description: Text("Jobs will appear here when agents are running")
                    )
                }
            }
            .navigationTitle("Activity")
            .task { await load() }
            .onAppear { connectSSE() }
            .onDisappear { sseClient?.disconnect() }
            .refreshable { await load() }
        }
    }

    private func load() async {
        do {
            async let j = api.listJobs()
            async let s = api.listScheduledJobs()
            async let w = api.listWorkers()
            jobs = try await j
            scheduledJobs = try await s
            workers = try await w
        } catch {
            // Silently handle — user can pull to refresh
        }
        loading = false
    }

    private func cancelScheduled(_ id: String) async {
        _ = try? await api.cancelScheduledJob(id: id)
        scheduledJobs.removeAll { $0.id == id }
    }

    private func connectSSE() {
        guard let url = api.stateStream() else { return }
        let client = SSEClient { sseMessage in
            guard let event = sseMessage.event,
                  let data = sseMessage.data.data(using: .utf8) else { return }

            // Parse the wrapper: {"type": "...", "data": {...}, "timestamp": "..."}
            guard let wrapper = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let payload = wrapper["data"] as? [String: Any] else { return }

            DispatchQueue.main.async {
                switch event {
                case "job.started":
                    handleJobStarted(payload)
                case "job.completed":
                    handleJobCompleted(payload)
                case "job.failed":
                    handleJobFailed(payload)
                case "job.progress":
                    handleJobProgress(payload)
                default:
                    break
                }
            }
        }
        client.connect(url: url, server: api.server)
        sseClient = client
    }

    private func handleJobStarted(_ data: [String: Any]) {
        guard let jobId = data["job_id"] as? String,
              let agentName = data["agent_name"] as? String else { return }
        if let idx = jobs.firstIndex(where: { $0.id == jobId }) {
            // Update existing
            let old = jobs[idx]
            jobs[idx] = Job(
                id: old.id, agent_name: old.agent_name, status: "running",
                source: old.source, input: old.input, output: old.output,
                worker_id: old.worker_id, error: old.error,
                created_at: old.created_at, started_at: ISO8601DateFormatter().string(from: Date()),
                completed_at: old.completed_at
            )
        } else {
            let newJob = Job(
                id: jobId, agent_name: agentName, status: "running",
                source: (data["source"] as? String) ?? "message",
                input: (data["input"] as? String) ?? "",
                output: nil, worker_id: nil, error: nil,
                created_at: ISO8601DateFormatter().string(from: Date()),
                started_at: ISO8601DateFormatter().string(from: Date()),
                completed_at: nil
            )
            jobs.insert(newJob, at: 0)
        }
    }

    private func handleJobCompleted(_ data: [String: Any]) {
        guard let jobId = data["job_id"] as? String,
              let idx = jobs.firstIndex(where: { $0.id == jobId }) else { return }
        let old = jobs[idx]
        jobs[idx] = Job(
            id: old.id, agent_name: old.agent_name, status: "completed",
            source: old.source, input: old.input, output: old.output,
            worker_id: old.worker_id, error: old.error,
            created_at: old.created_at, started_at: old.started_at,
            completed_at: ISO8601DateFormatter().string(from: Date())
        )
    }

    private func handleJobFailed(_ data: [String: Any]) {
        guard let jobId = data["job_id"] as? String,
              let idx = jobs.firstIndex(where: { $0.id == jobId }) else { return }
        let old = jobs[idx]
        jobs[idx] = Job(
            id: old.id, agent_name: old.agent_name, status: "failed",
            source: old.source, input: old.input, output: old.output,
            worker_id: old.worker_id, error: (data["error"] as? String) ?? old.error,
            created_at: old.created_at, started_at: old.started_at,
            completed_at: ISO8601DateFormatter().string(from: Date())
        )
    }

    private func handleJobProgress(_ data: [String: Any]) {
        // Progress doesn't change job model currently — could extend Job with a transient progress field
        // For now, just refresh to keep UI fresh
    }
}

// MARK: - Row Views

struct JobRow: View {
    let job: Job

    var body: some View {
        HStack(spacing: 10) {
            statusIndicator
            VStack(alignment: .leading, spacing: 3) {
                HStack(spacing: 6) {
                    Text(job.agent_name)
                        .font(.subheadline)
                        .fontWeight(.medium)
                    if job.isActive {
                        Text(elapsedText)
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                            .monospacedDigit()
                    }
                }
                Text(job.input)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
                if let error = job.error {
                    Text(error)
                        .font(.caption2)
                        .foregroundStyle(.red)
                        .lineLimit(1)
                }
            }
        }
        .padding(.vertical, 2)
    }

    @ViewBuilder
    private var statusIndicator: some View {
        switch job.status {
        case "running":
            Circle()
                .fill(.green)
                .frame(width: 8, height: 8)
        case "pending":
            Image(systemName: "clock")
                .font(.caption2)
                .foregroundStyle(.secondary)
        case "completed":
            Image(systemName: "checkmark.circle")
                .font(.caption2)
                .foregroundStyle(.secondary)
        case "failed":
            Image(systemName: "xmark.circle")
                .font(.caption2)
                .foregroundStyle(.red)
        default:
            Circle()
                .fill(.secondary)
                .frame(width: 8, height: 8)
        }
    }

    private var elapsedText: String {
        guard let started = job.started_at else { return "" }
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        guard let date = formatter.date(from: started) else { return "" }
        let s = Int(Date().timeIntervalSince(date))
        if s < 60 { return "\(s)s" }
        if s < 3600 { return "\(s / 60)m \(s % 60)s" }
        let h = s / 3600
        let m = (s % 3600) / 60
        if h < 24 { return "\(h)h \(m)m" }
        return "\(h / 24)d \(h % 24)h"
    }
}

struct ScheduledJobRow: View {
    let scheduledJob: ScheduledJob

    var body: some View {
        VStack(alignment: .leading, spacing: 3) {
            Text(scheduledJob.agent_name)
                .font(.subheadline)
                .fontWeight(.medium)
            Text(scheduledJob.input)
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(2)
            HStack(spacing: 8) {
                if let cron = scheduledJob.cron {
                    Label(cron, systemImage: "clock.arrow.2.circlepath")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                Label(relativeTime(scheduledJob.run_at), systemImage: "calendar")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
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

struct WorkerRow: View {
    let worker: WorkerInfo

    var body: some View {
        HStack(spacing: 10) {
            Circle()
                .fill(isOnline ? .green : .secondary.opacity(0.3))
                .frame(width: 8, height: 8)
            VStack(alignment: .leading, spacing: 2) {
                Text(worker.name ?? String(worker.id.prefix(8)))
                    .font(.subheadline)
                Text(isOnline ? "online" : "offline")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private var isOnline: Bool {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        guard let date = formatter.date(from: worker.last_heartbeat) else { return false }
        return Date().timeIntervalSince(date) < 60
    }
}
