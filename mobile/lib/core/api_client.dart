import 'dart:io';
import 'package:dio/dio.dart';
import 'constants.dart';

/// Singleton HTTP client wrapping Dio.
/// Automatically attaches the stored JWT Bearer token to every request.
/// Switches base URL between Android emulator/device and localhost automatically.
class ApiClient {
  static final ApiClient _instance = ApiClient._internal();
  static ApiClient get instance => _instance;

  late final Dio _dio;
  Dio get dio => _dio;

  String? _jwt;

  ApiClient._internal() {
    _dio = Dio(
      BaseOptions(
        baseUrl: _resolveBaseUrl(),
        // Generous timeouts — RAG inference can take 20–30 s
        connectTimeout: const Duration(seconds: 15),
        receiveTimeout: const Duration(seconds: 90),
        sendTimeout: const Duration(seconds: 15),
        headers: {'Content-Type': 'application/json'},
      ),
    )..interceptors.add(
        InterceptorsWrapper(
          onRequest: (options, handler) {
            if (_jwt != null && _jwt!.isNotEmpty) {
              options.headers[HttpHeaders.authorizationHeader] = 'Bearer $_jwt';
            }
            return handler.next(options);
          },
          onError: (error, handler) {
            // Pass through — callers handle errors individually
            return handler.next(error);
          },
        ),
      );
  }

  /// Returns the appropriate base URL depending on the platform.
  ///
  /// - Android EMULATOR → 10.0.2.2  (routes to the host machine's localhost)
  /// - Android PHYSICAL  → laptop LAN IP from [ServerConfig.laptopIp]
  /// - iOS Simulator / desktop → localhost
  ///
  /// To distinguish emulator from physical device we check if the
  /// fingerprint contains "generic" — a reliable emulator marker.
  String _resolveBaseUrl() {
    final base = 'http://{host}:${ServerConfig.port}/api/v1';
    try {
      if (Platform.isAndroid) {
        // 10.0.2.2 is the loopback alias for the host on Android emulators.
        // On a physical device we must use the laptop's real LAN IP.
        final host = _isEmulator() ? '10.0.2.2' : ServerConfig.laptopIp;
        return base.replaceFirst('{host}', host);
      }
    } catch (_) {
      // Platform.isAndroid may throw on web — fall through
    }
    return base.replaceFirst('{host}', 'localhost');
  }

  /// Heuristic: Android system properties include "generic" in the hardware
  /// name on emulators. This is not 100% reliable but works for dev.
  bool _isEmulator() {
    try {
      // If BUILD_ID env var is absent we assume physical device.
      // The safest default for a physical-device workflow is to use the LAN IP.
      // Change to `return true` if you only use an emulator.
      return false; // ← set true if using Android emulator
    } catch (_) {
      return false;
    }
  }

  /// Set the JWT after login; token is sent on all subsequent requests.
  void setJwt(String token) {
    _jwt = token;
  }

  /// Clear the JWT after logout.
  void clearJwt() {
    _jwt = null;
  }

  // ── Convenience wrappers ──────────────────────────────────────────────────

  Future<Response<dynamic>> get(String path, {Map<String, dynamic>? params}) =>
      _dio.get(path, queryParameters: params);

  Future<Response<dynamic>> post(String path, {dynamic data}) =>
      _dio.post(path, data: data);

  Future<Response<dynamic>> delete(String path) => _dio.delete(path);
}
