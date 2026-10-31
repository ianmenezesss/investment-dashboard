"""Streaming authenticated encryption for one Investment Dashboard backup archive."""
from hashlib import sha256
import os
from pathlib import Path
import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt


MAGIC = b"IDBKP009"
SALT_BYTES = 16
NONCE_BYTES = 12
TAG_BYTES = 16
CHUNK_BYTES = 1024 * 1024


def _derive_key(passphrase: str, salt: bytes) -> bytes:
    if not isinstance(passphrase, str) or len(passphrase) < 16:
        raise ValueError("A frase de proteção precisa ter ao menos 16 caracteres")
    return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(passphrase.encode("utf-8"))


def encrypt_stream(source, destination, passphrase: str) -> tuple[int, str]:
    """Encrypt a readable stream as IDBKP009 + salt + nonce + AES-256-GCM data/tag."""
    salt, nonce = secrets.token_bytes(SALT_BYTES), secrets.token_bytes(NONCE_BYTES)
    header = MAGIC + salt + nonce
    encryptor = Cipher(algorithms.AES(_derive_key(passphrase, salt)), modes.GCM(nonce)).encryptor()
    encryptor.authenticate_additional_data(header)
    digest = sha256()
    size = 0

    def write(data: bytes) -> None:
        nonlocal size
        if data:
            destination.write(data)
            digest.update(data)
            size += len(data)

    write(header)
    while chunk := source.read(CHUNK_BYTES):
        write(encryptor.update(chunk))
    write(encryptor.finalize())
    write(encryptor.tag)
    return size, digest.hexdigest()


def decrypt_stream(source, destination, passphrase: str) -> tuple[int, str]:
    """Authenticate/decrypt an IDBKP009 stream; caller must discard output on error."""
    header_size = len(MAGIC) + SALT_BYTES + NONCE_BYTES
    header = source.read(header_size)
    if len(header) != header_size or not header.startswith(MAGIC):
        raise ValueError("Formato do backup não reconhecido")
    salt = header[len(MAGIC):len(MAGIC) + SALT_BYTES]
    nonce = header[-NONCE_BYTES:]
    # Inputs are file streams. Keeping the final GCM tag separate enables bounded-memory reads.
    if not source.seekable():
        raise ValueError("A leitura do backup precisa aceitar seek")
    source.seek(0, os.SEEK_END)
    total_size = source.tell()
    if total_size < header_size + TAG_BYTES:
        raise ValueError("Arquivo de backup truncado")
    ciphertext_size = total_size - header_size - TAG_BYTES
    source.seek(-TAG_BYTES, os.SEEK_END)
    tag = source.read(TAG_BYTES)
    source.seek(header_size)
    decryptor = Cipher(algorithms.AES(_derive_key(passphrase, salt)), modes.GCM(nonce, tag)).decryptor()
    decryptor.authenticate_additional_data(header)
    digest = sha256()
    size = ciphertext_size
    remaining = ciphertext_size
    while remaining:
        chunk = source.read(min(CHUNK_BYTES, remaining))
        if not chunk:
            raise ValueError("Arquivo de backup truncado")
        remaining -= len(chunk)
        plaintext = decryptor.update(chunk)
        destination.write(plaintext)
        digest.update(plaintext)
    try:
        final = decryptor.finalize()
    except InvalidTag as exc:
        raise ValueError("Autenticação do backup falhou: senha incorreta ou arquivo alterado") from exc
    if final:
        destination.write(final)
        digest.update(final)
        size += len(final)
    return size, digest.hexdigest()


def sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()
