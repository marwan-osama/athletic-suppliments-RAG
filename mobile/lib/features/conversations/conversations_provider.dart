import 'package:flutter/material.dart';
import 'package:dio/dio.dart';
import '../../core/api_client.dart';
import '../../core/models.dart';

/// Manages the list of conversations for the current user.
/// 
/// Backend:
///   GET  /conversations        → List<Conversation>
///   POST /conversations        → { title } → Conversation
///   DELETE /conversations/:id  → OK
class ConversationsProvider extends ChangeNotifier {
  List<Conversation> _conversations = [];
  bool _loading = false;
  String? _error;

  List<Conversation> get conversations => _conversations;
  bool get loading => _loading;
  String? get error => _error;

  Future<void> fetchConversations() async {
    _loading = true;
    _error = null;
    notifyListeners();

    try {
      final res = await ApiClient.instance.get('/conversations');
      final list = (res.data as List).cast<Map<String, dynamic>>();
      _conversations = list.map((c) => Conversation.fromJson(c)).toList();
    } on DioException catch (e) {
      _error = _extractError(e);
    } catch (e) {
      _error = e.toString();
    } finally {
      _loading = false;
      notifyListeners();
    }
  }

  Future<Conversation?> createConversation(String title) async {
    _loading = true;
    _error = null;
    notifyListeners();

    try {
      final res = await ApiClient.instance.post('/conversations', data: {
        'title': title,
      });
      final conv = Conversation.fromJson(res.data as Map<String, dynamic>);
      _conversations.insert(0, conv);
      return conv;
    } on DioException catch (e) {
      _error = _extractError(e);
      return null;
    } catch (e) {
      _error = e.toString();
      return null;
    } finally {
      _loading = false;
      notifyListeners();
    }
  }

  Future<void> deleteConversation(String id) async {
    try {
      await ApiClient.instance.delete('/conversations/$id');
      _conversations.removeWhere((c) => c.id == id);
      notifyListeners();
    } on DioException catch (e) {
      _error = _extractError(e);
      notifyListeners();
    }
  }

  void clearError() {
    _error = null;
    notifyListeners();
  }

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
