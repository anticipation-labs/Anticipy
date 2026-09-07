import SwiftUI

/// Who she thinks you are, and where she reaches you.
///
/// Screen 4 of the seven Jose supplied: label-left, value-right rows, and the
/// confirm control as a CIRCULAR BUTTON IN THE HEADER, greyed until there is
/// something to save. That last part is the real change and not a decoration —
/// the old screen carried two separate Save buttons, one per section, and a
/// person who edited their name and their number had to find both.
///
/// EVERYTHING FIX 7 SHIPPED IS CARRIED ACROSS, and it is carried across whole
/// rather than re-derived, because every clause of it was written against a bug
/// that had already shipped:
///
///   * the placeholder names no country. `e164` refuses to guess one and
///     `DiallingCode` reads this phone's own region, so a grey "+1" was the
///     last place still assuming one for somebody.
///   * the prefill runs on appear, because `e164`'s refusal is only a fix if
///     the country is IN FRONT of the person rather than missing behind them.
///   * save is gated on `session.e164(...) != nil`, never on emptiness. The
///     field is never empty once the prefill lands, so an emptiness test stops
///     meaning anything — and it never matched `saveOwnerPhone`, which begins
///     by refusing text `e164` cannot read. "+44" lit the button, returned
///     false, and reported nothing.
///   * what was SENT is what the verdict is about. Reading the field inside the
///     Task meant a digit typed mid-flight was the digit that got saved, and
///     the verdict landed on whatever the field held when it came back.
///   * a "Saved." from the last value must not sit over the next one.
struct SettingsProfileView: View {
    @ObservedObject var session: AnticipySession
    @Environment(\.dismiss) private var dismiss

    @State private var firstName = ""
    @State private var lastName = ""
    @State private var email = ""
    @State private var birthday = ""
    @State private var detailsAttempt: FieldCaption.Attempt = .untried
    @State private var savingDetails = false

    @State private var phoneField = ""
    @State private var phoneAttempt: FieldCaption.Attempt = .untried
    @State private var savingPhone = false
    @State private var removingPhone = false
    @State private var numberRemoved = false

    /// Has anything actually changed? The header button is inert otherwise.
    ///
    /// Compared against the session rather than against a snapshot taken on
    /// appear: the session IS the saved truth, so this cannot drift out of step
    /// with what the server holds the way a captured copy would.
    private var detailsChanged: Bool {
        firstName != session.ownerFirstName
            || lastName != session.ownerLastName
            || email != session.ownerEmail
            || birthday != session.ownerBirthday
    }

    /// The number is different: changed is not enough, it must also be SAVEABLE.
    /// This is fix 7's predicate, unchanged.
    private var phoneSaveable: Bool {
        phoneField != session.ownerPhone && session.e164(phoneField) != nil
    }

    private var canSave: Bool {
        (detailsChanged || phoneSaveable)
            && !savingDetails && !savingPhone && !removingPhone
    }

    private var hasSavedNumber: Bool {
        switch session.canonicalOwnerPhoneState {
        case .valid, .invalid: return true
        case .none: return false
        case .unknown:
            return !session.ownerPhone
                .trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        }
    }

