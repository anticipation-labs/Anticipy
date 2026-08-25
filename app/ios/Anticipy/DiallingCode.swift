import Foundation

/// The country code this phone already knows, so nobody has to know what
/// E.164 is.
///
/// `AnticipySession.e164` used to prepend "+1" to any bare ten-digit number, so
/// a stranger in London finished sign-up with a US number on their account and
/// never received one text all week. The fix is that e164 refuses to guess a
/// country — and the refusal only stops being a new dead end if the number
/// field already carries the right country when the person arrives at it.
///
/// This is where that comes from, and it is not a guess: iOS is already set to
/// a region, because the person set it when they set up the phone. The code it
/// yields is PUT IN THE FIELD, in front of them, where a wrong one is one tap
/// to fix. That is the whole difference from the bug it replaces — the old
/// "+1" was invisible, and nothing on any screen ever showed it back.
///
/// The table is ITU-T E.164 assignment data: which numbers belong to which
/// country is not a judgement, and nothing here decides what anything MEANS.
/// A region this table does not carry yields a bare "+" — an honest empty
/// prompt to type a country code — rather than a plausible wrong one.
enum DiallingCode {

    /// The dialling code for this phone's own region, ready to be typed after:
    /// "+44" on a phone set to the United Kingdom, "+1" on one set to Canada,
    /// "+" when iOS reports a region this table has never heard of.
    ///
    /// `region` is injectable so the tests can ask about a country nobody is
    /// holding. Nothing in the app passes it.
    static func forThisPhone(region: String? = nil) -> String {
        let id = region ?? Locale.current.region?.identifier ?? ""
        return forRegion(id) ?? "+"
    }

    /// "GB" -> "+44". nil when the region is empty, malformed, or unlisted —
    /// never a fallback, because a fallback here is the original bug.
    static func forRegion(_ region: String) -> String? {
        let key = region.trimmingCharacters(in: .whitespaces).uppercased()
        guard key.count == 2 else { return nil }
        guard let code = table[key] else { return nil }
        return "+" + code
    }

    /// Every region this table carries, for the test that checks the shape of
    /// all of them rather than the four somebody thought to name.
    static var regions: [String] { Array(table.keys) }

    // ----------------------------------------------------------------------
    // Two letters then its digits, space separated. A dictionary literal of
    // this size is minutes of Swift type-checking; this is one string.
    // ----------------------------------------------------------------------
    private static let raw = """
    US1 CA1 AG1 AI1 AS1 BB1 BM1 BS1 DM1 DO1 GD1 GU1 JM1 KN1 KY1 LC1 MP1 MS1 \
    PR1 SX1 TC1 TT1 VC1 VG1 VI1 \
    EG20 SS211 MA212 EH212 DZ213 TN216 LY218 GM220 SN221 MR222 ML223 GN224 \
    CI225 BF226 NE227 TG228 BJ229 MU230 LR231 SL232 GH233 NG234 TD235 CF236 \
    CM237 CV238 ST239 GQ240 GA241 CG242 CD243 AO244 GW245 IO246 AC247 SC248 \
    SD249 RW250 ET251 SO252 DJ253 KE254 TZ255 UG256 BI257 MZ258 ZM260 MG261 \
    RE262 YT262 ZW263 NA264 MW265 LS266 BW267 SZ268 KM269 ZA27 SH290 ER291 \
    AW297 FO298 GL299 \
    GR30 NL31 BE32 FR33 ES34 GI350 PT351 LU352 IE353 IS354 AL355 MT356 CY357 \
    FI358 AX358 BG359 HU36 LT370 LV371 EE372 MD373 AM374 BY375 AD376 MC377 \
    SM378 VA379 UA380 RS381 ME382 XK383 HR385 SI386 BA387 MK389 IT39 RO40 \
    CH41 CZ420 SK421 LI423 AT43 GB44 GG44 IM44 JE44 DK45 SE46 NO47 SJ47 PL48 \
    DE49 \
    FK500 BZ501 GT502 SV503 HN504 NI505 CR506 PA507 PM508 HT509 PE51 MX52 \
    CU53 AR54 BR55 CL56 CO57 VE58 GP590 BL590 MF590 BO591 GY592 EC593 GF594 \
    PY595 MQ596 SR597 UY598 CW599 BQ599 \
    MY60 AU61 ID62 PH63 NZ64 SG65 TH66 TL670 NF672 BN673 NR674 PG675 TO676 \
    SB677 VU678 FJ679 PW680 WF681 CK682 NU683 WS685 KI686 NC687 TV688 PF689 \
    TK690 FM691 MH692 \
    RU7 KZ7 \
    JP81 KR82 VN84 CN86 HK852 MO853 KH855 LA856 BD880 TW886 \
    TR90 IN91 PK92 AF93 LK94 MM95 MV960 LB961 JO962 SY963 IQ964 KW965 SA966 \
    YE967 OM968 PS970 AE971 IL972 BH973 QA974 BT975 MN976 NP977 IR98 TJ992 \
    TM993 AZ994 GE995 KG996 UZ998
    """

    private static let table: [String: String] = {
        var out: [String: String] = [:]
        for token in raw.split(whereSeparator: { $0 == " " || $0.isNewline }) {
            let entry = String(token)
            guard entry.count > 2 else { continue }
            let region = String(entry.prefix(2))
            let code = String(entry.dropFirst(2))
            // A malformed entry is dropped rather than served: a region with
            // no code is an unlisted region, which is a bare "+", which is
            // the honest answer. A region with a bad code would be the bug.
            guard region.allSatisfy({ $0.isLetter }),
                  code.allSatisfy({ $0.isNumber }),
                  !code.hasPrefix("0"), code.count <= 3 else { continue }
            out[region] = code
        }
        return out
    }()
}
