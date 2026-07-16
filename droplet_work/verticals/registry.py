"""verticals.registry — the Field (vertical) -> Sub-option taxonomy.

This is the DATA that makes one voice agent adapt to any industry. Each vertical
carries a domain tone, a suggested persona/language, and hard COMPLIANCE guardrails;
each sub-option (use-case) carries the call GOAL, a lean domain DIRECTIVE (extra
brain instructions), and the SLOTS (data points) to collect.

Design rules (so it can never destabilise the live brain):
  * Every ``directive`` is SHORT (a few lines). The runtime prompt is length-
    sensitive — a bloated prompt makes the small model degenerate. Keep it lean.
  * Text is Hinglish/Hindi to match the brain's register (the composer renders
    English use-cases fine too — it just appends this block).
  * Nothing here executes; it is a pure dict the composer reads.

Extendable at runtime via verticals/overlay.py (a JSON file deep-merged over this),
so operators can add verticals/sub-options without a deploy.
"""

from __future__ import annotations

FIELDS: dict[str, dict] = {
    # ── MEDICAL / HEALTHCARE ─────────────────────────────────────────────────
    "medical": {
        "label": "Medical / Healthcare",
        "tone": "calm, caring, reassuring",
        "default_persona": "dr_meera",
        "default_languages": ["hi", "en"],
        "compliance": ("कभी diagnosis, इलाज, दवा या report की व्याख्या मत करो; "
                       "emergency लगे तो तुरंत doctor/नज़दीकी अस्पताल से मिलने को कहो; "
                       "इलाज ठीक होने का कोई guarantee मत दो।"),
        "sub_options": {
            "appointment_reminder": {
                "label": "Appointment reminder",
                "goal": "upcoming appointment confirm या reschedule कराना",
                "slots": ["patient_name", "preferred_date", "preferred_time"],
                "directive": ("caller राज़ी हो तो पसंदीदा दिन-समय पूछ कर slot confirm/reschedule कराओ; "
                              "ज़रूरी हो तो fasting/documents जैसी छोटी तैयारी याद दिला दो।"),
            },
            "lab_result_followup": {
                "label": "Lab result follow-up",
                "goal": "report तैयार होने की सूचना दे कर consult/pickup करवाना",
                "slots": ["patient_name", "preferred_date", "preferred_time"],
                "directive": ("बताओ कि report तैयार है और doctor से discuss करना अच्छा रहेगा; "
                              "report के values खुद मत पढ़ो/समझाओ — बस consult book कराओ।"),
            },
            "teleconsult_followup": {
                "label": "Teleconsultation follow-up",
                "goal": "पिछले consult के बाद हाल पूछ कर follow-up video/call book कराना",
                "slots": ["patient_name", "preferred_date", "preferred_time"],
                "directive": ("नरमी से हाल-चाल पूछो; अगर सुधार नहीं तो follow-up teleconsult book कराओ; "
                              "कोई नई दवा/खुराक मत सुझाओ।"),
            },
            "medication_adherence": {
                "label": "Medication adherence",
                "goal": "बताई गई दवा समय पर लेने की याद दिलाना + refill offer",
                "slots": ["patient_name"],
                "directive": ("दवा समय पर लेने की गर्मजोशी से याद दिलाओ; ज़रूरत हो तो refill/pharmacy "
                              "में मदद offer करो; खुराक बदलने की सलाह doctor पर छोड़ो।"),
            },
            "health_checkup_promo": {
                "label": "Preventive checkup promotion",
                "goal": "preventive health package की जानकारी दे कर checkup book कराना",
                "slots": ["patient_name", "preferred_date"],
                "directive": ("package के फ़ायदे simple भाषा में बताओ; डराओ मत; caller राज़ी हो तो "
                              "checkup slot book कराओ।"),
            },
        },
    },

    # ── SALES (B2B & B2C) ────────────────────────────────────────────────────
    "sales": {
        "label": "Sales",
        "tone": "confident, warm, value-led",
        "default_persona": "rohan_pro",
        "default_languages": ["hi", "en"],
        "compliance": ("दावे ईमानदार रखो; झूठा discount/urgency मत बनाओ; caller मना/DND कहे तो "
                       "सम्मान से call ख़त्म करो; कोई harassment नहीं।"),
        "sub_options": {
            "cold_outreach": {
                "label": "Cold outreach",
                "goal": "product/service में रुचि जगा कर अगला step (demo/meeting) तय करना",
                "slots": ["name", "need", "preferred_time"],
                "directive": ("पहले एक line में value बताओ, फिर एक सवाल से caller की ज़रूरत समझो; "
                              "रुचि दिखे तभी demo/meeting suggest करो।"),
            },
            "lead_qualification": {
                "label": "Lead qualification",
                "goal": "budget/need/timeline समझ कर lead को qualify करना",
                "slots": ["name", "need", "budget", "timeline", "decision_maker"],
                "directive": ("दोस्ताना अंदाज़ में ज़रूरत, बजट और timeline पूछो; interrogation जैसा मत करो; "
                              "fit दिखे तो अगला step तय करो।"),
            },
            "demo_booking": {
                "label": "Demo / meeting booking",
                "goal": "एक product demo या meeting slot book कराना",
                "slots": ["name", "preferred_date", "preferred_time"],
                "directive": ("demo का एक ठोस फ़ायदा बताओ, फिर दो time options दे कर slot lock कराओ।"),
            },
            "upsell_crosssell": {
                "label": "Upsell / cross-sell",
                "goal": "मौजूदा customer को relevant upgrade/add-on offer करना",
                "slots": ["name", "current_plan"],
                "directive": ("caller के मौजूदा use से जोड़ते हुए relevant upgrade suggest करो; "
                              "ज़बरदस्ती नहीं — फ़ायदा साफ़ रखो।"),
            },
            "renewal": {
                "label": "Renewal / retention",
                "goal": "expire हो रहे plan/subscription को renew कराना",
                "slots": ["name", "expiry_date"],
                "directive": ("renewal की समय पर याद दिलाओ; कोई दिक़्क़त हो तो सुनो और हल दो; "
                              "फिर renewal complete कराओ।"),
            },
            "winback": {
                "label": "Win-back (lapsed customer)",
                "goal": "छोड़ चुके customer को वापस लाना",
                "slots": ["name", "reason_left"],
                "directive": ("पहले जानो कि पहले क्यों छोड़ा (बिना बचाव किए सुनो), फिर उसी concern का "
                              "हल/offer दे कर वापसी का step दो।"),
            },
        },
    },

    # ── EDUCATION / EDTECH ───────────────────────────────────────────────────
    "education": {
        "label": "Education",
        "tone": "encouraging, guiding, patient",
        "default_persona": "neha_counsel",
        "default_languages": ["hi", "en"],
        "compliance": ("placement/नौकरी/score/visa का कोई guarantee मत दो; fees और शर्तें साफ़ बताओ; "
                       "माता-पिता/student पर दबाव मत डालो।"),
        "sub_options": {
            "admission_promotion": {
                "label": "Admission / course promotion",
                "goal": "course/program की जानकारी दे कर admission counselling book कराना",
                "slots": ["student_name", "course_interest", "preferred_time"],
                "directive": ("student के goal से जोड़ते हुए course की फ़िट बताओ; रुचि दिखे तो एक "
                              "counselling session book कराओ।"),
            },
            "counseling": {
                "label": "Career / admission counselling",
                "goal": "student के लक्ष्य समझ कर सही course/path suggest करना + अगला step",
                "slots": ["student_name", "goal", "current_level"],
                "directive": ("पहले सपने और मौजूदा स्तर समझो, फिर 1-2 सही रास्ते बताओ; बिना दबाव, "
                              "ईमानदारी से; फिर demo class/counselling तय करो।"),
            },
            "fee_reminder": {
                "label": "Fee reminder",
                "goal": "pending fee की शालीन याद दिलाना + payment में मदद",
                "slots": ["student_name", "due_date"],
                "directive": ("सम्मान से fee की याद दिलाओ; दिक़्क़त हो तो installment/मदद के विकल्प "
                              "बताओ; कोई धमकी नहीं।"),
            },
            "demo_class": {
                "label": "Free demo / trial class",
                "goal": "एक free demo/trial class schedule कराना",
                "slots": ["student_name", "preferred_date", "preferred_time"],
                "directive": ("free demo का फ़ायदा बताओ और दो slots दे कर book कराओ।"),
            },
            "reengagement": {
                "label": "Re-engagement (dropped student)",
                "goal": "बीच में छोड़ चुके student को वापस पढ़ाई से जोड़ना",
                "slots": ["student_name", "reason_paused"],
                "directive": ("बिना judge किए रुकने की वजह पूछो, फिर आसान वापसी का रास्ता (batch/schedule) "
                              "दे कर अगला step तय करो।"),
            },
        },
    },

    # ── FINANCE / BANKING / FINTECH ──────────────────────────────────────────
    "finance": {
        "label": "Finance / Banking",
        "tone": "trustworthy, clear, measured",
        "default_persona": "arjun_advisor",
        "default_languages": ["hi", "en"],
        "compliance": ("guaranteed returns का वादा कभी मत करो; कभी full card number/CVV/OTP/PIN/password "
                       "मत माँगो; उत्पाद market/शर्तों के अधीन है — साफ़ बताओ; RBI fair-practice का पालन।"),
        "sub_options": {
            "emi_reminder": {
                "label": "EMI / payment reminder",
                "goal": "आने वाली/pending EMI की शालीन याद दिलाना + payment path",
                "slots": ["name", "due_date"],
                "directive": ("सम्मान से due की याद दिलाओ; दिक़्क़त हो तो सुनो और सही payment/मदद बताओ; "
                              "कभी धमकी, दबाव या दूसरों को कर्ज़ की जानकारी नहीं।"),
            },
            "loan_offer": {
                "label": "Loan / credit offer",
                "goal": "eligible loan/credit की जानकारी दे कर application आगे बढ़ाना",
                "slots": ["name", "loan_type", "amount_needed"],
                "directive": ("साफ़ भाषा में offer और मोटे तौर पर शर्तें बताओ; ब्याज/शर्तें approval के "
                              "अधीन हैं — कहो; रुचि दिखे तो अगला step/documents बताओ।"),
            },
            "kyc_update": {
                "label": "KYC / profile update",
                "goal": "KYC/details update के लिए सही, सुरक्षित step बताना",
                "slots": ["name"],
                "directive": ("KYC update का official, सुरक्षित तरीक़ा बताओ; call पर कोई OTP/password/full "
                              "card number मत माँगो; branch/official link/app पर guide करो।"),
            },
            "investment_advisory": {
                "label": "Investment / SIP",
                "goal": "goal-based निवेश/SIP समझा कर एक review call तय करना",
                "slots": ["name", "goal", "horizon"],
                "directive": ("caller के लक्ष्य और समय समझो, फिर सामान्य, ईमानदार सुझाव; कोई guaranteed "
                              "return नहीं; detail के लिए advisor review book कराओ।"),
            },
            "card_sales": {
                "label": "Credit card / product sales",
                "goal": "relevant card/product के फ़ायदे बता कर apply कराना",
                "slots": ["name", "monthly_spend"],
                "directive": ("caller के खर्च से जुड़े 1-2 असली फ़ायदे बताओ; fees/charges छिपाओ मत; "
                              "रुचि दिखे तो apply का step दो।"),
            },
        },
    },

    # ── REAL ESTATE (matches the golden Godrej campaign) ─────────────────────
    "real_estate": {
        "label": "Real Estate",
        "tone": "warm, aspirational, credible",
        "default_persona": "aisha_warm",
        "default_languages": ["hi", "en"],
        "compliance": ("क़ीमतें indicative बताओ; RERA/approvals की सही जानकारी दो; ownership/appreciation "
                       "का झूठा guarantee नहीं।"),
        "sub_options": {
            "site_visit_booking": {
                "label": "Site visit / presentation booking",
                "goal": "एक free site visit या online presentation book कराना",
                "slots": ["name", "preferred_date", "preferred_time"],
                "directive": ("project का एक असली आकर्षण बताओ, फिर visit/presentation के दो options दे "
                              "कर slot lock कराओ।"),
            },
            "project_promotion": {
                "label": "New project launch",
                "goal": "नए project/inventory की जानकारी दे कर रुचि लेना",
                "slots": ["name", "budget", "config_interest"],
                "directive": ("location, config और शुरुआती क़ीमत (indicative) बताओ; बजट/ज़रूरत पूछ कर "
                              "fit हो तो visit तय करो।"),
            },
            "resale_followup": {
                "label": "Resale / inventory follow-up",
                "goal": "पहले दिखाई property/lead पर follow-up कर के decision आगे बढ़ाना",
                "slots": ["name", "property_ref"],
                "directive": ("पिछली बातचीत याद दिला कर हाल पूछो; कोई concern हो तो हल दो, फिर अगला "
                              "step तय करो।"),
            },
        },
    },

    # ── INSURANCE ────────────────────────────────────────────────────────────
    "insurance": {
        "label": "Insurance",
        "tone": "reassuring, honest, clear",
        "default_persona": "priya_support",
        "default_languages": ["hi", "en"],
        "compliance": ("mis-selling मत करो; यह एक proposal है, underwriting/शर्तों के अधीन — साफ़ कहो; "
                       "medical/निजी जानकारी दबाव से मत निकालो; झूठा दावा नहीं।"),
        "sub_options": {
            "policy_renewal": {
                "label": "Policy renewal",
                "goal": "expire हो रही policy समय पर renew कराना (कवर टूटने से बचाना)",
                "slots": ["name", "policy_no_last4", "expiry_date"],
                "directive": ("cover लगातार रहने का महत्व बताओ; renewal का आसान तरीक़ा बताओ; "
                              "पहचान के लिए policy के last-4 काफ़ी हैं, full/निजी details call पर मत माँगो।"),
            },
            "new_policy": {
                "label": "New policy / quote",
                "goal": "ज़रूरत समझ कर सही cover suggest करना + एक advisor call तय करना",
                "slots": ["name", "cover_type", "family_size"],
                "directive": ("caller की ज़रूरत (health/term/motor) समझो, फिर सामान्य suitable option "
                              "बताओ; premium/शर्तें underwriting पर निर्भर — कहो; detail के लिए review तय करो।"),
            },
            "claim_assist": {
                "label": "Claim assistance",
                "goal": "claim process में मदद कर के अगला ज़रूरी step बताना",
                "slots": ["name", "policy_no_last4", "claim_type"],
                "directive": ("नरमी से claim की स्थिति समझो; ज़रूरी documents/step साफ़ बताओ; कोई "
                              "settlement राशि/समय का पक्का वादा मत करो।"),
            },
        },
    },

    # ── E-COMMERCE / RETAIL ──────────────────────────────────────────────────
    "ecommerce": {
        "label": "E-commerce / Retail",
        "tone": "friendly, quick, helpful",
        "default_persona": "aisha_warm",
        "default_languages": ["hi", "en"],
        "compliance": ("दाम/उपलब्धता सही बताओ; झूठा stock/discount नहीं; refund/return नीति साफ़ रखो।"),
        "sub_options": {
            "abandoned_cart": {
                "label": "Abandoned cart recovery",
                "goal": "अधूरे order को complete कराना",
                "slots": ["name", "cart_item"],
                "directive": ("जो item cart में रहा उसका ज़िक्र कर के पूछो कोई दिक़्क़त तो नहीं; "
                              "size/payment/डिलीवरी doubt हो तो हल कर के checkout में मदद करो।"),
            },
            "order_confirmation": {
                "label": "Order / COD confirmation",
                "goal": "order (ख़ासकर COD) confirm कराना",
                "slots": ["name", "order_id"],
                "directive": ("order की पुष्टि करो; पता/delivery time verify करो; caller cancel चाहे "
                              "तो सम्मान से note करो।"),
            },
            "delivery_followup": {
                "label": "Delivery / feedback follow-up",
                "goal": "delivery का हाल पूछना + feedback/अगली खरीद",
                "slots": ["name", "order_id"],
                "directive": ("delivery ठीक मिली या नहीं पूछो; कोई issue हो तो resolve/escalate का step दो; "
                              "खुश हों तो relevant अगली खरीद suggest करो।"),
            },
        },
    },

    # ── HOSPITALITY / TRAVEL ─────────────────────────────────────────────────
    "hospitality": {
        "label": "Hospitality / Travel",
        "tone": "gracious, warm, attentive",
        "default_persona": "aisha_warm",
        "default_languages": ["hi", "en"],
        "compliance": ("दाम/उपलब्धता/नीतियाँ सही बताओ; झूठा वादा नहीं; cancellation शर्तें साफ़ रखो।"),
        "sub_options": {
            "booking_confirmation": {
                "label": "Booking confirmation",
                "goal": "reservation (hotel/table/ticket) confirm या adjust कराना",
                "slots": ["name", "date", "guests"],
                "directive": ("तारीख़, समय और लोगों की संख्या verify कर के booking confirm करो; कोई "
                              "special request हो तो note करो।"),
            },
            "offer_promotion": {
                "label": "Package / offer promotion",
                "goal": "relevant package/offer बता कर booking कराना",
                "slots": ["name", "travel_dates", "destination"],
                "directive": ("caller की योजना समझो, फिर relevant package का एक असली फ़ायदा बताओ; "
                              "रुचि दिखे तो book/hold कराओ।"),
            },
            "feedback": {
                "label": "Post-stay feedback",
                "goal": "अनुभव पूछना + दोबारा आने/review का step",
                "slots": ["name"],
                "directive": ("गर्मजोशी से अनुभव पूछो; कोई शिकायत हो तो सुनो और escalate करो; अच्छा हो "
                              "तो अगली visit/review के लिए धन्यवाद के साथ कहो।"),
            },
        },
    },

    # ── RECRUITMENT / HR ─────────────────────────────────────────────────────
    "recruitment": {
        "label": "Recruitment / HR",
        "tone": "professional, respectful, clear",
        "default_persona": "priya_support",
        "default_languages": ["hi", "en"],
        "compliance": ("job/salary/joining का झूठा वादा नहीं; कभी fee/पैसा मत माँगो; निजी जानकारी "
                       "सम्मान से और ज़रूरत भर लो।"),
        "sub_options": {
            "interview_scheduling": {
                "label": "Interview scheduling",
                "goal": "candidate का interview slot तय/confirm करना",
                "slots": ["candidate_name", "role", "preferred_date", "preferred_time"],
                "directive": ("role बता कर interest confirm करो, फिर दो slots दे कर interview तय करो; "
                              "mode (call/video/in-person) साफ़ बताओ।"),
            },
            "candidate_screening": {
                "label": "Initial screening",
                "goal": "basic fit (experience/notice/location/expectation) जाँचना",
                "slots": ["candidate_name", "experience", "notice_period", "location"],
                "directive": ("दोस्ताना अंदाज़ में experience, notice period, location और अपेक्षाएँ पूछो; "
                              "fit दिखे तो अगला step तय करो।"),
            },
            "offer_followup": {
                "label": "Offer follow-up",
                "goal": "दिए गए offer पर decision और joining confirm करना",
                "slots": ["candidate_name", "joining_date"],
                "directive": ("offer पर कोई सवाल/झिझक हो तो सुनो और हल दो; फिर joining की तारीख़ "
                              "confirm कराओ।"),
            },
        },
    },

    # ── LOGISTICS / DELIVERY ─────────────────────────────────────────────────
    "logistics": {
        "label": "Logistics / Delivery",
        "tone": "efficient, polite, clear",
        "default_persona": "rohan_pro",
        "default_languages": ["hi", "en"],
        "compliance": ("delivery समय/स्थिति सही बताओ; झूठा वादा नहीं; पते की पुष्टि सुरक्षित तरीक़े से।"),
        "sub_options": {
            "delivery_scheduling": {
                "label": "Delivery scheduling",
                "goal": "delivery का सुविधाजनक समय/पता तय करना",
                "slots": ["name", "address_confirm", "preferred_time"],
                "directive": ("पता और सुविधाजनक time-window verify करो; कोई landmark/instruction हो "
                              "तो note करो।"),
            },
            "failed_delivery": {
                "label": "Failed delivery re-attempt",
                "goal": "छूटी delivery का कारण समझ कर re-attempt तय करना",
                "slots": ["name", "order_id", "preferred_time"],
                "directive": ("बिना दोष दिए कारण समझो, फिर नया time/पता ले कर re-attempt schedule करो।"),
            },
            "pickup_request": {
                "label": "Pickup / return coordination",
                "goal": "return/pickup का समय और पता तय करना",
                "slots": ["name", "order_id", "preferred_time"],
                "directive": ("pickup का पता और time-window तय करो; item/packaging की छोटी शर्त हो "
                              "तो बता दो।"),
            },
        },
    },

    # ── FITNESS / WELLNESS ───────────────────────────────────────────────────
    "fitness": {
        "label": "Fitness / Wellness",
        "tone": "energetic, motivating, positive",
        "default_persona": "vikram_closer",
        "default_languages": ["hi", "en"],
        "compliance": ("कोई medical/diet इलाज की सलाह नहीं; unrealistic result का वादा नहीं; "
                       "health condition हो तो doctor की सलाह लेने को कहो।"),
        "sub_options": {
            "trial_booking": {
                "label": "Free trial / session booking",
                "goal": "एक free trial session/class book कराना",
                "slots": ["name", "goal", "preferred_time"],
                "directive": ("caller के fitness goal से जोड़ते हुए trial का फ़ायदा बताओ; फिर slot "
                              "book कराओ।"),
            },
            "membership_renewal": {
                "label": "Membership renewal",
                "goal": "membership renew कराना",
                "slots": ["name", "expiry_date"],
                "directive": ("progress/निरंतरता से जोड़ कर renewal की याद दिलाओ; कोई दिक़्क़त हो तो "
                              "plan option दो।"),
            },
            "reactivation": {
                "label": "Inactive member re-activation",
                "goal": "छूट चुके member को वापस लाना",
                "slots": ["name"],
                "directive": ("बिना judge किए रुकने की वजह पूछो, फिर आसान वापसी (new batch/goal) का "
                              "step दो।"),
            },
        },
    },

    # ── NGO / FUNDRAISING ────────────────────────────────────────────────────
    "ngo": {
        "label": "NGO / Non-profit",
        "tone": "warm, sincere, respectful",
        "default_persona": "neha_counsel",
        "default_languages": ["hi", "en"],
        "compliance": ("दान के उपयोग/tax लाभ की सही जानकारी दो; दबाव मत डालो; मना करें तो सम्मान से; "
                       "call पर संवेदनशील payment जानकारी मत माँगो।"),
        "sub_options": {
            "donation_appeal": {
                "label": "Donation appeal",
                "goal": "cause समझा कर एक contribution के लिए राज़ी करना",
                "slots": ["name", "amount_interest"],
                "directive": ("cause का असली असर एक-दो line में बताओ; बिना दबाव contribute का आसान "
                              "तरीक़ा दो; राशि caller पर छोड़ो।"),
            },
            "volunteer_signup": {
                "label": "Volunteer sign-up",
                "goal": "volunteer के तौर पर जोड़ना",
                "slots": ["name", "availability", "interest_area"],
                "directive": ("रुचि और उपलब्धता पूछो, फिर उपयुक्त volunteer भूमिका और अगला step बताओ।"),
            },
            "donor_followup": {
                "label": "Donor thank-you / follow-up",
                "goal": "पुराने donor को धन्यवाद + असर बता कर दोबारा जोड़ना",
                "slots": ["name"],
                "directive": ("सच्चे मन से धन्यवाद दो और उनके योगदान का असर बताओ; दोबारा जुड़ने का "
                              "सहज मौक़ा दो।"),
            },
        },
    },
}


