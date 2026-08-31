#!/bin/sh
# One honest iOS logic gate. These suites compile the real pure-Foundation
# production sources directly, so they need no simulator, signing, or duplicate
# XCTest implementation. The app build is a separate release gate.
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)

sh "$HERE/run_cursor_tests.sh"
# The gap law and the engine seam — the gap measured, drained, marked; the
# recognizer swappable under a cursor that never learns which engine spoke.
sh "$HERE/run_gap_engine_tests.sh"
sh "$HERE/run_heard_tests.sh"
sh "$HERE/run_flush_policy_tests.sh"
# WHEN the words started and WHEN the flush produced them — two instants, not
# one number written into three columns. Placed next to the flush policy
# because it is the other half of the same moment: that one decides when a line
# leaves, this one decides what the line says about the time it took.
sh "$HERE/run_capture_envelope_tests.sh"
sh "$HERE/run_end_errand_tests.sh"
sh "$HERE/run_reset_message_tests.sh"
sh "$HERE/run_line_source_tests.sh"
sh "$HERE/run_capture_source_tests.sh"
# The three stranger-gate legs that live in this tree: whose first run this is,
# whether enrolment is ever offered, and whether the card shows the receipt the
# server actually verified.
#
# Placed HERE, early, deliberately: `set -eu` stops this file at the first
# failure, and run_watchdog_policy_tests.sh below is red on a compile error
# (ListenSessionFacts is not passed to its swiftc invocation), so everything
# after it is unreachable today. That is pre-existing and not fixed here, but a
# suite nobody can reach is a suite nobody has.
sh "$HERE/run_first_run_tests.sh"
# WHICH screen that first run opens on, now that the sign-in door stands in
# the middle of it. The two beats that ask for nothing moved in front of the
# door, which makes three states real that nobody can reach by tapping:
# force-quitting between the second beat and the door, signing out and handing
# the phone on, and reinstalling onto an account that already exists. Beside
# the ownership suite, and early, for the reachability reason above.
sh "$HERE/run_first_run_route_tests.sh"
# Whose phone is this — the same question one step earlier. First-run ownership
# decides whether the TOUR replays for a new account; this decides whether the
# five device-local answers to "who are you" go with the account that left.
# Placed beside it, and early, for the reachability reason above.
sh "$HERE/run_owner_mirror_tests.sh"
# The third question about the same phone, one screen further in: not whose
# tour this is, nor whose answers are still on the handset, but whether what
# first run SAYS about them is true when it says it. The track counted the
# account they had just made as zero; the last beat re-interrogated somebody
# for an email and a number it already held; and the finale promised "Give me
# a day. You'll see." to a person who had declined the microphone thirty
# seconds earlier. Beside the other two, and early, for the reachability
# reason above.
sh "$HERE/run_first_run_copy_tests.sh"
sh "$HERE/run_enrollment_offer_tests.sh"
sh "$HERE/run_job_receipt_tests.sh"
# The same card from the other end. That one asks what the server proved
# before it says "done"; this asks which section a job reaches at all — and
# whether a job the owner STOPPED reaches one. `cancelled` matched none of
# Home's three filters, so a stop deleted the row from the screen along with
# the only sentence saying it might have gone through anyway. Early, for the
# reachability reason above.
sh "$HERE/run_home_feed_tests.sh"
# What Home SAYS once it has placed a job — the same screen one step later. Four
# of its sentences carry a number the phone counted: how many things are waiting
# on a browser, how many interview answers she already holds, how long the
# microphone has been gone, and what the day-zero examples read as out loud.
# Three of the four were saying the wrong thing (a queue nobody named, "Six
# questions" typed into the prose, and a recovery claimed in the present tense
# for the rest of the day), and this suite compiles the real wording out of
# ContentView.swift and asks it.
sh "$HERE/run_home_copy_tests.sh"
# The phone as a HAND, for one verb. Placed beside the receipt because it is the
# same argument from the other end: that one asks what the server proved before
# the card says "done", this one asks what has to be true before the phone
# touches the calendar at all. Its load-bearing leg is that the undo resolves
# from an id WE minted — EKEvent.eventIdentifier is assigned by EventKit ON
# SAVE, and an undo that needs it is the shape the Shelf 2 spec excludes by
# name. Early, like the three above it: `set -eu` stops this file at the first
# failure, so a suite placed late is a suite that may never run.
sh "$HERE/run_calendar_hand_tests.sh"
# LOCAL-FIRST rule 1, the iOS half: no vendor socket, no vendor credential, no
# retry loop against a permanent refusal, and copy that says what is true.
sh "$HERE/run_local_ears_tests.sh"
sh "$HERE/run_stale_extension_tests.sh"
sh "$HERE/run_reachable_number_tests.sh"
# Whether a field SAYS what just happened to it. Beside the reachable-number
# suite because it is the other end of the same failure: that one asks whether
# a number can be texted, this one asks whether a person was told when saving it
# did not work. Settings had two caption states where it needed four, so "+44"
# plus Save produced a silent false and nothing on the screen at all.
sh "$HERE/run_field_caption_tests.sh"
sh "$HERE/run_notifier_tests.sh"
sh "$HERE/run_context_grant_tests.sh"
# The same consent screen one moment later: what she says back once the grant
# lands, and what the button said before it. Beside the gate suite because it
# is the other half of the same sentence — that one holds "no grant, no read",
# this one holds "and here is exactly what the read produced", including the
# lines that did not fit on the sheet.
sh "$HERE/run_context_receipt_tests.sh"
sh "$HERE/run_interview_tests.sh"
# What that interview OFFERS, one screen later. Beside it because it reads the
# same `InterviewProgress`: that suite asks whether an answer is recorded and a
# skip is not, this one asks what Settings then SAYS about it. One section was
# telling a person two things about themselves and both could be false at once —
# a button offering six questions above a caption reading "You've answered 4 of
# 6", and that caption opening "You haven't told me anything about your life
# yet" on a screen holding their name, their number and their calendar grant.
# It also carries the listening row's measured silence, whose legs are law legs:
# no threshold decides when quiet becomes a finding, and no colour judges it.
sh "$HERE/run_interview_invite_tests.sh"
sh "$HERE/run_supervised_read_tests.sh"
sh "$HERE/run_theme_contract_tests.sh"
sh "$HERE/run_journal_tests.sh"
sh "$HERE/run_tally_tests.sh"
# How the tally's seconds are SAID. Beside it, because it is the same numbers
# one step later: that suite folds a day of listening out of the journal, this
# one holds the wording those seconds get on every screen that reports them.
# The diagnostics screen kept it private; Settings and the home card are being
# built against the same `unheardForSeconds`, and the argument all three rest on
# is that no threshold decides what counts as too long — which holds only while
# "6 hr 20 min" is not "6.3 hours" one screen over.
sh "$HERE/run_duration_tests.sh"
sh "$HERE/run_battery_tests.sh"
sh "$HERE/run_watchdog_policy_tests.sh"
sh "$HERE/run_resume_policy_tests.sh"
sh "$HERE/run_control_policy_tests.sh"
# The call sense. A call is a hole in the day where the ears go deaf, and today
# it looks exactly like silence: this decides, from CallKit's call list and the
# clock alone, when the microphone is gone to a call, when it is back, and where
# the conversation boundaries were. Its law legs live in the runner — no
# duration threshold, no identity, and no claim about FaceTime that a device has
# not made.
sh "$HERE/run_call_presence_tests.sh"
sh "$HERE/run_interruption_contract_tests.sh"
# The crash boundary beside the interruption contract: route notifications
# leave AVAudioSession's stack before rebuilding, the tap-bearing engine is
# retired rather than reused, and AVFAudio's NSException becomes a retry.
sh "$HERE/run_audio_recovery_tests.sh"
# Not a logic suite: it asks whether the build number still identifies these
# bytes. Last, because it is the one leg that reads git rather than source, and
# a red one here means "bump it before you commit", not "the code is wrong".
sh "$HERE/run_build_number_tests.sh"

echo "iOS logic gate: all suites passed"
