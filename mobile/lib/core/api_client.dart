import 'dart:io';
import 'package:dio/dio.dart';

/// Singleton HTTP client wrapping Dio.
/// Automatically attaches the stored JWT Bearer token to every request.
/// Switches base URL between Android emulator and localhost automatically.
class ApiClient {
  static final ApiClient _instance = ApiClient._internal();
  static ApiClient get instance => _instance;

  late final Dio _dio;
  Dio get dio => _dio;

  String? _jwt;

  ApiClient._internal() {
    _dio =
        Dio(
            BaseOptions(
              baseUrl: _resolveBaseUrl(),
              connectTimeout: const Duration(seconds: 10),
              receiveTimeout: const Duration(seconds: 30),
              headers: {'Content-Type': 'application/json'},
            ),
          )
          ..interceptors.add(
            InterceptorsWrapper(
              onRequest: (options, handler) {
                if (_jwt != null && _jwt!.isNotEmpty) {
                  options.headers[HttpHeaders.authorizationHeader] =
                      'Bearer $_jwt';
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
  /// Android emulator cannot reach localhost directly; it uses 10.0.2.2.
  String _resolveBaseUrl() {
    try {
      if (Platform.isAndroid) return 'http://10.0.2.2:3000';
    } catch (_) {
      // Platform check may throw on web; fall through to localhost
    }
    return 'http://localhost:3000';
  }

  /// Set the JWT after login/register; persists it in SharedPreferences.
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
