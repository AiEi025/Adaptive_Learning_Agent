import sys
from pathlib import Path

sys.path.insert(
    0,
    str(Path(__file__).resolve().parent.parent)
)
from login.login_pass import PasswordHasher

enc=PasswordHasher()

def test_hashed_pass():
    hash_pass = enc.hash_password('jkfldsa324_')
    hash_pass1 = enc.hash_password('jkfldsa324_')
    assert hash_pass != hash_pass1

def test_varify_pass():
    hash_pass = enc.hash_password('jkfldsa324_')
    assert enc.verify_password('jkfldsa324_',hash_pass)
    assert not enc.verify_password('fdsfefswfwsf',hash_pass)
