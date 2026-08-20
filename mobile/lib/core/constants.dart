/// ── Server configuration ────────────────────────────────────────────────────
///
/// CHANGE THIS to your laptop's local IP address when testing on a
/// physical Android device (run `ipconfig` on Windows → IPv4 Address).
/// When testing on an Android EMULATOR keep it as 10.0.2.2 (routes to host).
/// iOS Simulator always uses localhost.
class ServerConfig {
  /// Your laptop's IP on the local network (for physical Android devices).
  static const String laptopIp = '10.81.222.35';

  /// Port the Node.js backend runs on.
  static const int port = 3000;
}
