import Foundation
import UserNotifications

/// THE ORGAN THIS APP DID NOT HAVE.
///
/// Until now there was no `UNUserNotificationCenter` anywhere in the product.
/// A booking sitting on "needs your OK" reached its owner only if they
/// happened to pick the phone up and open the app; a run parked on a question
/// waited in silence. For a customer that is indistinguishable from broken —
/// and the product could not even tell them it was waiting, because a text
/// was the only channel it had and it only goes to a number on file.
///
/// This works without a push server, and the reason is specific: the app
/// declares `audio` and `bluetooth-central` background modes, so while it is
/// listening it keeps running and keeps polling. A LOCAL notification raised
/// from that poll reaches a locked screen exactly like a pushed one. When the
/// app is genuinely not running nothing fires here — the SMS path is still
/// the backstop, which is why a reachable number is now required at sign-up.
///
/// Three rules, all of them about not becoming the next thing he mutes:
///
///   1. ONE PER JOB. The poll runs every three seconds. Without a memory of
///      what has already been raised, a single parked booking would ring
///      twenty times a minute.
///   2. ONLY WHEN IT IS ACTUALLY WAITING ON HIM. Work in flight is not news;
///      a finished errand is in the feed. Only "I cannot go on without you"
///      earns the screen.
///   3. NOT IN THE MIDDLE OF THE NIGHT. The work is already stopped, and it
///      will still be stopped at eight. Anything raised during quiet hours is
///      held, not dropped — a dinner booking that needs a yes must not be
///      silently forgotten because it got stuck at 2am.
@MainActor
final class Notifier {

    /// Quiet hours, matching the brain's own outbound rules.
    static let quietStartHour = 22
    static let quietEndHour = 8

    private var raised: Set<String> = []
    private var held: [(id: String, title: String, body: String)] = []
    private var authorized = false
    private var asked = false

    /// Ask only when there is something real to ask about.
    ///
    /// A permission sheet on first launch, before the product has done
    /// anything, is the one most people decline — and a declined prompt is
    /// not offered again. So this is called the first time work actually
    /// needs him, when the reason is on screen behind the dialog.
    func askIfNeeded() async {
        guard !asked else { return }
        asked = true
        let centre = UNUserNotificationCenter.current()
        let settings = await centre.notificationSettings()
        switch settings.authorizationStatus {
        case .authorized, .provisional, .ephemeral:
            authorized = true
        case .notDetermined:
            authorized = (try? await centre.requestAuthorization(
                options: [.alert, .sound, .badge])) ?? false
        default:
            authorized = false      // they said no; the text is the backstop
        }
    }

    static func inQuietHours(_ date: Date = Date(),
                             calendar: Calendar = .current) -> Bool {
        let hour = calendar.component(.hour, from: date)
        return hour >= quietStartHour || hour < quietEndHour
    }

    /// Everything the owner is currently blocking, raised once each.
    func announce(jobs: [AgentJob], now: Date = Date()) async {
        let waiting = jobs.filter { Self.isWaitingOnOwner($0) }
        guard !waiting.isEmpty else { return }
        await askIfNeeded()
        guard authorized else { return }

        for job in waiting where !raised.contains(job.id) {
            raised.insert(job.id)
            let (title, body) = Self.words(for: job)
            if Self.inQuietHours(now) {
                held.append((job.id, title, body))   // morning, not never
            } else {
                await post(id: job.id, title: title, body: body)
            }
        }
        // Anything parked overnight goes out once the hours end.
        if !Self.inQuietHours(now), !held.isEmpty {
            let due = held
            held.removeAll()
            for item in due {
                await post(id: item.id, title: item.title, body: item.body)
            }
        }
        // A job that stopped waiting can raise again if it comes back round.
        let stillWaiting = Set(waiting.map(\.id))
        raised = raised.intersection(stillWaiting)
    }

    static func isWaitingOnOwner(_ job: AgentJob) -> Bool {
        job.status == "awaiting_confirm" || job.status == "needs_user"
    }

    /// What the lock screen says. It has one line to be worth unlocking for,
    /// so it names the errand rather than announcing itself.
    static func words(for job: AgentJob) -> (String, String) {
        let goal = job.goal.trimmingCharacters(in: .whitespacesAndNewlines)
        let shortGoal = goal.count > 60 ? String(goal.prefix(57)) + "…" : goal
        if job.status == "awaiting_confirm" {
            return ("Ready when you are", shortGoal.isEmpty
                    ? "Something's ready for your OK."
                    : "\(shortGoal). Say the word and I'll do it.")
        }
        let asked = (job.result ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        // job.result carries the question it stopped on. Prefer his own
        // words; fall back to the errand rather than to a status word.
        let question = asked.isEmpty ? shortGoal : asked
        let trimmed = question.count > 140 ? String(question.prefix(137)) + "…" : question
        return ("I need you for a second", trimmed)
    }

    private func post(id: String, title: String, body: String) async {
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        content.sound = .default
        content.userInfo = ["jobID": id]
        let request = UNNotificationRequest(
            identifier: "anticipy-job-\(id)", content: content, trigger: nil)
        try? await UNUserNotificationCenter.current().add(request)
    }

    /// Signing out must not leave someone else's errands on the lock screen.
    func clearAll() {
        raised.removeAll()
        held.removeAll()
        UNUserNotificationCenter.current().removeAllDeliveredNotifications()
        UNUserNotificationCenter.current().removeAllPendingNotificationRequests()
    }
}
