"""Sample educational content used to build test fixtures (PDF/DOCX/TXT).

Each entry is (label, text). Labels are the classifier classes, which lets the
fixtures double as a sanity check for the extraction → classification path.
"""

ML_CHAPTER: list[tuple[str, str]] = [
    ("TITLE", "Introduction to Machine Learning"),
    ("HEADING", "1. What is Machine Learning?"),
    (
        "PARAGRAPH",
        "Machine learning is a branch of artificial intelligence that allows computers to "
        "learn patterns from data instead of being explicitly programmed. A model is trained "
        "on examples and then used to make predictions on new, unseen inputs.",
    ),
    (
        "DEFINITION",
        "Definition: A training set is the collection of labelled examples that a learning "
        "algorithm uses to fit the parameters of a model.",
    ),
    (
        "PARAGRAPH",
        "The quality of a model depends heavily on the quality and quantity of its training "
        "data. Noisy labels, missing values and biased samples all reduce accuracy.",
    ),
    ("HEADING", "2. Types of Machine Learning"),
    ("SUBHEADING", "2.1 Supervised Learning"),
    (
        "PARAGRAPH",
        "In supervised learning every training example has a known target label. Common "
        "tasks are classification, where the target is a category, and regression, where the "
        "target is a number.",
    ),
    (
        "EXAMPLE",
        "Example: Predicting whether an email is spam from its words is a supervised "
        "classification problem.",
    ),
    ("SUBHEADING", "2.2 Unsupervised Learning"),
    (
        "PARAGRAPH",
        "Unsupervised learning finds structure in unlabelled data. Clustering groups similar "
        "points together and dimensionality reduction compresses features while keeping most "
        "of the information.",
    ),
    ("SUBHEADING", "2.3 Reinforcement Learning"),
    (
        "PARAGRAPH",
        "In reinforcement learning an agent interacts with an environment and learns a policy "
        "that maximises cumulative reward through trial and error.",
    ),
    ("HEADING", "3. Training a Model"),
    (
        "PROCEDURE",
        "Step 1: Collect and clean the data. Step 2: Split it into training and test sets. "
        "Step 3: Fit the model on the training set. Step 4: Evaluate it on the test set.",
    ),
    ("FORMULA", "MSE = (1/n) * Σ (y_i − ŷ_i)²"),
    (
        "IMPORTANT_POINT",
        "Important: Never evaluate a model on the same data that was used to train it.",
    ),
    ("HEADING", "4. Review Questions"),
    ("QUESTION", "Q1. What is the difference between classification and regression?"),
    (
        "ANSWER",
        "Answer: Classification predicts a discrete category, while regression predicts a "
        "continuous numerical value.",
    ),
    ("QUESTION", "Q2. Why do we need a separate test set?"),
    ("HEADING", "5. Conclusion"),
    (
        "CONCLUSION",
        "In conclusion, machine learning turns data into predictive models, and careful "
        "evaluation is what makes those models trustworthy.",
    ),
    ("HEADING", "References"),
    (
        "REFERENCE",
        "[1] Mitchell, T. (1997). Machine Learning. McGraw-Hill.",
    ),
    (
        "REFERENCE",
        "[2] Bishop, C. M. (2006). Pattern Recognition and Machine Learning. Springer.",
    ),
]
