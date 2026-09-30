"""Subject vocabularies and sentence frames for the synthetic document generator.

Everything here is hand-written. The generator (``dataset.py``) combines these
into complete educational documents; see docs/ml-pipeline.md for why this
exists and its limitations.
"""

from __future__ import annotations

# Each subject: terms with a definitional phrase, processes, formulas, people/works.
SUBJECTS: dict[str, dict] = {
    "biology": {
        "titles": ["Cell Biology Fundamentals", "Introduction to Genetics", "Human Physiology Notes", "Ecology and Ecosystems"],
        "topics": ["Cell Structure", "Photosynthesis", "Cellular Respiration", "DNA Replication", "Protein Synthesis", "Mitosis", "Meiosis", "Enzymes", "Natural Selection", "Food Webs"],
        "terms": [
            ("the mitochondrion", "an organelle that produces most of the cell's supply of ATP"),
            ("an enzyme", "a protein that speeds up a chemical reaction without being consumed"),
            ("osmosis", "the movement of water across a semi-permeable membrane"),
            ("a gene", "a sequence of DNA that codes for a functional product"),
            ("homeostasis", "the maintenance of a stable internal environment"),
            ("an allele", "one of several alternative forms of the same gene"),
            ("a producer", "an organism that makes its own food from light or chemical energy"),
            ("transcription", "the process of copying a DNA sequence into messenger RNA"),
        ],
        "processes": ["regulates the flow of nutrients", "controls cell division", "releases energy from glucose", "stores genetic information", "maintains membrane potential", "transports oxygen through the blood"],
        "formulas": ["6CO2 + 6H2O → C6H12O6 + 6O2", "C6H12O6 + 6O2 → 6CO2 + 6H2O + ATP", "p² + 2pq + q² = 1", "N(t) = N0 · e^(rt)"],
        "people": [("Darwin, C.", "On the Origin of Species", "John Murray", 1859), ("Watson, J. D. & Crick, F. H. C.", "Molecular structure of nucleic acids", "Nature", 1953), ("Alberts, B.", "Molecular Biology of the Cell", "Garland Science", 2014)],
    },
    "physics": {
        "titles": ["Classical Mechanics", "Electricity and Magnetism", "Waves and Optics", "Thermodynamics Revision"],
        "topics": ["Newton's Laws", "Kinematics", "Work and Energy", "Momentum", "Circular Motion", "Electric Fields", "Ohm's Law", "Wave Properties", "Refraction", "Heat Transfer"],
        "terms": [
            ("velocity", "the rate of change of displacement with respect to time"),
            ("momentum", "the product of an object's mass and its velocity"),
            ("a force", "an interaction that changes the motion of an object"),
            ("resistance", "the opposition a conductor offers to electric current"),
            ("entropy", "a measure of the disorder of a system"),
            ("frequency", "the number of oscillations completed per second"),
            ("work", "the energy transferred when a force moves an object through a distance"),
            ("inertia", "the tendency of an object to resist changes in its motion"),
        ],
        "processes": ["conserves total energy", "accelerates the object uniformly", "transfers heat by convection", "reflects light at the boundary", "converts potential energy into kinetic energy", "produces a magnetic field around the wire"],
        "formulas": ["F = m · a", "v = u + a·t", "E_k = ½ m v²", "V = I · R", "p = m · v", "λ = v / f", "ΔU = Q − W"],
        "people": [("Newton, I.", "Philosophiæ Naturalis Principia Mathematica", "Royal Society", 1687), ("Feynman, R. P.", "The Feynman Lectures on Physics", "Addison-Wesley", 1964), ("Halliday, D., Resnick, R. & Walker, J.", "Fundamentals of Physics", "Wiley", 2013)],
    },
    "chemistry": {
        "titles": ["General Chemistry Notes", "Organic Chemistry Basics", "Chemical Bonding", "Acids and Bases"],
        "topics": ["Atomic Structure", "The Periodic Table", "Ionic Bonding", "Covalent Bonding", "Reaction Rates", "Chemical Equilibrium", "Acids and Bases", "Redox Reactions", "Hydrocarbons", "Stoichiometry"],
        "terms": [
            ("an isotope", "an atom of the same element with a different number of neutrons"),
            ("a catalyst", "a substance that increases the rate of a reaction without being used up"),
            ("electronegativity", "the ability of an atom to attract a bonding pair of electrons"),
            ("a mole", "the amount of substance containing 6.022 × 10²³ particles"),
            ("an oxidising agent", "a species that accepts electrons in a redox reaction"),
            ("a buffer", "a solution that resists changes in pH"),
            ("activation energy", "the minimum energy required for a reaction to occur"),
            ("an ion", "an atom or molecule with a net electric charge"),
        ],
        "processes": ["shifts the equilibrium to the right", "increases the rate of reaction", "forms a covalent bond", "donates a proton", "releases heat to the surroundings", "neutralises the acid"],
        "formulas": ["pH = −log[H+]", "PV = nRT", "n = m / M", "K_c = [C][D] / [A][B]", "ΔG = ΔH − TΔS"],
        "people": [("Atkins, P. & de Paula, J.", "Physical Chemistry", "Oxford University Press", 2014), ("Pauling, L.", "The Nature of the Chemical Bond", "Cornell University Press", 1939), ("Clayden, J.", "Organic Chemistry", "Oxford University Press", 2012)],
    },
    "history": {
        "titles": ["The Industrial Revolution", "World War I: Causes and Consequences", "The Renaissance", "Ancient Rome"],
        "topics": ["Social Change", "Economic Growth", "Political Reform", "Key Figures", "Causes of the War", "Treaty Negotiations", "Cultural Developments", "Trade Networks", "Urbanisation", "Legacy"],
        "terms": [
            ("mercantilism", "an economic policy aimed at accumulating wealth through trade surpluses"),
            ("an armistice", "an agreement to stop fighting while peace terms are negotiated"),
            ("humanism", "an intellectual movement that emphasised classical learning and human potential"),
            ("urbanisation", "the growth in the proportion of people living in towns and cities"),
            ("a republic", "a state in which power is held by elected representatives"),
            ("nationalism", "strong identification with and loyalty to one's nation"),
            ("a guild", "an association of craftsmen or merchants that regulated a trade"),
            ("imperialism", "the policy of extending a nation's power through colonisation"),
        ],
        "processes": ["reshaped the balance of power in Europe", "transformed working conditions in factories", "encouraged the growth of towns", "led to new trade routes", "weakened the authority of the monarchy", "spread new ideas through printing"],
        "formulas": [],
        "people": [("Hobsbawm, E.", "The Age of Revolution", "Weidenfeld & Nicolson", 1962), ("Clark, C.", "The Sleepwalkers", "Allen Lane", 2012), ("Burckhardt, J.", "The Civilization of the Renaissance in Italy", "Penguin", 1860)],
    },
    "economics": {
        "titles": ["Principles of Microeconomics", "Macroeconomics Revision", "Market Structures", "International Trade"],
        "topics": ["Supply and Demand", "Elasticity", "Market Equilibrium", "Perfect Competition", "Monopoly", "Inflation", "Unemployment", "Fiscal Policy", "Monetary Policy", "Comparative Advantage"],
        "terms": [
            ("opportunity cost", "the value of the next best alternative that is given up"),
            ("inflation", "a sustained increase in the general price level"),
            ("elasticity", "the responsiveness of quantity demanded to a change in price"),
            ("a monopoly", "a market with a single seller and no close substitutes"),
            ("GDP", "the total value of final goods and services produced in a country"),
            ("a tariff", "a tax imposed on imported goods"),
            ("marginal utility", "the additional satisfaction gained from consuming one more unit"),
            ("fiscal policy", "the use of government spending and taxation to influence the economy"),
        ],
        "processes": ["raises the equilibrium price", "reduces consumer surplus", "shifts the demand curve outward", "lowers the rate of unemployment", "increases aggregate demand", "creates a deadweight loss"],
        "formulas": ["PED = %ΔQd / %ΔP", "GDP = C + I + G + (X − M)", "MV = PT", "Profit = TR − TC", "Real GDP = Nominal GDP / Deflator"],
        "people": [("Smith, A.", "The Wealth of Nations", "W. Strahan", 1776), ("Keynes, J. M.", "The General Theory of Employment, Interest and Money", "Macmillan", 1936), ("Mankiw, N. G.", "Principles of Economics", "Cengage", 2020)],
    },
    "computer_science": {
        "titles": ["Data Structures and Algorithms", "Operating Systems Notes", "Computer Networks", "Introduction to Databases"],
        "topics": ["Arrays and Lists", "Stacks and Queues", "Binary Trees", "Sorting Algorithms", "Hash Tables", "Process Scheduling", "Memory Management", "The TCP/IP Model", "Normalisation", "SQL Queries"],
        "terms": [
            ("a stack", "a last-in, first-out collection of elements"),
            ("a hash function", "a function that maps keys to positions in a table"),
            ("a process", "a program in execution with its own address space"),
            ("recursion", "a technique in which a function calls itself on smaller inputs"),
            ("a primary key", "an attribute that uniquely identifies each row in a table"),
            ("latency", "the delay between sending a request and receiving a response"),
            ("a deadlock", "a state in which processes wait forever for each other's resources"),
            ("big-O notation", "a way of describing the upper bound of an algorithm's growth rate"),
        ],
        "processes": ["reduces the average lookup time", "allocates memory to each process", "guarantees reliable delivery of packets", "sorts the input in place", "avoids redundant data", "balances the tree after insertion"],
        "formulas": ["T(n) = 2T(n/2) + O(n)", "load factor α = n / m", "Throughput = data / time", "O(n log n)", "h(k) = k mod m"],
        "people": [("Cormen, T. H. et al.", "Introduction to Algorithms", "MIT Press", 2009), ("Tanenbaum, A. S.", "Modern Operating Systems", "Pearson", 2014), ("Knuth, D. E.", "The Art of Computer Programming", "Addison-Wesley", 1968)],
    },
    "mathematics": {
        "titles": ["Calculus I Notes", "Linear Algebra Essentials", "Probability and Statistics", "Discrete Mathematics"],
        "topics": ["Limits", "Derivatives", "Integration", "Matrices", "Eigenvalues", "Probability Rules", "Random Variables", "Hypothesis Testing", "Set Theory", "Graph Theory"],
        "terms": [
            ("a derivative", "the instantaneous rate of change of a function"),
            ("a matrix", "a rectangular array of numbers arranged in rows and columns"),
            ("a random variable", "a function that assigns a number to each outcome of an experiment"),
            ("an eigenvector", "a non-zero vector whose direction is unchanged by a linear transformation"),
            ("a limit", "the value a function approaches as its input approaches a point"),
            ("the variance", "the average squared deviation from the mean"),
            ("a graph", "a set of vertices connected by edges"),
            ("a set", "a well-defined collection of distinct objects"),
        ],
        "processes": ["approaches zero as x grows", "preserves vector addition", "measures the spread of the data", "gives the area under the curve", "is invariant under rotation", "counts the number of paths"],
        "formulas": ["d/dx (xⁿ) = n·xⁿ⁻¹", "∫ x dx = x²/2 + C", "P(A ∪ B) = P(A) + P(B) − P(A ∩ B)", "Var(X) = E[X²] − (E[X])²", "det(A − λI) = 0", "a² + b² = c²"],
        "people": [("Stewart, J.", "Calculus: Early Transcendentals", "Cengage", 2015), ("Strang, G.", "Introduction to Linear Algebra", "Wellesley-Cambridge Press", 2016), ("Ross, S.", "A First Course in Probability", "Pearson", 2014)],
    },
    "geography": {
        "titles": ["Physical Geography", "Climate and Weather", "Rivers and Coasts", "Population and Settlement"],
        "topics": ["Plate Tectonics", "The Water Cycle", "Weather Systems", "Climate Zones", "River Processes", "Coastal Erosion", "Population Growth", "Migration", "Urban Land Use", "Natural Hazards"],
        "terms": [
            ("erosion", "the wearing away of land by water, wind or ice"),
            ("a watershed", "the boundary between two drainage basins"),
            ("climate", "the long-term average weather conditions of a region"),
            ("a tectonic plate", "a large slab of the Earth's lithosphere"),
            ("migration", "the movement of people from one place to another"),
            ("precipitation", "water released from clouds as rain, snow or hail"),
            ("a delta", "a landform created by sediment deposited at a river mouth"),
            ("population density", "the number of people living per square kilometre"),
        ],
        "processes": ["shapes the landscape over time", "causes earthquakes along the boundary", "deposits sediment on the floodplain", "drives the global circulation of air", "increases the risk of flooding", "attracts people to urban areas"],
        "formulas": ["Population density = population / area", "Natural increase = birth rate − death rate", "Discharge = cross-sectional area × velocity"],
        "people": [("Holden, J.", "An Introduction to Physical Geography and the Environment", "Pearson", 2017), ("Knox, P. & Marston, S.", "Human Geography", "Pearson", 2016), ("Strahler, A.", "Physical Geography", "Wiley", 2013)],
    },
    "psychology": {
        "titles": ["Introduction to Psychology", "Cognitive Psychology", "Developmental Psychology", "Research Methods in Psychology"],
        "topics": ["Memory", "Attention", "Learning Theories", "Child Development", "Social Influence", "Motivation", "Perception", "Experimental Design", "Personality", "Stress"],
        "terms": [
            ("working memory", "a limited-capacity system for temporarily holding information"),
            ("classical conditioning", "learning in which a neutral stimulus becomes associated with a response"),
            ("conformity", "changing one's behaviour to match that of a group"),
            ("a hypothesis", "a testable prediction about the relationship between variables"),
            ("attachment", "a deep emotional bond between a child and a caregiver"),
            ("perception", "the process of organising and interpreting sensory information"),
            ("an independent variable", "the variable that the researcher manipulates"),
            ("cognitive dissonance", "the discomfort felt when holding conflicting beliefs"),
        ],
        "processes": ["improves recall of the material", "reduces the effect of stress", "shapes behaviour through reinforcement", "influences how people make decisions", "develops during early childhood", "biases the interpretation of results"],
        "formulas": ["Reliability = true variance / observed variance", "z = (x − μ) / σ", "d = (M1 − M2) / SD"],
        "people": [("Baddeley, A. D. & Hitch, G.", "Working memory", "Academic Press", 1974), ("Piaget, J.", "The Origins of Intelligence in Children", "International Universities Press", 1952), ("Asch, S. E.", "Opinions and social pressure", "Scientific American", 1955)],
    },
    "literature": {
        "titles": ["Studying Poetry", "The Victorian Novel", "Shakespearean Tragedy", "Modernist Literature"],
        "topics": ["Themes", "Characterisation", "Narrative Voice", "Imagery", "Structure and Form", "Historical Context", "Symbolism", "Tragic Heroes", "Language and Tone", "Critical Perspectives"],
        "terms": [
            ("a metaphor", "a figure of speech that describes something as if it were something else"),
            ("irony", "a contrast between what is expected and what actually happens"),
            ("a soliloquy", "a speech in which a character speaks their thoughts aloud alone on stage"),
            ("a motif", "a recurring element that has symbolic significance"),
            ("an unreliable narrator", "a narrator whose credibility is compromised"),
            ("iambic pentameter", "a line of verse with five iambic feet"),
            ("pathos", "a quality that evokes pity or sadness"),
            ("free indirect discourse", "third-person narration that takes on a character's voice"),
        ],
        "processes": ["creates a sense of foreboding", "reveals the character's inner conflict", "reflects the anxieties of the period", "challenges the reader's expectations", "reinforces the central theme", "builds tension towards the climax"],
        "formulas": [],
        "people": [("Bradley, A. C.", "Shakespearean Tragedy", "Macmillan", 1904), ("Eagleton, T.", "Literary Theory: An Introduction", "Blackwell", 1983), ("Woolf, V.", "A Room of One's Own", "Hogarth Press", 1929)],
    },
    "environmental_science": {
        "titles": ["Environmental Science Basics", "Climate Change", "Sustainable Energy", "Pollution and Health"],
        "topics": ["The Greenhouse Effect", "Carbon Cycle", "Renewable Energy", "Air Pollution", "Water Quality", "Biodiversity Loss", "Waste Management", "Sustainable Development", "Deforestation", "Ocean Acidification"],
        "terms": [
            ("the greenhouse effect", "the warming of the Earth's surface by gases that trap heat"),
            ("biodiversity", "the variety of life in a particular habitat or ecosystem"),
            ("a carbon sink", "a reservoir that absorbs more carbon than it releases"),
            ("renewable energy", "energy from sources that are naturally replenished"),
            ("eutrophication", "excessive nutrient enrichment of water that causes algal blooms"),
            ("a pollutant", "a substance that harms the environment when released"),
            ("sustainability", "meeting present needs without compromising future generations"),
            ("a carbon footprint", "the total greenhouse gas emissions caused by an activity"),
        ],
        "processes": ["reduces greenhouse gas emissions", "absorbs carbon dioxide from the air", "lowers the pH of sea water", "threatens many species with extinction", "improves the efficiency of energy use", "contaminates local water supplies"],
        "formulas": ["CO2 + H2O ⇌ H2CO3", "Efficiency = useful output / total input × 100%", "Emissions = activity × emission factor"],
        "people": [("Carson, R.", "Silent Spring", "Houghton Mifflin", 1962), ("IPCC", "Climate Change 2021: The Physical Science Basis", "Cambridge University Press", 2021), ("Miller, G. T.", "Living in the Environment", "Cengage", 2018)],
    },
    "business": {
        "titles": ["Principles of Management", "Marketing Fundamentals", "Introduction to Accounting", "Organisational Behaviour"],
        "topics": ["The Marketing Mix", "Market Research", "Leadership Styles", "Motivation Theories", "Financial Statements", "Break-even Analysis", "Cash Flow", "Business Strategy", "Organisational Structure", "Human Resources"],
        "terms": [
            ("a stakeholder", "any individual or group with an interest in a business"),
            ("market segmentation", "dividing a market into groups of similar consumers"),
            ("working capital", "current assets minus current liabilities"),
            ("a brand", "a name, design or symbol that identifies a product"),
            ("delegation", "passing authority down the organisational hierarchy"),
            ("depreciation", "the fall in value of a fixed asset over time"),
            ("a SWOT analysis", "an assessment of strengths, weaknesses, opportunities and threats"),
            ("liquidity", "the ability of a business to meet its short-term debts"),
        ],
        "processes": ["increases customer loyalty", "improves employee motivation", "reduces the cost per unit", "helps managers plan ahead", "attracts new investors", "widens the profit margin"],
        "formulas": ["Break-even = fixed costs / (price − variable cost)", "Profit margin = net profit / revenue × 100", "ROCE = operating profit / capital employed", "Current ratio = current assets / current liabilities"],
        "people": [("Drucker, P. F.", "The Practice of Management", "Harper & Row", 1954), ("Kotler, P.", "Marketing Management", "Pearson", 2016), ("Porter, M. E.", "Competitive Strategy", "Free Press", 1980)],
    },
}

