'''
╔══════════════════════════════════════════════════════╗
║  Creator:                  Shirayume-Hibiki          ║
║  Creation date:            12/11/26                  ║
║  Edit dates / contributor:                           ║
╚══════════════════════════════════════════════════════╝
'''

import os
import sys
import time
import unittest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LIB_V1_DIR = os.path.join(PROJECT_ROOT, "script", "lib", "v1")
if LIB_V1_DIR not in sys.path:
    sys.path.insert(0, LIB_V1_DIR)

from peer.peer_node import PeerNode

class TestLanChatP2P(unittest.TestCase):
    def setUp(self):
        self.test_dir = os.path.join(PROJECT_ROOT, "scratch_e2e_test")
        os.makedirs(self.test_dir, exist_ok=True)
        self.alice_downloads = os.path.join(self.test_dir, "alice_dl")
        self.bob_downloads = os.path.join(self.test_dir, "bob_dl")

        # Create dummy file to send (150 KB)
        self.sample_file = os.path.join(self.test_dir, "sample_document.dat")
        with open(self.sample_file, "wb") as f:
            f.write(b"HelloWorld" * 15000)

        self.alice_msgs = []
        self.bob_msgs = []
        self.bob_files = []
        self.alice_notices = []
        self.bob_notices = []

        self.alice = PeerNode(
            name="Alice",
            tcp_port=7001,
            discovery_port=9999,
            downloads_dir=self.alice_downloads,
            on_message=lambda s, m: self.alice_msgs.append((s, m)),
            on_notice=lambda m: self.alice_notices.append(m),
        )
        self.bob = PeerNode(
            name="Bob",
            tcp_port=7002,
            discovery_port=9999,
            downloads_dir=self.bob_downloads,
            on_message=lambda s, m: self.bob_msgs.append((s, m)),
            on_file_complete=lambda fn, p, is_up: self.bob_files.append((fn, p)),
            on_notice=lambda m: self.bob_notices.append(m),
        )

    def tearDown(self):
        self.alice.stop()
        self.bob.stop()
        time.sleep(0.5)
        # Clean up scratch dir
        if os.path.exists(self.test_dir):
            for root, dirs, files in os.walk(self.test_dir, topdown=False):
                for f in files:
                    try:
                        os.remove(os.path.join(root, f))
                    except Exception:
                        pass
                for d in dirs:
                    try:
                        os.rmdir(os.path.join(root, d))
                    except Exception:
                        pass
            try:
                os.rmdir(self.test_dir)
            except Exception:
                pass

    def test_p2p_full_workflow(self):
        print("\n[E2E] Starting Alice and Bob nodes...")
        self.alice.start()
        self.bob.start()

        # 1. Peer Discovery
        print("[E2E] Waiting for UDP beacon exchange...")
        time.sleep(1.2)

        alice_peers = self.alice.peer_table.getActivePeers()
        print(f"[E2E] Alice found peers: {[p.name for p in alice_peers]}")
        self.assertTrue(any(p.name == "Bob" for p in alice_peers), "Alice should discover Bob")

        # 2. Status Update
        print("[E2E] Testing status update (Bob -> away)...")
        self.bob.setStatus("away")
        time.sleep(0.5)
        bob_peer_in_alice = self.alice.peer_table.getPeerByName("Bob")
        self.assertIsNotNone(bob_peer_in_alice)
        self.assertEqual(bob_peer_in_alice.status, "away", "Bob's status in Alice table should be 'away'")

        # 3. TCP Connect & Chat
        print("[E2E] Alice connecting to Bob...")
        connected = self.alice.connectToPeer("Bob")
        self.assertTrue(connected, "Alice should successfully connect to Bob")
        time.sleep(0.5)

        print("[E2E] Alice sending chat message to Bob...")
        sent = self.alice.sendMessage("Hello Bob, this is a test message!")
        self.assertTrue(sent)
        time.sleep(0.5)

        self.assertGreaterEqual(len(self.bob_msgs), 1, "Bob should receive chat message")
        self.assertEqual(self.bob_msgs[-1][0], "Alice")
        self.assertEqual(self.bob_msgs[-1][1], "Hello Bob, this is a test message!")
        print(f"[E2E] Bob received message: '{self.bob_msgs[-1][1]}'")

        # 4. Chunked File Transfer
        print("[E2E] Alice sending file to Bob...")
        file_sent = self.alice.sendFile(self.sample_file)
        self.assertTrue(file_sent)
        time.sleep(1.5)

        self.assertEqual(len(self.bob_files), 1, "Bob should finish receiving file")
        received_filename, received_path = self.bob_files[0]
        self.assertEqual(received_filename, "sample_document.dat")
        self.assertTrue(os.path.isfile(received_path))
        self.assertEqual(os.path.getsize(received_path), os.path.getsize(self.sample_file))
        print(f"[E2E] Bob successfully received file ({os.path.getsize(received_path)} bytes) at {received_path}")

        # 5. Graceful Leave
        print("[E2E] Alice leaving chat...")
        self.alice.leaveChat()
        time.sleep(0.5)
        self.assertIsNone(self.alice.active_sock)

        print("[E2E] Full P2P workflow test PASSED successfully!")

if __name__ == "__main__":
    unittest.main()
