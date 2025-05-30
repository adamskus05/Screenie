-- Delete existing admin if exists
DELETE FROM users WHERE username = 'OPERATOR_1337';

-- Insert admin user with pre-generated password hash
INSERT INTO users (
    username,
    password_hash,
    email,
    is_admin,
    is_approved,
    status,
    created_at,
    updated_at
) VALUES (
    'OPERATOR_1337',
    'pbkdf2:sha256:600000$dxqFDHAP$e7a6cf5c6fb8e6f8d9ef3c8f3c6a1e6d4c7b8a9d0e3f2c5b8a7d0e3f2c5b8a7',
    'admin@example.com',
    1,
    1,
    'active',
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
); 