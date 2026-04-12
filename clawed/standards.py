"""Standards database for Common Core (CCSS), NGSS, and C3 Framework."""

from __future__ import annotations

# Each entry: (code, description, grade_band)
STANDARDS: dict[str, list[tuple[str, str, str]]] = {
    "math": [
        # K-2
        ("CCSS.MATH.K.CC.1", "Count to 100 by ones and tens", "K"),
        ("CCSS.MATH.K.OA.1", "Represent addition and subtraction with objects, drawings, and equations", "K"),
        ("CCSS.MATH.1.OA.1", "Use addition and subtraction within 20 to solve word problems", "1"),
        ("CCSS.MATH.1.NBT.1", "Count to 120, starting at any number less than 120", "1"),
        ("CCSS.MATH.2.OA.1", "Use addition and subtraction within 100 to solve one- and two-step word problems", "2"),
        (
            "CCSS.MATH.2.NBT.1",
            "Understand that the three digits of a three-digit number represent hundreds, tens, and ones",
            "2",
        ),
        # 3-5
        ("CCSS.MATH.3.OA.1", "Interpret products of whole numbers (e.g., 5 x 7 as the total in 5 groups of 7)", "3"),
        (
            "CCSS.MATH.3.NF.1",
            "Understand a fraction 1/b as the quantity formed by 1 part when a whole is partitioned into b equal parts",
            "3",
        ),
        ("CCSS.MATH.4.OA.1", "Interpret a multiplication equation as a comparison (e.g., 35 = 5 x 7)", "4"),
        (
            "CCSS.MATH.4.NF.1",
            "Explain why a fraction a/b is equivalent to (n x a)/(n x b) using visual fraction models",
            "4",
        ),
        ("CCSS.MATH.5.NF.1", "Add and subtract fractions with unlike denominators", "5"),
        (
            "CCSS.MATH.5.NBT.1",
            "Recognize that in a multi-digit number, a digit in one place represents 10 times as much as it represents"
            "in the place to its right",
            "5",
        ),
        # 6-8
        (
            "CCSS.MATH.6.RP.1",
            "Understand the concept of a ratio and use ratio language to describe a ratio relationship",
            "6",
        ),
        ("CCSS.MATH.6.EE.1", "Write and evaluate numerical expressions involving whole-number exponents", "6"),
        ("CCSS.MATH.7.RP.1", "Compute unit rates associated with ratios of fractions", "7"),
        (
            "CCSS.MATH.7.EE.1",
            "Apply properties of operations to add, subtract, factor, and expand linear expressions",
            "7",
        ),
        (
            "CCSS.MATH.8.EE.1",
            "Know and apply the properties of integer exponents to generate equivalent numerical expressions",
            "8",
        ),
        ("CCSS.MATH.8.F.1", "Understand that a function is a rule that assigns to each input exactly one output", "8"),
        ("CCSS.MATH.8.G.1", "Verify experimentally the properties of rotations, reflections, and translations", "8"),
        # 9-12
        (
            "CCSS.MATH.HSA.REI.1",
            "Explain each step in solving a simple equation as following from the equality of numbers",
            "9-12",
        ),
        (
            "CCSS.MATH.HSA.CED.1",
            "Create equations and inequalities in one variable and use them to solve problems",
            "9-12",
        ),
        (
            "CCSS.MATH.HSF.IF.1",
            "Understand that a function from one set to another assigns each element of the domain exactly one element"
            "of the range",
            "9-12",
        ),
        (
            "CCSS.MATH.HSG.CO.1",
            "Know precise definitions of angle, circle, perpendicular line, parallel line, and line segment",
            "9-12",
        ),
        (
            "CCSS.MATH.HSS.ID.1",
            "Represent data with plots on the real number line (dot plots, histograms, and box plots)",
            "9-12",
        ),
    ],
    "ela": [
        # K-2
        (
            "CCSS.ELA-LITERACY.RL.K.1",
            "With prompting and support, ask and answer questions about key details in a text",
            "K",
        ),
        ("CCSS.ELA-LITERACY.RF.K.1", "Demonstrate understanding of the organization and basic features of print", "K"),
        ("CCSS.ELA-LITERACY.RL.1.1", "Ask and answer questions about key details in a text", "1"),
        (
            "CCSS.ELA-LITERACY.W.1.1",
            "Write opinion pieces in which they introduce the topic, state an opinion, and supply a reason",
            "1",
        ),
        (
            "CCSS.ELA-LITERACY.RL.2.1",
            "Ask and answer such questions as who, what, where, when, why, and how about key details",
            "2",
        ),
        (
            "CCSS.ELA-LITERACY.W.2.1",
            "Write opinion pieces introducing the topic, stating an opinion, and supplying reasons",
            "2",
        ),
        # 3-5
        (
            "CCSS.ELA-LITERACY.RL.3.1",
            "Ask and answer questions to demonstrate understanding of a text, referring explicitly to the text",
            "3",
        ),
        (
            "CCSS.ELA-LITERACY.W.3.1",
            "Write opinion pieces on topics or texts, supporting a point of view with reasons",
            "3",
        ),
        (
            "CCSS.ELA-LITERACY.RL.4.1",
            "Refer to details and examples in a text when explaining what the text says explicitly and when drawing"
            "inferences",
            "4",
        ),
        (
            "CCSS.ELA-LITERACY.W.4.1",
            "Write opinion pieces on topics or texts, supporting a point of view with reasons and information",
            "4",
        ),
        (
            "CCSS.ELA-LITERACY.RL.5.1",
            "Quote accurately from a text when explaining what the text says explicitly and when drawing inferences",
            "5",
        ),
        (
            "CCSS.ELA-LITERACY.RI.5.1",
            "Quote accurately from a text and make relevant connections when explaining what the text says",
            "5",
        ),
        # 6-8
        (
            "CCSS.ELA-LITERACY.RL.6.1",
            "Cite textual evidence to support analysis of what the text says explicitly as well as inferences drawn",
            "6",
        ),
        ("CCSS.ELA-LITERACY.W.6.1", "Write arguments to support claims with clear reasons and relevant evidence", "6"),
        (
            "CCSS.ELA-LITERACY.RL.7.1",
            "Cite several pieces of textual evidence to support analysis of what the text says",
            "7",
        ),
        ("CCSS.ELA-LITERACY.W.7.1", "Write arguments to support claims with clear reasons and relevant evidence", "7"),
        (
            "CCSS.ELA-LITERACY.RL.8.1",
            "Cite the textual evidence that most strongly supports an analysis of what the text says",
            "8",
        ),
        ("CCSS.ELA-LITERACY.W.8.1", "Write arguments to support claims with clear reasons and relevant evidence", "8"),
        # 9-12
        (
            "CCSS.ELA-LITERACY.RL.9-10.1",
            "Cite strong and thorough textual evidence to support analysis of what the text says",
            "9-12",
        ),
        (
            "CCSS.ELA-LITERACY.W.9-10.1",
            "Write arguments to support claims in an analysis of substantive topics or texts",
            "9-12",
        ),
        (
            "CCSS.ELA-LITERACY.RL.11-12.1",
            "Cite strong and thorough textual evidence to support analysis, including determining where the text"
            "leaves matters uncertain",
            "11-12",
        ),
        (
            "CCSS.ELA-LITERACY.W.11-12.1",
            "Write arguments to support claims in an analysis of substantive topics or texts, using valid reasoning"
            "and relevant evidence",
            "11-12",
        ),
    ],
    "science": [
        # Middle School (6-8)
        ("MS-LS1-1", "Conduct an investigation to provide evidence that living things are made of cells", "6-8"),
        (
            "MS-LS1-2",
            "Develop and use a model to describe the function of a cell as a whole and ways cell parts contribute to"
            "the function",
            "6-8",
        ),
        (
            "MS-LS1-6",
            "Construct a scientific explanation based on evidence for the role of photosynthesis in the cycling of"
            "matter and flow of energy",
            "6-8",
        ),
        (
            "MS-LS1-7",
            "Develop a model to describe how food is rearranged through chemical reactions forming new molecules that"
            "support growth",
            "6-8",
        ),
        (
            "MS-LS2-1",
            "Analyze and interpret data to provide evidence for the effects of resource availability on organisms and"
            "populations",
            "6-8",
        ),
        (
            "MS-LS2-3",
            "Develop a model to describe the cycling of matter and flow of energy among living and nonliving parts of"
            "an ecosystem",
            "6-8",
        ),
        (
            "MS-PS1-1",
            "Develop models to describe the atomic composition of simple molecules and extended structures",
            "6-8",
        ),
        (
            "MS-PS1-2",
            "Analyze and interpret data on the properties of substances before and after the substances interact to"
            "determine if a chemical reaction has occurred",
            "6-8",
        ),
        (
            "MS-PS2-1",
            "Apply Newton's Third Law to design a solution to a problem involving the motion of two colliding objects",
            "6-8",
        ),
        (
            "MS-ESS1-1",
            "Develop and use a model of the Earth-sun-moon system to describe the cyclic patterns of lunar phases,"
            "eclipses, and seasons",
            "6-8",
        ),
        (
            "MS-ESS2-1",
            "Develop a model to describe the cycling of Earth's materials and the flow of energy that drives this"
            "process",
            "6-8",
        ),
        (
            "MS-ESS3-3",
            "Apply scientific principles to design a method for monitoring and minimizing a human impact on the"
            "environment",
            "6-8",
        ),
        # High School (9-12)
        (
            "HS-LS1-1",
            "Construct an explanation based on evidence for how the structure of DNA determines the structure of"
            "proteins",
            "9-12",
        ),
        (
            "HS-LS1-2",
            "Develop and use a model to illustrate the hierarchical organization of interacting systems that provide"
            "specific functions within multicellular organisms",
            "9-12",
        ),
        (
            "HS-LS1-5",
            "Use a model to illustrate how photosynthesis transforms light energy into stored chemical energy",
            "9-12",
        ),
        (
            "HS-LS1-7",
            "Use a model to illustrate that cellular respiration is a chemical process whereby the bonds of food"
            "molecules and oxygen molecules are broken and the bonds in new compounds are formed",
            "9-12",
        ),
        (
            "HS-LS2-1",
            "Use mathematical and/or computational representations to support explanations of factors that affect"
            "carrying capacity of ecosystems",
            "9-12",
        ),
        (
            "HS-PS1-1",
            "Use the periodic table as a model to predict the relative properties of elements based on the patterns of"
            "electrons in the outermost energy level",
            "9-12",
        ),
        (
            "HS-PS1-2",
            "Construct and revise an explanation for the outcome of a simple chemical reaction based on outermost"
            "electron states and the periodic table",
            "9-12",
        ),
        (
            "HS-PS2-1",
            "Analyze data to support the claim that Newton's second law of motion describes the mathematical"
            "relationship among the net force on a macroscopic object, its mass, and its acceleration",
            "9-12",
        ),
        (
            "HS-ESS1-1",
            "Develop a model based on evidence to illustrate the life span of the sun and the role of nuclear fusion"
            "in the sun's core",
            "9-12",
        ),
        (
            "HS-ESS2-1",
            "Develop a model to illustrate how Earth's internal and surface processes operate at different spatial and"
            "temporal scales to form continental and ocean-floor features",
            "9-12",
        ),
    ],
    "history": [
        # Middle School (6-8)
        (
            "D1.1.6-8",
            "Explain how a question represents key ideas in the field of civics, economics, geography, or history",
            "6-8",
        ),
        (
            "D1.2.6-8",
            "Explain points of agreement and disagreement experts have about interpretations of sources",
            "6-8",
        ),
        (
            "D2.Civ.1.6-8",
            "Distinguish the powers and responsibilities of citizens, political parties, interest groups, and the"
            "media in a variety of governmental and nongovernmental contexts",
            "6-8",
        ),
        (
            "D2.Civ.6.6-8",
            "Describe the roles of political, civil, and economic organizations in shaping people's lives",
            "6-8",
        ),
        (
            "D2.Eco.1.6-8",
            "Explain how economic decisions affect the well-being of individuals, businesses, and society",
            "6-8",
        ),
        (
            "D2.Geo.1.6-8",
            "Construct maps to represent and explain the spatial patterns of cultural"
            " and environmental characteristics",
            "6-8",
        ),
        ("D2.His.1.6-8", "Analyze connections among events and developments in broader historical contexts", "6-8"),
        (
            "D2.His.3.6-8",
            "Use questions generated about individuals and groups to analyze why they and the developments they shaped"
            "are seen as historically significant",
            "6-8",
        ),
        # High School (9-12)
        ("D1.1.9-12", "Explain how a question reflects an enduring issue in the field", "9-12"),
        (
            "D1.2.9-12",
            "Explain points of agreement and disagreement experts have about interpretations and applications of"
            "disciplinary concepts",
            "9-12",
        ),
        (
            "D2.Civ.1.9-12",
            "Distinguish the powers and responsibilities of local, state, tribal, national, and international civic"
            "and political institutions",
            "9-12",
        ),
        ("D2.Civ.6.9-12", "Critique relationships among governments, civil societies, and economic markets", "9-12"),
        (
            "D2.Eco.1.9-12",
            "Analyze how incentives influence choices that may result in policies with a range of costs and benefits"
            "for different groups",
            "9-12",
        ),
        (
            "D2.Geo.1.9-12",
            "Use geospatial and related technologies to create maps to display and explain the spatial patterns of"
            "cultural and environmental characteristics",
            "9-12",
        ),
        (
            "D2.His.1.9-12",
            "Evaluate how historical events and developments were shaped by unique circumstances of time and place as"
            "well as broader historical contexts",
            "9-12",
        ),
        (
            "D2.His.3.9-12",
            "Use questions generated about individuals and groups to assess how the significance of their actions"
            "changes over time",
            "9-12",
        ),
        (
            "D3.1.9-12",
            "Gather relevant information from multiple sources representing a wide range of views while checking the"
            "credibility of each source",
            "9-12",
        ),
        (
            "D4.1.9-12",
            "Construct arguments using precise and knowledgeable claims, with evidence from multiple sources, while"
            "acknowledging counterclaims and evidentiary weaknesses",
            "9-12",
        ),
    ],
}

