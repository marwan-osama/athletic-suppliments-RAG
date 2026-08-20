import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:dio/dio.dart';
import '../../core/api_client.dart';
import '../../core/models.dart';

/// Manages authentication state: login, register, logout, JWT persistence.
///
/// Backend responses:
///   POST /auth/register  → { id, email }          (no token — must login after)
///   POST /auth/login     → { token }               (JWT only — decode for user info)
///   GET  /auth/me        → { id, email, ... }
class AuthProvider extends ChangeNotifier {
  User? _user;
  bool _loading = false;
  String? _error;

  User? get user => _user;
  bool get isAuthenticated => _user != null;
  bool get loading => _loading;
  String? get error => _error;

  AuthProvider() {
    _loadFromPrefs();
  }

  // ── Persistence ────────────────────────────────────────────────────────────

  Future<void> _loadFromPrefs() async {
    final prefs = await SharedPreferences.getInstance();
    final jwt = prefs.getString('jwt');
    final userJson = prefs.getString('user');
    if (jwt != null && userJson != null) {
      _user = User.fromJsonString(userJson);
      ApiClient.instance.setJwt(jwt);
    }
    notifyListeners();
  }

  Future<void> _saveToPrefs(String jwt, User user) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('jwt', jwt);
    await prefs.setString('user', user.toJsonString());
  }

  Future<void> _clearPrefs() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('jwt');
    await prefs.remove('user');
  }

  // ── Auth actions ───────────────────────────────────────────────────────────

  /// Register then automatically login to get the JWT.
  Future<bool> register(String email, String password) async {
    _loading = true;
    _error = null;
    notifyListeners();
    try {
      // Step 1: register (returns { id, email } — no token)
      await ApiClient.instance.post(
        '/auth/register',
        data: {'email': email, 'password': password},
      );
      // Step 2: login to get the token
      return await _loginInternal(email, password);
    } on DioException catch (e) {
      _error = _extractError(e);
      return false;
    } catch (e) {
      _error = e.toString();
      return false;
    } finally {
      _loading = false;
      notifyListeners();
    }
  }

  Future<bool> login(String email, String password) async {
    _loading = true;
    _error = null;
    notifyListeners();
    try {
      return await _loginInternal(email, password);
    } on DioException catch (e) {
      _error = _extractError(e);
      return false;
    } catch (e) {
      _error = e.toString();
      return false;
    } finally {
      _loading = false;
      notifyListeners();
    }
  }

  /// Internal: POST /auth/login → { token }, then GET /auth/me for user info.
  Future<bool> _loginInternal(String email, String password) async {
    final loginResp = await ApiClient.instance.post(
      '/auth/login',
      data: {'email': email, 'password': password},
    );
    final token = loginResp.data['token'] as String;
    ApiClient.instance.setJwt(token);

    // Fetch full user object
    final meResp = await ApiClient.instance.get('/auth/me');
    final user = User.fromJson(meResp.data as Map<String, dynamic>);
    _user = user;
    await _saveToPrefs(token, user);
    return true;
  }

  Future<void> logout() async {
    try {
      await ApiClient.instance.post('/auth/logout');
    } catch (_) {
      // Best-effort — always clear local state
    }
    _user = null;
    ApiClient.instance.clearJwt();
    await _clearPrefs();
    notifyListeners();
  }

  void clearError() {
    _error = null;
    notifyListeners();
  }

  // ── Helpers ────────────────────────────────────────────────────────────────

  String _extractError(DioException e) {
    switch (e.type) {
      case DioExceptionType.connectionTimeout:
      case DioExceptionType.sendTimeout:
        return 'Connection timed out. Is the server running?';
      case DioExceptionType.receiveTimeout:
        return 'Server took too long to respond. Try again.';
      case DioExceptionType.connectionError:
        return 'Cannot reach server. Check your network and server IP.';
      default:
        break;
    }
    final data = e.response?.data;
    if (data is Map && data['error'] != null) return data['error'].toString();
    if (data is Map && data['message'] != null) return data['message'].toString();
    return e.message ?? 'An unexpected error occurred';
  }
}
