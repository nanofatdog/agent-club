"""Tests for cryptographic primitives."""

import pytest
from agent_club.crypto.keys import IdentityKey, ExchangeKey, KeyBundle
from agent_club.crypto.cipher import AESCipher, RoomCipher, RekeyManager
from agent_club.crypto.signature import MessageSigner, SignatureError
from agent_club.crypto.room_key import X3DHHandshake, RoomKeyManager


class TestIdentityKey:
    """Test Ed25519 identity key operations."""

    def test_generate_keypair(self):
        key = IdentityKey()
        assert key.public_key_bytes is not None
        assert len(key.public_key_bytes) == 32
        assert len(key.private_key_bytes) == 32

    def test_fingerprint(self):
        key = IdentityKey()
        fp = key.fingerprint()
        assert isinstance(fp, str)
        assert len(fp) > 0
        assert fp == key.fingerprint()  # Deterministic!

    def test_sign_and_verify(self):
        key = IdentityKey()
        data = b"Hello, Agent Club!"

        signature = key.sign(data)
        assert len(signature) == 64
        assert key.verify(data, signature)

        # Tampered data should fail
        assert not key.verify(b"different data", signature)

    def test_export_import(self):
        key = IdentityKey()
        pem = key.export_private()
        assert b"PRIVATE KEY" in pem

        loaded = IdentityKey.from_private_pem(pem)
        assert loaded.fingerprint() == key.fingerprint()

    def test_export_with_password(self):
        key = IdentityKey()
        pem = key.export_private(password=b"test123")
        assert b"ENCRYPTED" in pem

        loaded = IdentityKey.from_private_pem(pem, password=b"test123")
        assert loaded.fingerprint() == key.fingerprint()

        # Wrong password should fail
        with pytest.raises(Exception):
            IdentityKey.from_private_pem(pem, password=b"wrong")


class TestExchangeKey:
    """Test X25519 exchange key operations."""

    def test_derive_shared_secret(self):
        alice = ExchangeKey()
        bob = ExchangeKey()

        secret_alice = alice.derive_shared_secret(bob.public_key_bytes)
        secret_bob = bob.derive_shared_secret(alice.public_key_bytes)

        assert len(secret_alice) == 32
        assert secret_alice == secret_bob  # Same shared secret!

    def test_different_keys_different_secrets(self):
        alice = ExchangeKey()
        bob = ExchangeKey()
        charlie = ExchangeKey()

        secret_ab = alice.derive_shared_secret(bob.public_key_bytes)
        secret_ac = alice.derive_shared_secret(charlie.public_key_bytes)

        assert secret_ab != secret_ac


class TestKeyBundle:
    """Test KeyBundle (combined identity + exchange)."""

    def test_create_bundle(self):
        bundle = KeyBundle(name="TestAgent")
        assert bundle.fingerprint is not None
        assert bundle.name == "TestAgent"
        assert len(bundle.exchange_pubkey) == 32

    def test_sign_and_verify(self):
        bundle = KeyBundle(name="Alice")
        data = b"Test message"

        sig = bundle.sign(data)
        assert bundle.verify(data, sig)

    def test_export_import(self):
        bundle = KeyBundle(name="TestAgent")
        data = bundle.export(password=b"secret123")

        loaded = KeyBundle.from_export(data, password=b"secret123")
        assert loaded.fingerprint == bundle.fingerprint
        assert loaded.name == "TestAgent"