    var body: some View {
        SheetChrome(
            title: "Profile",
            leading: .back,
            onLeading: { dismiss() },
            trailing: SheetAction(systemImage: "checkmark",
                                  label: "Save",
                                  isEnabled: canSave) { save() }
        ) {
            GroupedCard {
                ValueRow("First name", text: $firstName,
                         placeholder: "Jose", contentType: .givenName)
                ValueRow("Last name", text: $lastName,
                         placeholder: "Cruz Lopez", contentType: .familyName)
                ValueRow("Email", text: $email,
                         placeholder: "you@email.com",
                         keyboard: .emailAddress, contentType: .emailAddress)
                ValueRow("Birthday", text: $birthday,
                         placeholder: "YYYY-MM-DD", keyboard: .numbersAndPunctuation)
            }

            FieldCaptionLine(
                text: firstName + lastName + email + birthday,
                // These fields have no shared completeness rule. Passing
                // `detailsChanged` here made an unchanged, already-saved
                // profile render the phone component's "country code" error.
                // The attempt still carries save success or failure; nil only
                // prevents this view from inventing validation it does not own.
                complete: nil,
                attempt: detailsAttempt,
                words: .init(
                    neutral: "Used for approved booking and signup forms. Payment details are never stored or filled.",
                    saved: "Profile details saved."))

            SectionHeader("Your number")

            GroupedCard {
                ValueRow("Number", text: $phoneField,
                         placeholder: "604 555 0123",
                         keyboard: .phonePad, contentType: .telephoneNumber)
            }

            FieldCaptionLine(
                text: phoneField,
                complete: session.e164(phoneField) != nil,
                attempt: phoneAttempt,
                words: .init(
                    neutral: phoneField.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                        ? "No number means in-app alerts only. Add one for text approvals and results."
                        : "This number receives text approvals and results; they also stay in the app.",
                    saved: "Phone number saved."))

            if numberRemoved {
                Label("Number removed. Updates will stay in the app.",
                      systemImage: "checkmark.circle")
                    .font(.caption)
                    .foregroundStyle(Theme.text2)
                    .fixedSize(horizontal: false, vertical: true)
            }

            if hasSavedNumber {
                GroupedCard {
                    // REVERSIBLE: no confirmation, and the footnote below
                    // already says why — "You can add a number again here
                    // anytime." Removing a number takes away a channel, not a
                    // record; nothing written is lost and nothing has to be
                    // recovered.
                    DestructiveRow(
                        removingPhone ? "Removing number…" : "Remove number",
                        systemImage: "phone.down") {
                            removeNumber()
                        }
                        .disabled(removingPhone || savingPhone)
                }
                FootnoteText("Use in-app updates only. You can add a number again here anytime.")
            }

            // Account and handset lifecycle controls live together in
            // Privacy & Data, not inside an editable profile card. That screen
            // owns the full forget flow: stop listening, clear this account's
            // pending speech and local identity, and verify browser unpairing.
        }
        // The prefill, verbatim from fix 7. Somebody who has never saved a
        // number met an empty field, typed the number they have typed their
        // whole life, and was refused with nothing on screen saying what was
        // missing.
        .onAppear {
            if firstName.isEmpty { firstName = session.ownerFirstName }
            if lastName.isEmpty { lastName = session.ownerLastName }
            if email.isEmpty { email = session.ownerEmail }
            if birthday.isEmpty { birthday = session.ownerBirthday }
            if phoneField.isEmpty {
                phoneField = session.ownerPhone.isEmpty
                    ? DiallingCode.forThisPhone() : session.ownerPhone
            }
        }
        .onChange(of: firstName) { _ in detailsAttempt = .untried }
        .onChange(of: lastName) { _ in detailsAttempt = .untried }
        .onChange(of: email) { _ in detailsAttempt = .untried }
        .onChange(of: birthday) { _ in detailsAttempt = .untried }
        .onChange(of: phoneField) { value in
            phoneAttempt = .untried
            if !value.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                numberRemoved = false
            }
        }
    }

    /// One button, two saves, and each keeps its own verdict.
    ///
    /// They are not merged into one request: `saveOwnerDetails` and
    /// `saveOwnerPhone` fail for different reasons and each has its own caption
    /// underneath saying so. A single "couldn't save" over both would be the
    /// silent failure fix 7 removed, rebuilt one level up.
    private func save() {
        Haptics.engage()
        if detailsChanged { saveDetails() }
        if phoneSaveable { savePhone() }
    }

    private func saveDetails() {
        guard !savingDetails else { return }
        savingDetails = true
        // READ ONCE, HERE. Reading the fields inside the Task meant a character
        // typed while the request was in flight was the one that got saved, and
        // the verdict then landed on whatever the fields held when it returned.
        let sent = (firstName, lastName, email, birthday)
        Task {
            let ok = await session.saveOwnerDetails(
                first: sent.0, last: sent.1, email: sent.2, birthday: sent.3)
            savingDetails = false
            guard (firstName, lastName, email, birthday) == sent else { return }
            detailsAttempt = ok ? .saved : .failed
            if ok { Haptics.success() }
        }
    }

    private func savePhone() {
        guard !savingPhone else { return }
        savingPhone = true
        let sent = phoneField
        Task {
            let ok = await session.saveOwnerPhone(sent)
            savingPhone = false
            guard phoneField == sent else { return }
            phoneAttempt = ok ? .saved : .failed
            if ok { Haptics.success() }
        }
    }

    private func removeNumber() {
        guard !removingPhone, !savingPhone else { return }
        Haptics.engage()
        removingPhone = true
        Task {
            let ok = await session.removeOwnerPhone()
            removingPhone = false
            if ok {
                phoneField = ""
                phoneAttempt = .untried
                numberRemoved = true
                Haptics.success()
            } else {
                phoneAttempt = .failed
            }
        }
    }
}