# Subject name aliases — kept in sync with clawed.skills aliases
SUBJECT_ALIASES: dict[str, str] = {
    "math": "math",
    "mathematics": "math",
    "algebra": "math",
    "geometry": "math",
    "calculus": "math",
    "pre-algebra": "math",
    "pre-calculus": "math",
    "statistics": "math",
    "ela": "ela",
    "english": "ela",
    "language arts": "ela",
    "english language arts": "ela",
    "reading": "ela",
    "writing": "ela",
    "literacy": "ela",
    "science": "science",
    "biology": "science",
    "chemistry": "science",
    "physics": "science",
    "earth science": "science",
    "environmental science": "science",
    "life science": "science",
    "physical science": "science",
    "history": "history",
    "social studies": "history",
    "civics": "history",
    "economics": "history",
    "geography": "history",
    "us history": "history",
    "american history": "history",
    "world history": "history",
    "european history": "history",
    "ap history": "history",
    "ap us history": "history",
    "apush": "history",
    "government": "history",
    "ap government": "history",
    "ap bio": "science",
    "ap chem": "science",
    "ap world": "history",
    "ap euro": "history",
    "ap gov": "history",
    "ap lang": "ela",
    "ap lit": "ela",
    "ib history": "history",
}


def resolve_subject(subject: str) -> str | None:
    """Resolve a subject name to a canonical key in the STANDARDS dict."""
    return SUBJECT_ALIASES.get(subject.lower().strip())


