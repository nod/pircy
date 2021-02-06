
import hashlib

def gen_password():
    seed = str(urandom(20)).encode('utf-8')
    h = hashlib.new('sha512', seed).hexdigest()[:20]
    return h
