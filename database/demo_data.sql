INSERT INTO users (username, email, password_hash, role, is_active)
VALUES (
    'roshan_admin',
    'roshanbhadane@gmail.com',
    'scrypt:32768:8:1$1vqSVxUanyiDQHQ0$d372f571e424aca25d10acc904ec70e4b8aed382a712083d6ee990328849c7a1a517d4eba1811a7c171e6b7b539873903569b2b99d0a2e98801e5d427a30e218',
    'admin',
    1
);