PARAGRAPH_FRAMES = [
    "{Term} {process}, which is why it is studied closely in {subject}.",
    "Researchers have shown that {term} {process} in many different situations.",
    "In most cases {term} {process}, although the effect depends on the conditions.",
    "Understanding {term} helps us explain how the system {process}.",
    "Historically, {term} was poorly understood, but modern work shows that it {process}.",
    "When conditions change, {term} often {process} more quickly than expected.",
    "This section looks at how {term} {process} and why this matters.",
    "A common misconception is that {term} always {process}; in reality it varies.",
    "The relationship between {term} and {term2} is central to this topic.",
    "Both {term} and {term2} play a role, but they work in different ways.",
    "Scientists and scholars continue to debate how {term} {process}.",
    "It is useful to compare {term} with {term2} when revising this chapter.",
    "The evidence suggests that {term} {process} over a long period of time.",
    "Many textbooks describe {term} first because the rest of the topic builds on it.",
    "In practice, {term} {process} only when several conditions are met.",
    "Students should be able to describe how {term} {process} and give reasons.",
]

DEFINITION_FRAMES = [
    "Definition: {Term} is {definition}.",
    "{Term} is defined as {definition}.",
    "{Term} refers to {definition}.",
    "Key term – {term_bare}: {definition}.",
    "{Term_bare} means {definition}.",
    "We use the word {term_bare} to mean {definition}.",
    "{Term_bare} (definition): {definition}.",
]