class TestAESCipher:
    """Test AES-256-GCM encryption."""

    def test_encrypt_decrypt(self):
        key = b"0" * 32  # 32-byte key
        cipher = AESCipher(key)

        plaintext = b"Hello, Agent Club!"
        nonce, ciphertext = cipher.encrypt(plaintext)
        decrypted = cipher.decrypt(nonce, ciphertext)

        assert decrypted == plaintext

    def test_tampered_data_fails(self):
        key = b"0" * 32
        cipher = AESCipher(key)

        plaintext = b"Sensitive data"
        nonce, ciphertext = cipher.encrypt(plaintext)

        # Tamper with ciphertext
        tampered = bytearray(ciphertext)
        tampered[0] ^= 1
        with pytest.raises(Exception):
            cipher.decrypt(nonce, bytes(tampered))

    def test_wrong_key_fails(self):
        key1 = b"1" * 32
        key2 = b"2" * 32
        cipher1 = AESCipher(key1)
        cipher2 = AESCipher(key2)

        plaintext = b"Secret"
        nonce, ciphertext = cipher1.encrypt(plaintext)

        with pytest.raises(Exception):
            cipher2.decrypt(nonce, ciphertext)

    def test_invalid_key_length(self):
        with pytest.raises(ValueError):
            AESCipher(b"short")

    def test_associated_data(self):
        key = b"0" * 32
        cipher = AESCipher(key)

        plaintext = b"Hello"
        ad = b"room_id=abc123"
        nonce, ct = cipher.encrypt(plaintext, associated_data=ad)

        # Wrong associated data should fail
        with pytest.raises(Exception):
            cipher.decrypt(nonce, ct, associated_data=b"wrong")

        # Correct associated data should succeed
        dec = cipher.decrypt(nonce, ct, associated_data=ad)
        assert dec == plaintext


class TestRoomCipher:
    """Test RoomCipher with sender metadata."""

    def test_encrypt_decrypt_message(self):
        room_key = b"R" * 32
        cipher = RoomCipher(room_key)

        sender_id = "agent_abc123"
        message_data = b"Hello room!"
        metadata = b"room=test123"

        nonce, ct = cipher.encrypt_message(sender_id, message_data, metadata)
        result = cipher.decrypt_message(nonce, ct, expected_sender_id=sender_id, associated_data=metadata)

        assert result["sender_id"] == sender_id
        assert result["data"] == message_data

    def test_wrong_sender_rejected(self):
        room_key = b"R" * 32
        cipher = RoomCipher(room_key)

        nonce, ct = cipher.encrypt_message("alice", b"data")
        with pytest.raises(ValueError):
            cipher.decrypt_message(nonce, ct, expected_sender_id="bob")


class TestX3DHHandshake:
    """Test X3DH-like key exchange handshake."""

    def test_full_handshake(self):
        alice_bundle = KeyBundle(name="Alice")
        bob_bundle = KeyBundle(name="Bob")

        # Alice initiates
        alice_handshake = X3DHHandshake(initiator=True)
        init_msg = alice_handshake.initiate(alice_bundle)

        # Bob responds
        bob_handshake = X3DHHandshake(initiator=False)
        response_msg = bob_handshake.respond(bob_bundle, init_msg)

        # Alice completes
        alice_secret = alice_handshake.complete(response_msg)

        # Both should have the same shared secret
        assert alice_secret == bob_handshake.shared_secret
        assert len(alice_secret) == 32


class TestMessageSigner:
    """Test message signing and verification."""

    def test_sign_and_verify(self):
        alice = IdentityKey()
        payload = b"Test message"

        signed = MessageSigner.sign_message(alice, payload)
        assert "signature" in signed
        assert signed["payload"] == payload

        # Verify with same key
        result = MessageSigner.verify_message(alice, signed)
        assert result is True

    def test_expired_message_fails(self):
        alice = IdentityKey()
        import time

        signed = MessageSigner.sign_message(alice, b"data")
        # Artificially age the timestamp
        signed["timestamp"] = int(time.time() * 1000) - 120000  # 2 minutes ago

        with pytest.raises(SignatureError):
            MessageSigner.verify_message(alice, signed, tolerance_ms=60000)

    def test_wrong_key_fails(self):
        alice = IdentityKey()
        bob = IdentityKey()

        signed = MessageSigner.sign_message(alice, b"data")
        with pytest.raises(SignatureError):
            MessageSigner.verify_message(bob, signed)