def get_standards(
    subject: str,
    grade: str | None = None,
) -> list[tuple[str, str, str]]:
    """Return standards matching the subject and optional grade filter.

    Args:
        subject: Subject name (will be resolved via aliases).
        grade: Grade level filter (e.g., "8", "K", "9-12"). If None, returns all.

    Returns:
        List of (code, description, grade_band) tuples.
    """
    key = resolve_subject(subject)
    if key is None:
        return []

    all_standards = STANDARDS.get(key, [])
    if grade is None:
        return all_standards

    grade = grade.strip()
    results = []
    for code, desc, band in all_standards:
        if _grade_matches(grade, band):
            results.append((code, desc, band))
    return results


def _grade_matches(query_grade: str, band: str) -> bool:
    """Check if a queried grade falls within a standard's grade band."""
    query = query_grade.upper().strip()
    band_upper = band.upper().strip()

    # Exact match
    if query == band_upper:
        return True

    # K special case
    if query == "K" and band_upper == "K":
        return True

    # Range match: "6-8", "9-12", "11-12"
    if "-" in band_upper:
        parts = band_upper.split("-")
        try:
            low = int(parts[0])
            high = int(parts[1])
            grade_num = int(query)
            return low <= grade_num <= high
        except ValueError:
            return False

    # Numeric exact match
    try:
        return int(query) == int(band_upper)
    except ValueError:
        return False