EXAMPLE_FRAMES = [
    "Example: {example_text}",
    "For example, {example_text_lc}",
    "For instance, {example_text_lc}",
    "e.g. {example_text_lc}",
    "Worked example: {example_text}",
    "Consider the following case: {example_text_lc}",
    "Illustration: {example_text}",
]

EXAMPLE_BODIES = [
    "In a typical classroom experiment, {term} {process}, which can be observed directly.",
    "A well-known case study shows how {term} {process} in a real setting.",
    "If we measure {term} before and after the change, we see that it {process}.",
    "Suppose a student investigates {term}; they will find that it {process}.",
]

PROCEDURE_FRAMES = [
    "Step 1: {a}. Step 2: {b}. Step 3: {c}.",
    "First, {a_lc}. Then, {b_lc}. Finally, {c_lc}.",
    "Procedure: {a}; {b_lc}; {c_lc}.",
    "Method: {a}, then {b_lc}, and finally {c_lc}.",
    "1) {a}  2) {b}  3) {c}",
    "To carry out the investigation, first {a_lc}, next {b_lc}, and then {c_lc}.",
]

PROCEDURE_STEPS = [
    "Identify the key variables",
    "Collect the relevant data",
    "Record the measurements in a table",
    "Plot the results on a graph",
    "Calculate the mean value",
    "Compare the results with the prediction",
    "Repeat the experiment three times",
    "Write down the known quantities",
    "Substitute the values into the equation",
    "State the conclusion clearly",
    "Label the diagram carefully",
    "Check the units of the final answer",
]

