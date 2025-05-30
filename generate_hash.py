from werkzeug.security import generate_password_hash

password = "ITgwXqkIl2co6RsgAvBhvQ"
hash = generate_password_hash(password)
print(f"Password hash for '{password}':")
print(hash) 