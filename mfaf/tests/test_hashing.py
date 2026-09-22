import io, os, tempfile, unittest
from mfaf import hashing
from mfaf.errors import ValidationError


class TestHashing(unittest.TestCase):
    def test_known_vector(self):
        h = hashing.hash_bytes(b"abc")
        self.assertEqual(h["sha256"],
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
        self.assertEqual(h["_size"], 3)

    def test_streaming_large_chunks(self):
        data = b"A" * (3 * 1024 * 1024 + 7)   # > chunk size
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(data); path = f.name
        try:
            h = hashing.hash_file(path)
            self.assertEqual(h["_size"], len(data))
            self.assertEqual(h["sha256"], hashing.hash_bytes(data)["sha256"])
        finally:
            os.unlink(path)

    def test_max_bytes_enforced(self):
        with self.assertRaises(ValidationError):
            hashing.hash_stream(io.BytesIO(b"x" * 100), max_bytes=10)

    def test_sha512_present(self):
        h = hashing.hash_bytes(b"abc", algorithms=("sha256", "sha512"))
        self.assertEqual(len(h["sha512"]), 128)


if __name__ == "__main__":
    unittest.main()