def _norm(s) -> str:
    return str(s or "").strip().lower().replace(" ", "_").replace("-", "_")


_SYNONYMS = {"healthcare": "medical", "health": "medical", "edtech": "education",
             "banking": "finance", "fintech": "finance", "realestate": "real_estate",
             "property": "real_estate", "retail": "ecommerce", "hr": "recruitment",
             "travel": "hospitality", "wellness": "fitness", "nonprofit": "ngo",
             "non_profit": "ngo"}


def get_field(key, source: dict | None = None) -> dict | None:
    """Return a vertical descriptor (with ``key`` set), or None. Case/space-insensitive.

    ``source`` lets the composer pass an overlay-merged FIELDS table; defaults to the
    static registry.
    """
    table = source if source is not None else FIELDS
    k = _norm(key)
    if not k:
        return None
    if k not in table:
        k = _SYNONYMS.get(k, k)
    if k in table:
        d = dict(table[k])
        d["key"] = k
        return d
    return None


def get_sub_option(field: dict | None, sub_key) -> dict | None:
    """Return a sub-option descriptor within a field (with ``key`` set), or None."""
    if not field:
        return None
    subs = field.get("sub_options") or {}
    sk = _norm(sub_key)
    if not sk or sk not in subs:
        return None
    d = dict(subs[sk])
    d["key"] = sk
    return d


def list_fields() -> list[dict]:
    """Catalogue for a UI: each vertical + its sub-options (labels/goals only)."""
    out = []
    for key, f in FIELDS.items():
        subs = [{"key": sk, "label": sv.get("label", sk), "goal": sv.get("goal", "")}
                for sk, sv in (f.get("sub_options") or {}).items()]
        out.append({
            "key": key, "label": f.get("label", key), "tone": f.get("tone", ""),
            "default_persona": f.get("default_persona"),
            "default_languages": list(f.get("default_languages") or []),
            "sub_options": subs,
        })
    return out