IMPORTANT_FRAMES = [
    "Important: {Term} does not always {process_base}.",
    "Note: remember that {term} {process} only under certain conditions.",
    "Remember: {term} and {term2} are not the same thing.",
    "Key point: {term} {process}.",
    "Exam tip: always define {term_bare} before using it in an answer.",
    "Caution: do not confuse {term_bare} with {term2_bare}.",
    "NB: {Term} is one of the most frequently examined ideas in {subject}.",
]

QUESTION_FRAMES = [
    "Q{n}. What is {term_bare}?",
    "Q{n}: Explain how {term} {process}.",
    "Question {n}: Why is {term_bare} important in {subject}?",
    "{n}. Describe the role of {term_bare}.",
    "Explain the difference between {term_bare} and {term2_bare}.",
    "Discuss the importance of {term_bare}.",
    "How does {term} affect {term2_bare}?",
    "Compare {term_bare} with {term2_bare}.",
    "Define {term_bare} and give an example.",
    "Why does {term} {process_base}?",
]

ANSWER_FRAMES = [
    "Answer: {Term} is {definition}.",
    "Ans: {Term} {process}, because of the conditions described above.",
    "Solution: Start from the definition — {term} is {definition}.",
    "A{n}. {Term} is {definition}.",
    "Answer: The main difference is that {term} {process}, whereas {term2} does not.",
    "Model answer: {Term} matters because it {process}.",
]

CONCLUSION_FRAMES = [
    "In conclusion, {term} {process}, and this idea connects the whole chapter.",
    "To summarise, we have seen that {term} and {term2} are closely linked.",
    "Overall, {term} is essential for understanding {subject}.",
    "In summary, this chapter explained how {term} {process}.",
    "To conclude, the study of {term_bare} shows why {subject} matters.",
    "Therefore, a clear understanding of {term_bare} is the foundation for the next chapter.",
]

HEADING_EXTRAS = ["Introduction", "Overview", "Background", "Key Concepts", "Summary", "Applications", "Case Study", "Further Reading"]
QUESTION_SECTION_TITLES = ["Review Questions", "Practice Questions", "Self-Test", "Exercises", "Check Your Understanding"]
CONCLUSION_SECTION_TITLES = ["Conclusion", "Summary", "Chapter Summary", "Final Thoughts"]
REFERENCE_SECTION_TITLES = ["References", "Bibliography", "Further Reading", "Sources"]