# NY State K-12 Social Studies Framework (Framework for Jon)
NY_SOCIAL_STUDIES: dict[str, list[tuple[str, str, str]]] = {
    "social_studies": [
        # Grade 6 — The World in Ancient Times
        ("NYS-SS.6.1", "Early humans and the development of culture", "6"),
        ("NYS-SS.6.2", "River valley civilizations: Mesopotamia, Egypt, Indus Valley, China", "6"),
        ("NYS-SS.6.3", "Classical civilizations: Greece, Rome, China, India", "6"),
        ("NYS-SS.6.4", "The role of geography in the development of civilizations", "6"),

        # Grade 7 — Geography of the Western Hemisphere
        ("NYS-SS.7.1", "Physical geography of the Western Hemisphere", "7"),
        ("NYS-SS.7.2", "Human geography: settlement patterns, movement of people", "7"),
        ("NYS-SS.7.3", "Pre-Columbian civilizations: Maya, Aztec, Inca", "7"),
        ("NYS-SS.7.4", "European exploration and colonization of the Americas", "7"),
        ("NYS-SS.7.5", "Forced migration: the transatlantic slave trade", "7"),
        ("NYS-SS.7.6", "Colonial economies and their impact", "7"),
        ("NYS-SS.7.7", "Causes and effects of the American Revolution", "7"),

        # Grade 8 — United States and New York State History
        ("NYS-SS.8.1", "Constitutional foundations of American democracy", "8"),
        ("NYS-SS.8.2", "Expansion and reform in the early 19th century", "8"),
        ("NYS-SS.8.3", "Causes and consequences of the Civil War", "8"),
        ("NYS-SS.8.4", "Reconstruction and its aftermath", "8"),
        ("NYS-SS.8.5", "Industrialization and immigration: 1870-1920", "8"),
        ("NYS-SS.8.6", "Progressive Era reforms", "8"),
        ("NYS-SS.8.7", "American imperialism and World War I", "8"),
        ("NYS-SS.8.8", "The Roaring Twenties and the Great Depression", "8"),

        # Grade 9-10 — Global History and Geography I
        ("NYS-SS.9.1", "The World in 1750: Regions, trade, and power", "9"),
        ("NYS-SS.9.2", "The Age of Revolution: Enlightenment, French Revolution, Haitian Revolution", "9"),
        ("NYS-SS.9.3", "Industrial Revolution and its global impact", "9"),
        ("NYS-SS.9.4", "Imperialism and colonialism: causes and global impact", "9"),
        ("NYS-SS.9.5", "World War I: causes, events, and consequences", "9"),
        ("NYS-SS.10.1", "The Great Depression and the rise of totalitarianism", "10"),
        ("NYS-SS.10.2", "World War II: causes, events, Holocaust, Pacific theater", "10"),
        ("NYS-SS.10.3", "The Cold War: ideology, proxy wars, decolonization", "10"),
        ("NYS-SS.10.4", "Decolonization and independence movements in Africa and Asia", "10"),
        ("NYS-SS.10.5", "Contemporary global issues: human rights, terrorism, globalization", "10"),

        # Grade 11 — United States History and Government
        ("NYS-SS.11.1", "Progressive Era through World War I", "11"),
        ("NYS-SS.11.2", "The Interwar period and World War II on the homefront", "11"),
        ("NYS-SS.11.3", "Post-WWII America: Truman, Cold War, Korean War", "11"),
        ("NYS-SS.11.4", "The Civil Rights Movement", "11"),
        ("NYS-SS.11.5", "Vietnam War era and social movements", "11"),
        ("NYS-SS.11.6", "Conservative resurgence: Reagan Revolution", "11"),
        ("NYS-SS.11.7", "Post-Cold War America and the 21st century", "11"),

        # Grade 12 — Participation in Government / Economics
        ("NYS-SS.12.1", "The Constitution: structure and function of government", "12"),
        ("NYS-SS.12.2", "The political process: elections, voting, political parties", "12"),
        ("NYS-SS.12.3", "Civil liberties and civil rights", "12"),
        ("NYS-SS.12.4", "Economic systems and decision making", "12"),
        ("NYS-SS.12.5", "Personal finance and economic literacy", "12"),
    ]
}

