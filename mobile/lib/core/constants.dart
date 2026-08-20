class ApiEndpoints {
  static const String register = '/auth/register';
  static const String login = '/auth/login';
  static const String me = '/auth/me';
  static const String conversations = '/conversations';
  static const String createConversation = '/conversations'; // POST
  static const String messages =
      '/conversations/{id}/messages'; // GET messages for a conversation
  static const String sendMessage =
      '/conversations/{id}/messages'; // POST new user question
}
