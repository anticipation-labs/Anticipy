import Foundation
import UserNotifications

/// `UNUserNotificationCenter.add` can complete after sign-out has already run
/// `clearAll`. In that ordering the clear happens first and the stale request
/// is installed second, so the add completion must remove its own identifier.
enum NotificationLeasePolicy {
    static func removeAfterAdd(stillCurrent: Bool) -> Bool { !stillCurrent }
}

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
    /// Readable so first run's Notifications switch can reflect the answer
    /// rather than sit on over a refusal; only this type writes it.
    private(set) var authorized = false
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
                             calendar: Calendar = .current,
                             schedule: NotificationQuietSchedule = .current) -> Bool {
        guard let hours = schedule.hours else { return false }
        let hour = calendar.component(.hour, from: date)
        return hour >= hours.start || hour < hours.end
    }

    /// Everything the owner is currently blocking, raised once each.
    func announce(jobs: [AgentJob], now: Date = Date(),
                  stillCurrent: @escaping @MainActor () -> Bool) async {
        guard AppPreferences.bool(forKey: AppPreferences.notificationsKey,
                                  default: true), stillCurrent() else { return }
        let waiting = jobs.filter { Self.isWaitingOnOwner($0) }
        guard !waiting.isEmpty else { return }
        await askIfNeeded()
        // Permission UI yields the main actor. The account that supplied these
        // jobs may have left while the sheet was open.
        guard stillCurrent(), authorized else { return }

        for job in waiting where !raised.contains(job.id) {
            guard stillCurrent() else { return }
            raised.insert(job.id)
            let (title, body) = Self.words(for: job)
            if Self.inQuietHours(now) {
                held.append((job.id, title, body))   // morning, not never
            } else {
                await post(id: job.id, title: title, body: body,
                           stillCurrent: stillCurrent)
                guard stillCurrent() else { return }
            }
        }
        // Anything parked overnight goes out once the hours end.
        if !Self.inQuietHours(now), !held.isEmpty {
            let due = held
            held.removeAll()
            for item in due {
                guard stillCurrent() else { return }
                await post(id: item.id, title: item.title, body: item.body,
                           stillCurrent: stillCurrent)
                guard stillCurrent() else { return }
            }
        }
        // A job that stopped waiting can raise again if it comes back round.
        guard stillCurrent() else { return }
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
        if job.workflow_state == "draft" {
            let asked = (job.result ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            let question = asked.isEmpty ? shortGoal : asked
            let trimmed = question.count > 140 ? String(question.prefix(137)) + "…" : question
            return ("I need one detail", trimmed)
        }
        if job.status == "awaiting_confirm" {
            return ("Ready when you are", shortGoal.isEmpty
                    ? "Something's ready for your OK."
                    : "\(shortGoal). Approve it when it looks right.")
        }
        let asked = (job.result ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        // job.result carries the question it stopped on. Prefer his own
        // words; fall back to the errand rather than to a status word.
        let question = asked.isEmpty ? shortGoal : asked
        let trimmed = question.count > 140 ? String(question.prefix(137)) + "…" : question
        return ("I need you for a second", trimmed)
    }

    private func post(id: String, title: String, body: String,
                      stillCurrent: @escaping @MainActor () -> Bool) async {
        let content = UNMutableNotificationContent()
        content.title = title
        content.body = body
        if AppPreferences.bool(forKey: AppPreferences.notificationSoundKey,
                               default: true) {
            content.sound = .default
        }
        content.userInfo = ["jobID": id]
        let identifier = "anticipy-job-\(id)"
        let request = UNNotificationRequest(
            identifier: identifier, content: content, trigger: nil)
        let centre = UNUserNotificationCenter.current()
        try? await centre.add(request)
        // `clearAll()` may have run while add was suspended. Remove this exact
        // request both ways (pending and already delivered) if its account or
        // generation no longer owns the completion.
        if NotificationLeasePolicy.removeAfterAdd(stillCurrent: stillCurrent()) {
            centre.removePendingNotificationRequests(withIdentifiers: [identifier])
            centre.removeDeliveredNotifications(withIdentifiers: [identifier])
        }
    }

    /// Signing out must not leave someone else's errands on the lock screen.
    func clearAll() {
        raised.removeAll()
        held.removeAll()
        UNUserNotificationCenter.current().removeAllDeliveredNotifications()
        UNUserNotificationCenter.current().removeAllPendingNotificationRequests()
    }
}
