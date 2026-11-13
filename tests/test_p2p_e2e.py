'''
╔══════════════════════════════════════════════════════╗
║  Creator:                  Shirayume-Hibiki          ║
║  Creation date:            12/11/26                  ║
║  Edit dates / contributor:                           ║
║  13/11/26 Shirayume-Hibiki                           ║
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

    def test_busy_peer_rejection_no_false_positive(self):
        """Verify that when Bob is chatting with Alice, Zack is rejected and gets False without false-connected state."""
        print("\n[E2E] Testing busy peer rejection...")
        self.alice.start()
        self.bob.start()
        time.sleep(1.2)

        zack = PeerNode(name="Zack", tcp_port=7003, discovery_port=9999, downloads_dir=self.test_dir)
        zack.start()
        time.sleep(1.2)

        # Alice connects to Bob
        ok_alice = self.alice.connectToPeer("Bob")
        self.assertTrue(ok_alice, "Alice should connect to Bob")
        time.sleep(0.5)

        # Zack attempts to connect to busy Bob
        ok_zack = zack.connectToPeer("Bob")
        self.assertFalse(ok_zack, "Zack should be rejected by busy Bob")
        self.assertIsNone(zack.active_sock, "Zack active_sock must be None after rejection")
        self.assertIsNone(zack.active_peer_name, "Zack active_peer_name must be None")

        zack.stop()
        print("[E2E] Busy peer rejection test PASSED!")

    def test_multi_peer_identity_attribution_on_same_host(self):
        """Verify that Zack connecting to Bob is attributed to Zack, never to Alice (first alphabetically)."""
        print("\n[E2E] Testing multi-peer identity attribution...")
        self.bob.start()

        zack = PeerNode(name="Zack", tcp_port=7003, discovery_port=9999, downloads_dir=self.test_dir)
        zack.start()

        # Add Alice to Bob's peer table so Alice is alphabetically first at same IP (127.0.0.1)
        self.bob.peer_table.addOrUpdatePeer("Alice", "127.0.0.1", 7001, "online")
        self.bob.peer_table.addOrUpdatePeer("Zack", "127.0.0.1", 7003, "online")
        zack.peer_table.addOrUpdatePeer("Bob", "127.0.0.1", 7002, "online")

        # Verify Bob's table lists Alice first
        bob_peers = [p.name for p in self.bob.peer_table.getActivePeers()]
        self.assertEqual(bob_peers[0], "Alice", "Alice must be first alphabetically in Bob's table")
        self.assertIn("Zack", bob_peers)

        # Zack connects to Bob from 127.0.0.1
        ok = zack.connectToPeer("Bob")
        self.assertTrue(ok, "Zack should connect to Bob")
        time.sleep(0.5)

        # Bob MUST attribute connection to Zack, NOT Alice!
        self.assertEqual(self.bob.active_peer_name, "Zack", "Bob must attribute incoming connection to Zack")
        self.assertEqual(zack.active_peer_name, "Bob", "Zack active peer must be Bob")

        zack.leaveChat()
        zack.stop()
        print("[E2E] Identity attribution test PASSED!")

    def test_peer_table_port_update_on_restart(self):
        """Verify that PeerTable properly updates port when a peer restarts on a new dynamic port."""
        print("\n[E2E] Testing peer table port update on restart...")
        from peer.peer_table import PeerTable
        table = PeerTable(timeout=10.0)

        # Initial beacon: Bob on 5001
        table.addOrUpdatePeer(name="Bob", ip="192.168.1.50", port=5001, status="online")
        peer = table.getPeerByName("Bob")
        self.assertIsNotNone(peer)
        self.assertEqual(peer.port, 5001)

        # Bob restarts on dynamic port 5099 within timeout window
        table.addOrUpdatePeer(name="Bob", ip="192.168.1.50", port=5099, status="online")
        peer = table.getPeerByName("Bob")
        self.assertEqual(peer.port, 5099, "Peer port must update to 5099 upon restart")

        print("[E2E] Peer table port update test PASSED!")

    def test_concurrent_chat_during_file_transfer(self):
        """Verify that concurrent chat messages do not corrupt TCP framing during chunked file transfer."""
        print("\n[E2E] Testing concurrent chat during file transfer...")
        self.alice.start()
        self.bob.start()
        time.sleep(1.2)

        ok = self.alice.connectToPeer("Bob")
        self.assertTrue(ok)
        time.sleep(0.5)

        # Create larger test file (400 KB)
        large_file = os.path.join(self.test_dir, "large_doc.bin")
        with open(large_file, "wb") as f:
            f.write(os.urandom(400 * 1024))

        # Start file transfer
        self.alice.sendFile(large_file)

        # Concurrently send chat messages while file is being transferred
        for i in range(10):
            self.alice.sendMessage(f"Concurrent message {i}")
            time.sleep(0.02)

        # Wait for file transfer to complete
        time.sleep(3.0)

        # Verify chat messages were received without frame corruption
        chat_texts = [m[1] for m in self.bob_msgs]
        for i in range(10):
            self.assertIn(f"Concurrent message {i}", chat_texts)

        # Verify file received and matches exact size
        self.assertGreaterEqual(len(self.bob_files), 1)
        received_path = self.bob_files[0][1]
        self.assertEqual(os.path.getsize(received_path), 400 * 1024)

        self.alice.leaveChat()
        print("[E2E] Concurrent chat during file transfer test PASSED!")

    def test_filename_sanitization_and_traversal_prevention(self):
        """Verify filename sanitization prevents traversal and crashes on invalid/dot filenames."""
        print("\n[E2E] Testing filename sanitization...")
        from file_transfer.file_manager import getUniqueDownloadHandle, sanitizeFilename

        # Traversal and invalid names
        self.assertEqual(sanitizeFilename("../../evil.exe"), "evil.exe")
        self.assertEqual(sanitizeFilename("..\\..\\windows\\system32.dll"), "system32.dll")
        self.assertTrue(sanitizeFilename("").startswith("download_"))
        self.assertTrue(sanitizeFilename(".").startswith("download_"))
        self.assertTrue(sanitizeFilename("..").startswith("download_"))
        self.assertEqual(sanitizeFilename(".bashrc"), "bashrc")

        # Atomic handle creation without TOCTOU race
        dest_dir = os.path.join(self.test_dir, "sanitize_dl")
        path1, h1 = getUniqueDownloadHandle(dest_dir, "notes.txt")
        path2, h2 = getUniqueDownloadHandle(dest_dir, "notes.txt")
        self.assertNotEqual(path1, path2)
        h1.close()
        h2.close()

        # Malicious traversal path is trapped inside dest_dir
        path_trav, ht = getUniqueDownloadHandle(dest_dir, "../../../../outside.txt")
        ht.close()
        self.assertTrue(os.path.abspath(path_trav).startswith(os.path.abspath(dest_dir)))

        print("[E2E] Filename sanitization test PASSED!")

    def test_status_validation_and_sanitization(self):
        """Verify that unvalidated/corrupted status strings in beacons are sanitized to 'online'."""
        print("\n[E2E] Testing status validation...")
        import json
        from protocol.udp_protocol import parseDatagram

        # Malformed / invalid status values
        bad_packet = json.dumps({
            "magic": "LANCHAT",
            "type": "BEACON",
            "name": "Eve",
            "port": 5005,
            "status": "super_hacked_status_12345"
        }).encode("utf-8")

        parsed = parseDatagram(bad_packet)
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["status"], "online", "Invalid status string must be sanitized to 'online'")

        numeric_status_packet = json.dumps({
            "magic": "LANCHAT",
            "type": "BEACON",
            "name": "Eve",
            "port": 5005,
            "status": 9999
        }).encode("utf-8")

        parsed_num = parseDatagram(numeric_status_packet)
        self.assertIsNotNone(parsed_num)
        self.assertEqual(parsed_num["status"], "online", "Non-string status must be sanitized to 'online'")
        print("[E2E] Status validation test PASSED!")

    def test_peer_goodbye_does_not_delete_wrong_peer_on_same_port(self):
        """Verify that GOODBYE from Bob does not delete Charlie who happens to share the same port."""
        print("\n[E2E] Testing targeted peer deletion on GOODBYE...")
        from peer.peer_table import PeerTable
        table = PeerTable(timeout=10.0)

        # Bob and Charlie both registered on port 7002 at different IPs
        table.addOrUpdatePeer("Bob", "192.168.1.50", 7002, "online")
        table.addOrUpdatePeer("Charlie", "192.168.1.60", 7002, "online")

        # Bob departs with GOODBYE
        table.removePeer("192.168.1.50", 7002, name="Bob")

        # Verify Bob is removed, but Charlie remains completely intact!
        self.assertIsNone(table.getPeerByName("Bob"))
        charlie = table.getPeerByName("Charlie")
        self.assertIsNotNone(charlie)
        self.assertEqual(charlie.ip, "192.168.1.60")
        print("[E2E] Targeted peer deletion test PASSED!")

    def test_active_chat_cleans_up_on_peer_goodbye(self):
        """Verify that when the remote active peer leaves, the local active session cleanly tears down."""
        print("\n[E2E] Testing active chat cleanup on peer departure...")
        self.alice.start()
        self.bob.start()
        time.sleep(1.2)

        # Alice connects to Bob
        ok = self.alice.connectToPeer("Bob")
        self.assertTrue(ok)
        time.sleep(0.5)
        self.assertEqual(self.alice.active_peer_name, "Bob")

        # Bob stops and broadcasts GOODBYE
        self.bob.stop()
        time.sleep(1.0)

        # Alice should have automatically cleaned up active session!
        self.assertIsNone(self.alice.active_sock, "Alice active_sock must be None after Bob leaves")
        self.assertIsNone(self.alice.active_peer_name, "Alice active_peer_name must be None after Bob leaves")
        print("[E2E] Active chat cleanup on peer departure test PASSED!")

    def test_p2p_logging_and_config_integration(self):
        """Verify that P2P Node loads configs and creates log files in logs/."""
        print("\n[E2E] Testing logging and config integration...")
        from common_functions import loadLanChatConfig, loadUIConfig
        cfg_lan = loadLanChatConfig()
        cfg_ui = loadUIConfig()

        self.assertIn("discovery_port", cfg_lan)
        self.assertEqual(cfg_lan["discovery_port"], 9999)
        self.assertIn("progress_bar_width", cfg_ui)

        # Check that Alice's CNLogger created a log file
        self.assertTrue(os.path.isfile(self.alice.log.filepath), "Log file must exist on disk")
        with open(self.alice.log.filepath, "r", encoding="utf-8") as f:
            content = f.read()
            self.assertIn("P2P Node initiated", content)
        print("[E2E] Logging and config integration test PASSED!")

    def test_terminal_ui_cross_platform_buffering(self):
        """Verify TerminalUI buffers characters and redrawing correctly."""
        print("\n[E2E] Testing TerminalUI buffering...")
        from ui.terminal import TerminalUI
        tui = TerminalUI(prompt="[Test] > ", ansi_enabled=False)

        # Simulate buffer input
        tui._input_buffer = ["h", "e", "l", "l", "o"]
        # printLine should not crash in non-interactive / non-ANSI environments
        tui.printLine("Background notification")
        self.assertEqual("".join(tui._input_buffer), "hello")
        print("[E2E] TerminalUI buffering test PASSED!")

if __name__ == "__main__":
    unittest.main()
