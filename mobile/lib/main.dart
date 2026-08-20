import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'core/theme.dart';
import 'features/auth/auth_provider.dart';
import 'features/auth/login_screen.dart';
import 'features/conversations/conversations_provider.dart';
import 'features/conversations/conversations_list_screen.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const AthleticRAGApp());
}

class AthleticRAGApp extends StatelessWidget {
  const AthleticRAGApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        // Auth state — top-level, always alive
        ChangeNotifierProvider(create: (_) => AuthProvider()),

        // Conversations list — alive while the app is open
        ChangeNotifierProvider(create: (_) => ConversationsProvider()),
      ],
      child: MaterialApp(
        title: 'AthleticRAG',
        debugShowCheckedModeBanner: false,
        theme: AppTheme.dark,
        home: const _AuthGate(),
      ),
    );
  }
}

/// Decides which screen to show based on authentication state.
/// Listens to AuthProvider and switches between Login and Conversations.
class _AuthGate extends StatelessWidget {
  const _AuthGate();

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();

    // Still loading JWT from SharedPreferences
    if (!auth.isAuthenticated && auth.loading) {
      return const Scaffold(
        body: Center(child: CircularProgressIndicator()),
      );
    }

    if (auth.isAuthenticated) {
      return const ConversationsListScreen();
    }

    return const LoginScreen();
  }
}
