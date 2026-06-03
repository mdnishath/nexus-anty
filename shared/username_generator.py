"""
shared/username_generator.py — Realistic Gmail username & identity generator.

Generates complete identities (name, DOB, gender, username, password)
for Gmail account creation.

Public API
----------
generate_identity() -> dict
generate_username(first_name, last_name) -> str
generate_password() -> str
"""

from __future__ import annotations

import random
import string
from datetime import datetime

# ── Name Databases ───────────────────────────────────────────────────────────

FIRST_NAMES_MALE = [
    'James', 'John', 'Robert', 'Michael', 'David', 'William', 'Richard', 'Joseph',
    'Thomas', 'Christopher', 'Daniel', 'Matthew', 'Anthony', 'Mark', 'Steven',
    'Andrew', 'Joshua', 'Kevin', 'Brian', 'Ryan', 'Timothy', 'Jason', 'Jeffrey',
    'Eric', 'Stephen', 'Jacob', 'Benjamin', 'Samuel', 'Patrick', 'Alexander',
    'Nathan', 'Peter', 'Adam', 'Tyler', 'Dylan', 'Ethan', 'Noah', 'Logan',
    'Aaron', 'Justin', 'Brandon', 'Austin', 'Kyle', 'Caleb', 'Zachary',
    'Luis', 'Carlos', 'Miguel', 'Rafael', 'Diego', 'Raj', 'Arjun', 'Vikram',
    'Amit', 'Rahul', 'Omar', 'Ali', 'Hassan', 'Ahmed', 'Mohammed', 'Yusuf',
]

FIRST_NAMES_FEMALE = [
    'Mary', 'Patricia', 'Jennifer', 'Linda', 'Barbara', 'Elizabeth', 'Susan',
    'Jessica', 'Sarah', 'Karen', 'Lisa', 'Nancy', 'Betty', 'Margaret', 'Sandra',
    'Ashley', 'Emily', 'Donna', 'Michelle', 'Dorothy', 'Amanda', 'Melissa',
    'Stephanie', 'Rebecca', 'Sharon', 'Laura', 'Cynthia', 'Kathleen', 'Amy',
    'Angela', 'Shirley', 'Anna', 'Brenda', 'Pamela', 'Emma', 'Nicole', 'Helen',
    'Samantha', 'Katherine', 'Christine', 'Deborah', 'Rachel', 'Carolyn',
    'Maria', 'Sofia', 'Isabella', 'Fatima', 'Priya', 'Ananya', 'Aisha',
    'Noor', 'Layla', 'Zara', 'Mia', 'Olivia', 'Ava', 'Charlotte', 'Luna',
]

LAST_NAMES = [
    'Smith', 'Johnson', 'Williams', 'Brown', 'Jones', 'Garcia', 'Miller',
    'Davis', 'Rodriguez', 'Martinez', 'Hernandez', 'Lopez', 'Gonzalez',
    'Wilson', 'Anderson', 'Thomas', 'Taylor', 'Moore', 'Jackson', 'Martin',
    'Lee', 'Perez', 'Thompson', 'White', 'Harris', 'Sanchez', 'Clark',
    'Lewis', 'Robinson', 'Walker', 'Young', 'Allen', 'King', 'Wright',
    'Scott', 'Torres', 'Nguyen', 'Hill', 'Flores', 'Green', 'Adams',
    'Nelson', 'Baker', 'Hall', 'Rivera', 'Campbell', 'Mitchell', 'Carter',
    'Roberts', 'Gomez', 'Phillips', 'Evans', 'Turner', 'Diaz', 'Parker',
    'Cruz', 'Edwards', 'Collins', 'Reyes', 'Stewart', 'Morris', 'Morales',
    'Khan', 'Singh', 'Patel', 'Sharma', 'Kumar', 'Das', 'Ali', 'Rahman',
]


def generate_identity() -> dict:
    """Generate a complete realistic identity for Gmail signup.

    Returns dict with: first_name, last_name, username, password,
    birth_month, birth_day, birth_year, gender, recovery_email
    """
    gender = random.choice(['male', 'female'])
    first_name = random.choice(
        FIRST_NAMES_MALE if gender == 'male' else FIRST_NAMES_FEMALE
    )
    last_name = random.choice(LAST_NAMES)

    username = generate_username(first_name, last_name)
    password = generate_password()

    # DOB: 18-45 years old
    current_year = datetime.now().year
    birth_year = random.randint(current_year - 45, current_year - 18)
    birth_month = random.randint(1, 12)
    # Valid day for month
    max_day = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][birth_month - 1]
    birth_day = random.randint(1, max_day)

    return {
        'first_name': first_name,
        'last_name': last_name,
        'username': username,
        'password': password,
        'birth_month': str(birth_month),
        'birth_day': str(birth_day),
        'birth_year': str(birth_year),
        'gender': '1' if gender == 'male' else '2',
        'gender_text': gender,
        'recovery_email': '',
    }


def generate_username(first_name: str, last_name: str) -> str:
    """Generate a realistic Gmail username.

    Simple format only:
    - firstnamelastname (no dots, no underscores)
    - firstname + 4digit year
    """
    fn = first_name.lower().strip()
    ln = last_name.lower().strip()
    year = random.randint(1985, 2005)
    num4 = random.randint(1000, 9999)

    patterns = [
        f'{fn}{ln}{year}',
        f'{fn}{ln}{num4}',
        f'{fn}{year}{ln}',
        f'{ln}{fn}{year}',
        f'{ln}{fn}{num4}',
        f'{fn}{num4}{ln}',
    ]

    username = random.choice(patterns)

    # Ensure minimum 12 chars
    if len(username) < 12:
        username += str(random.randint(100, 9999))

    return username


def generate_password(length: int = 12) -> str:
    """Generate a strong but typeable password.

    Pattern: Word + Special + Numbers + Word
    Example: Blue$47Moon, Fast#82Rain
    """
    words = [
        'Blue', 'Red', 'Moon', 'Star', 'Rain', 'Wind', 'Fire', 'Lake',
        'Snow', 'Sun', 'Sky', 'Gold', 'Iron', 'Rock', 'Wave', 'Pine',
        'Rose', 'Oak', 'Fox', 'Bear', 'Wolf', 'Hawk', 'Deer', 'Fish',
        'Lion', 'Bird', 'Frog', 'Jade', 'Ruby', 'Onyx', 'Sage', 'Mint',
        'Dawn', 'Dusk', 'Nova', 'Echo', 'Bolt', 'Glow', 'Haze', 'Peak',
    ]
    specials = ['!', '@', '#', '$', '%', '&', '*']

    w1 = random.choice(words)
    w2 = random.choice(words)
    while w2 == w1:
        w2 = random.choice(words)

    special = random.choice(specials)
    nums = str(random.randint(10, 99))

    patterns = [
        f'{w1}{special}{nums}{w2}',
        f'{w1}{nums}{special}{w2}',
        f'{w1.upper()}{special}{nums}{w2.lower()}',
        f'{w2}{nums}{w1}{special}',
    ]
    return random.choice(patterns)


def generate_batch(count: int) -> list[dict]:
    """Generate multiple identities at once.

    Ensures no duplicate usernames in the batch.
    """
    identities = []
    used_usernames = set()

    for _ in range(count):
        identity = generate_identity()
        # Ensure unique username
        while identity['username'] in used_usernames:
            identity['username'] = generate_username(
                identity['first_name'], identity['last_name']
            )
        used_usernames.add(identity['username'])
        identities.append(identity)

    return identities