# Add to main STANDARDS dict
STANDARDS["social_studies"] = NY_SOCIAL_STUDIES["social_studies"]


def get_ny_ss_standards(grade: str) -> list[dict]:
    """Get NY State Social Studies standards for a specific grade."""
    return [
        {"code": s[0], "description": s[1], "grade_band": s[2]}
        for s in NY_SOCIAL_STUDIES["social_studies"]
        if s[2] == grade or s[2].startswith(grade)
    ]


def get_standards_for_lesson(
    subject: str,
    grade: str,
    state: str = "",
    topic: str = "",
) -> list[str]:
    """Return formatted standard codes and descriptions for a lesson.

    For CCSS states: returns matching standards from the built-in database.
    For non-CCSS states: returns a framework alignment note with the
    actual framework name from state_standards.py.

    Args:
        subject: Subject name (e.g. "Math", "Science", "ELA").
        grade: Grade level (e.g. "8", "K", "9-12").
        state: Two-letter US state abbreviation (e.g. "NY", "TX").
        topic: Lesson topic for context (currently unused but reserved
               for future keyword-based filtering).

    Returns:
        List of formatted strings like "CCSS.MATH.8.EE.1: Know and apply..."
        or framework alignment notes for non-CCSS states.
    """
    from clawed.state_standards import (
        STATE_STANDARDS_CONFIG,
        get_framework_description,
        get_state_framework,
    )

    results: list[str] = []

    # Normalize subject for the state config lookup
    subject_key = subject.lower().strip().replace(" ", "_")
    # Map common names to state_standards keys
    _subject_map = {
        "math": "math", "mathematics": "math",
        "ela": "ela", "english": "ela", "language_arts": "ela",
        "reading": "ela", "writing": "ela",
        "science": "science", "biology": "science",
        "chemistry": "science", "physics": "science",
        "history": "social_studies", "social_studies": "social_studies",
        "civics": "social_studies", "economics": "social_studies",
        "geography": "social_studies",
    }
    config_subject = _subject_map.get(subject_key, subject_key)

    # Determine framework
    framework = ""
    if state:
        framework = get_state_framework(state, config_subject)

    # Check if this is a CCSS/NGSS/C3 framework where we have actual standards
    ccss_frameworks = {
        "CCSS", "NGSS", "C3",
        # CCSS-aligned state variants still use CCSS standards
        "CCSS_AZ", "CCSS_CA", "CCSS_LA", "CCSS_MS", "CCSS_NC",
        "CCSS_NJ", "CCSS_NM", "CCSS_UT", "MA_CCSS", "PA_CCSS",
        "KY_ACAS", "SC_CCRS", "WV_CSO",
    }

    is_ccss_like = framework in ccss_frameworks or not framework

    if is_ccss_like:
        # Look up actual standards from our database
        matches = get_standards(subject, grade)
        for code, desc, _band in matches:
            results.append(f"{code}: {desc}")

    if not results and framework and framework not in ccss_frameworks:
        # Non-CCSS state — provide framework alignment note
        desc = get_framework_description(framework)
        state_cfg = STATE_STANDARDS_CONFIG.get(state.upper(), {})
        state_name = state_cfg.get("name", state)
        results.append(
            f"Align to {state_name} {desc} ({framework}): "
            f"{subject.title()} Grade {grade}"
        )

    if not results:
        results.append(
            f"Use appropriate grade-level standards for {subject.title()} Grade {grade}"
        )

    return results


def format_standards_for_prompt(standards: list[str]) -> str:
    """Format a list of standards into a prompt-friendly block.

    Returns a string suitable for injection into LLM prompts,
    including a 'Standards Addressed' header.
    """
    if not standards:
        return "Standards: Use appropriate grade-level standards."
    lines = ["Standards Addressed:"]
    for s in standards:
        lines.append(f"  - {s}")
    return "\n".join(lines)
