import 'package:flutter/material.dart';
import 'package:dio/dio.dart';
import '../../core/api_client.dart';
import '../../core/models.dart';

/// Manages messages for a single conversation and handles sending chat questions.
///
/// Backend:
///   GET  /conversations/[id]/messages          - returns List of Message
///   POST /chat  { question, conversation_id }  - returns { answer, sources }
class ChatProvider extends ChangeNotifier {
  final String conversationId;

  List<Message> _messages = [];
  bool _loading = false;     // Loading history
  bool _sending = false;     // Sending a new question
  String? _error;

  List<Message> get messages => _messages;
  bool get loading => _loading;
  bool get sending => _sending;
  String? get error => _error;

  ChatProvider({required this.conversationId});

  /// Fetch previous messages for this conversation
  Future<void> fetchMessages() async {
    _loading = true;
    _error = null;
    notifyListeners();

    try {
      final res = await ApiClient.instance.get('/conversations/$conversationId/messages');
      final list = (res.data as List).cast<Map<String, dynamic>>();
      _messages = list.map((m) => Message.fromJson(m)).toList();
    } on DioException catch (e) {
      _error = _extractError(e);
    } catch (e) {
      _error = e.toString();
    } finally {
      _loading = false;
      notifyListeners();
    }
  }

  /// Send a question to the RAG endpoint
  Future<void> sendMessage(String text) async {
    // 1. Add user message optimistically
    final userMsg = Message(
      id: 'optimistic_${DateTime.now().millisecondsSinceEpoch}',
      role: 'user',
      content: text,
    );
    _messages.add(userMsg);
    _sending = true;
    _error = null;
    notifyListeners();

    try {
      final res = await ApiClient.instance.post('/chat', data: {
        'conversation_id': conversationId,
        'question': text,
      });

      // 2. Add AI response from RAG
      final aiMsg = Message(
        id: 'ai_${DateTime.now().millisecondsSinceEpoch}',
        role: 'ai',
        content: res.data['answer'] as String,
        sources: (res.data['sources'] as List).map((s) => Source.fromJson(s as Map<String, dynamic>)).toList(),
      );
      _messages.add(aiMsg);
    } on DioException catch (e) {
      _error = _extractError(e);
      // Remove the optimistic user message if failed
      _messages.removeLast();
    } catch (e) {
      _error = e.toString();
      _messages.removeLast();
    } finally {
      _sending = false;
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
