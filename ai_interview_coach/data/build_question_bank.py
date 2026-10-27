"""
build_question_bank.py
-------------------------
Builds the interview question bank for the AI Interview Coach.

Each entry has:
- category: which interview track this belongs to
- question: the interview question
- model_answer: a strong reference answer used for semantic similarity scoring
- key_points: important concepts/keywords a good answer should hit
  (used for the keyword-coverage feedback layer)

Categories:
- HR / Behavioral
- Computer Science Fundamentals (CS core, common in MCA placements)
- Python Programming
- Machine Learning Basics
- System Design (entry-level)

Run: python build_question_bank.py
Produces: question_bank.csv
"""

import csv
from collections import defaultdict
from pathlib import Path

bank = [
    # ---------------- HR / BEHAVIORAL ----------------
    {
        "category": "HR / Behavioral",
        "question": "Tell me about yourself.",
        "model_answer": "I am a computer applications student with a strong foundation in programming and problem solving. I have worked on academic and personal projects involving web development and machine learning, and I enjoy learning new technologies. I am looking for a role where I can apply my technical skills, contribute to a team, and continue growing as a developer.",
        "key_points": "background, skills, projects, career goal, relevance to role",
    },
    {
        "category": "HR / Behavioral",
        "question": "What are your strengths and weaknesses?",
        "model_answer": "One of my key strengths is my ability to break down complex problems into manageable steps, which helps me debug and learn new concepts quickly. A weakness I have been working on is that I used to spend too much time perfecting small details, so I have been practicing setting clearer time limits for tasks to balance quality with efficiency.",
        "key_points": "specific strength, specific weakness, self-awareness, improvement effort",
    },
    {
        "category": "HR / Behavioral",
        "question": "Why should we hire you?",
        "model_answer": "I bring a solid technical foundation combined with hands-on project experience, and I am genuinely eager to learn and adapt quickly to new tools and processes. I also work well in teams and communicate clearly, which helps in collaborative environments. I believe my combination of technical skill and willingness to learn makes me a good fit for this role.",
        "key_points": "technical skill, adaptability, teamwork, genuine motivation, fit for role",
    },
    {
        "category": "HR / Behavioral",
        "question": "Describe a challenging situation you faced and how you handled it.",
        "model_answer": "During a group project, we faced a tight deadline and a teammate who was unavailable due to a personal issue. I reorganized the remaining tasks among the team, took on an extra module myself, and communicated clearly with our mentor about the adjusted timeline. We managed to submit the project successfully and on time.",
        "key_points": "specific situation, action taken, teamwork, outcome, communication",
    },
    {
        "category": "HR / Behavioral",
        "question": "Where do you see yourself in five years?",
        "model_answer": "In five years, I see myself having grown into a more senior technical role, having built strong expertise in software development or a specialized area like machine learning, and having contributed to impactful projects. I also hope to mentor junior team members by then.",
        "key_points": "growth, specialization, contribution, realistic ambition, mentorship",
    },

    # ---------------- CS FUNDAMENTALS ----------------
    {
        "category": "CS Fundamentals",
        "question": "What is the difference between a stack and a queue?",
        "model_answer": "A stack follows Last-In-First-Out order, meaning the most recently added element is removed first, like a pile of plates. A queue follows First-In-First-Out order, meaning the first element added is the first one removed, like a line of people waiting.",
        "key_points": "LIFO, FIFO, insertion, removal order, real-world analogy",
    },
    {
        "category": "CS Fundamentals",
        "question": "Explain normalization in databases.",
        "model_answer": "Normalization is the process of organizing database tables to reduce data redundancy and improve data integrity. It involves splitting large tables into smaller related tables and defining relationships between them using foreign keys, typically following normal forms like 1NF, 2NF, and 3NF.",
        "key_points": "redundancy, data integrity, normal forms, foreign keys, table decomposition",
    },
    {
        "category": "CS Fundamentals",
        "question": "What is the difference between process and thread?",
        "model_answer": "A process is an independent program in execution with its own memory space, while a thread is a smaller unit of execution within a process that shares the same memory space with other threads of that process. Threads are lighter weight and allow for concurrent execution within a single process.",
        "key_points": "independent memory, shared memory, lightweight, concurrency, execution unit",
    },
    {
        "category": "CS Fundamentals",
        "question": "What is the time complexity of binary search and why?",
        "model_answer": "Binary search has a time complexity of O(log n) because it repeatedly divides the search space in half at each step, rather than scanning every element linearly. This requires the array to be sorted beforehand.",
        "key_points": "O(log n), divide search space, sorted array requirement",
    },
    {
        "category": "CS Fundamentals",
        "question": "What is deadlock in operating systems and how can it be prevented?",
        "model_answer": "Deadlock occurs when a set of processes are blocked because each process is holding a resource and waiting for another resource held by another process, forming a circular wait. It can be prevented by breaking one of the four necessary conditions, such as avoiding circular wait through resource ordering, or using techniques like the Banker's algorithm.",
        "key_points": "circular wait, resource holding, four conditions, prevention techniques, Banker's algorithm",
    },

    # ---------------- PYTHON PROGRAMMING ----------------
    {
        "category": "Python Programming",
        "question": "What is the difference between a list and a tuple in Python?",
        "model_answer": "A list is mutable, meaning its elements can be changed after creation, while a tuple is immutable, meaning it cannot be modified once created. Lists are generally used for collections that may change, while tuples are used for fixed collections of items, and tuples are slightly faster due to immutability.",
        "key_points": "mutable, immutable, use cases, performance difference",
    },
    {
        "category": "Python Programming",
        "question": "What are Python decorators?",
        "model_answer": "A decorator is a function that takes another function as input and extends or modifies its behavior without changing its actual code. Decorators are commonly used for logging, access control, and timing functions, and are applied using the @ symbol above a function definition.",
        "key_points": "function wrapping, modifies behavior, @ syntax, common use cases",
    },
    {
        "category": "Python Programming",
        "question": "What is the difference between deep copy and shallow copy?",
        "model_answer": "A shallow copy creates a new object but inserts references to the same nested objects found in the original, so changes to nested objects affect both copies. A deep copy creates a completely independent copy, including all nested objects, so changes to one do not affect the other.",
        "key_points": "shallow copy references, deep copy independent, nested objects, mutability impact",
    },
    {
        "category": "Python Programming",
        "question": "What are Python generators and why are they useful?",
        "model_answer": "Generators are functions that use the yield keyword to return values one at a time, pausing their state between calls instead of computing and storing an entire sequence in memory. This makes them memory-efficient for working with large datasets or infinite sequences.",
        "key_points": "yield keyword, lazy evaluation, memory efficiency, large datasets",
    },
    {
        "category": "Python Programming",
        "question": "Explain Python's Global Interpreter Lock (GIL).",
        "model_answer": "The GIL is a mutex that allows only one thread to execute Python bytecode at a time in a single process, even on multi-core systems. This means CPU-bound multithreaded programs don't get true parallelism in standard Python, though I/O-bound tasks can still benefit from threading, and true parallelism can be achieved using multiprocessing instead.",
        "key_points": "mutex, one thread at a time, CPU-bound limitation, multiprocessing alternative",
    },

    # ---------------- MACHINE LEARNING BASICS ----------------
    {
        "category": "Machine Learning Basics",
        "question": "What is overfitting and how can you prevent it?",
        "model_answer": "Overfitting occurs when a model learns the training data too well, including its noise, resulting in poor performance on new, unseen data. It can be prevented using techniques like cross-validation, regularization, pruning, dropout in neural networks, or simply gathering more training data.",
        "key_points": "learns noise, poor generalization, regularization, cross-validation, dropout",
    },
    {
        "category": "Machine Learning Basics",
        "question": "What is the difference between supervised and unsupervised learning?",
        "model_answer": "Supervised learning uses labeled data, where the model learns to map inputs to known outputs, such as in classification or regression tasks. Unsupervised learning works with unlabeled data and tries to find hidden patterns or structure, such as in clustering or dimensionality reduction.",
        "key_points": "labeled data, unlabeled data, classification/regression, clustering",
    },
    {
        "category": "Machine Learning Basics",
        "question": "Explain the bias-variance tradeoff.",
        "model_answer": "Bias refers to error from overly simplistic assumptions in a model, causing underfitting, while variance refers to error from a model being too sensitive to small fluctuations in training data, causing overfitting. The tradeoff involves finding a balance where the model is complex enough to capture patterns but not so complex that it overfits.",
        "key_points": "bias, variance, underfitting, overfitting, balance",
    },
    {
        "category": "Machine Learning Basics",
        "question": "What is a confusion matrix and why is it useful?",
        "model_answer": "A confusion matrix is a table showing the counts of true positives, true negatives, false positives, and false negatives for a classification model. It is useful because it allows calculation of metrics like precision, recall, and F1-score, which give a fuller picture of model performance than accuracy alone, especially for imbalanced datasets.",
        "key_points": "true/false positives/negatives, precision, recall, F1-score, imbalanced data",
    },
    {
        "category": "Machine Learning Basics",
        "question": "What is the difference between bagging and boosting?",
        "model_answer": "Bagging trains multiple models independently on different random subsets of data and combines their predictions, usually by averaging or voting, to reduce variance, as seen in Random Forests. Boosting trains models sequentially, where each new model focuses on correcting the errors of the previous ones, reducing bias, as seen in algorithms like AdaBoost and XGBoost.",
        "key_points": "independent training, sequential training, variance reduction, bias reduction, examples",
    },

    # ---------------- SYSTEM DESIGN (ENTRY LEVEL) ----------------
    {
        "category": "System Design",
        "question": "What are the main parts of a basic web application?",
        "model_answer": "A basic web application has a client such as a browser, a server that handles requests and application logic, and a database that stores persistent information. The client and server communicate over HTTP, and the server reads or writes data as needed.",
        "key_points": "client, server, application logic, database, HTTP",
    },
    {
        "category": "System Design",
        "question": "How would you design a simple URL shortener?",
        "model_answer": "I would generate a unique short code for each long URL, using a hash function or a base62 encoding of an auto-incrementing ID, and store the mapping between the short code and original URL in a database. When a user visits the short URL, the system looks up the original URL and redirects the user, with caching used to speed up frequently accessed links.",
        "key_points": "unique short code, database mapping, redirect logic, caching, scalability consideration",
    },
    {
        "category": "System Design",
        "question": "How would you handle a sudden spike in traffic on a web application?",
        "model_answer": "I would use horizontal scaling by adding more server instances behind a load balancer to distribute traffic. Caching frequently accessed data and using a Content Delivery Network for static assets would also reduce load, along with database read replicas to handle increased read traffic.",
        "key_points": "horizontal scaling, load balancer, caching, CDN, database replicas",
    },
]


def questions_with_difficulty():
    category_rows = defaultdict(list)
    for row in bank:
        category_rows[row["category"]].append(row)

    prepared = []
    for category, rows in category_rows.items():
        for position, row in enumerate(rows):
            level_index = min(position * 3 // len(rows), 2)
            prepared.append({**row, "difficulty": ("Beginner", "Intermediate", "Advanced")[level_index]})
    return prepared


def main():
    out_path = Path(__file__).with_name("question_bank.csv")
    prepared = questions_with_difficulty()
    fieldnames = ["category", "difficulty", "question", "model_answer", "key_points"]

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(prepared)

    print(f"Wrote {len(prepared)} questions -> {out_path}")
    categories = sorted(set(row["category"] for row in prepared))
    print(f"Categories: {categories}")


if __name__ == "__main__":
    main()
