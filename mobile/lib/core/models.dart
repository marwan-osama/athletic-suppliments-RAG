import 'dart:convert';

/// ── User ──────────────────────────────────────────────────────────────────
class User {
  final String id;
  final String email;

  User({required this.id, required this.email});

  factory User.fromJson(Map<String, dynamic> json) => User(
    id: json['_id']?.toString() ?? json['id']?.toString() ?? '',
    email: json['email'] ?? '',
  );

  /// Serialise to a JSON string for SharedPreferences storage.
  String toJsonString() => jsonEncode({'id': id, 'email': email});

  /// Deserialise from a JSON string stored in SharedPreferences.
  factory User.fromJsonString(String s) => User.fromJson(jsonDecode(s));
}

/// ── Conversation ─────────────────────────────────────────────────────────
class Conversation {
  final String id;
  final String title;

  Conversation({required this.id, required this.title});

  factory Conversation.fromJson(Map<String, dynamic> json) => Conversation(
    id: json['_id']?.toString() ?? json['id']?.toString() ?? '',
    title: json['title'] ?? 'Untitled',
  );
}

/// ── Message ──────────────────────────────────────────────────────────────
class Message {
  final String id;

  /// Either 'user' or 'assistant'
  final String role;
  final String content;
  final List<Source> sources;

  Message({
    required this.id,
    required this.role,
    required this.content,
    this.sources = const [],
  });

  factory Message.fromJson(Map<String, dynamic> json) {
    final rawSources = json['sources'] as List<dynamic>? ?? [];
    return Message(
      id: json['_id']?.toString() ?? json['id']?.toString() ?? '',
      role: json['role'] ?? 'assistant',
      content: json['content'] ?? '',
      sources: rawSources
          .map((e) => Source.fromJson(e as Map<String, dynamic>))
          .toList(),
    );
  }
}

/// ── Source (RAG citations) ────────────────────────────────────────────────
class Source {
  final String title;
  final String content;
  final String? url;

  Source({required this.title, required this.content, this.url});

  factory Source.fromJson(Map<String, dynamic> json) => Source(
    title: json['title'] ?? json['source'] ?? '',
    content: json['content'] ?? json['text'] ?? '',
    url: json['url'],
  );
}
