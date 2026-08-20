import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../core/theme.dart';
import '../../core/models.dart';
import '../auth/auth_provider.dart';
import '../chat/chat_screen.dart';
import 'conversations_provider.dart';
import 'create_conversation_dialog.dart';

/// Main screen that lists the user's conversations.
class ConversationsListScreen extends StatefulWidget {
  const ConversationsListScreen({super.key});

  @override
  State<ConversationsListScreen> createState() =>
      _ConversationsListScreenState();
}

class _ConversationsListScreenState extends State<ConversationsListScreen> {
  @override
  void initState() {
    super.initState();
    // Fetch conversations once the widget is mounted
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<ConversationsProvider>().fetchConversations();
    });
  }

  Future<void> _openCreateDialog() async {
    await showDialog(
      context: context,
      builder: (_) => const CreateConversationDialog(),
    );
  }

  void _openChat(Conversation conversation) {
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => ChatScreen(conversation: conversation),
      ),
    );
  }

  Future<void> _confirmDelete(Conversation conv) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: AppTheme.surface,
        title: const Text('Delete Conversation'),
        content: Text('Delete "${conv.title}"? This cannot be undone.'),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancel')),
          TextButton(
              onPressed: () => Navigator.pop(ctx, true),
              style: TextButton.styleFrom(foregroundColor: AppTheme.error),
              child: const Text('Delete')),
        ],
      ),
    );
    if (confirmed == true && mounted) {
      await context.read<ConversationsProvider>().deleteConversation(conv.id);
    }
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();
    final provider = context.watch<ConversationsProvider>();

    return Scaffold(
      appBar: AppBar(
        title: const Text('Conversations'),
        actions: [
          // Current user email chip
          if (auth.user != null)
            Padding(
              padding: const EdgeInsets.only(right: 4),
              child: Center(
                child: Text(
                  auth.user!.email,
                  style: Theme.of(context)
                      .textTheme
                      .bodySmall
                      ?.copyWith(color: AppTheme.onSurfaceDim),
                ),
              ),
            ),
          // Logout button
          IconButton(
            icon: const Icon(Icons.logout_rounded),
            tooltip: 'Logout',
            onPressed: () async {
              await auth.logout();
            },
          ),
        ],
      ),
      body: RefreshIndicator(
        color: AppTheme.primary,
        onRefresh: () => context.read<ConversationsProvider>().fetchConversations(),
        child: _buildBody(provider),
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: _openCreateDialog,
        backgroundColor: AppTheme.primary,
        foregroundColor: Colors.white,
        icon: const Icon(Icons.add_rounded),
        label: const Text('New Chat'),
      ),
    );
  }

  Widget _buildBody(ConversationsProvider provider) {
    // ── Loading ────────────────────────────────────────────────────────────
    if (provider.loading && provider.conversations.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }

    // ── Error ──────────────────────────────────────────────────────────────
    if (provider.error != null && provider.conversations.isEmpty) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.error_outline, size: 48, color: AppTheme.error),
              const SizedBox(height: 12),
              Text(provider.error!,
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.bodyMedium),
              const SizedBox(height: 20),
              ElevatedButton(
                onPressed: () =>
                    context.read<ConversationsProvider>().fetchConversations(),
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
      );
    }

    // ── Empty ──────────────────────────────────────────────────────────────
    if (provider.conversations.isEmpty) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.chat_bubble_outline_rounded,
                size: 64, color: AppTheme.onSurfaceDim.withValues(alpha: 0.5)),
            const SizedBox(height: 16),
            Text('No conversations yet',
                style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            Text('Tap "New Chat" to get started',
                style: Theme.of(context).textTheme.bodySmall),
          ],
        ),
      );
    }

    // ── List ───────────────────────────────────────────────────────────────
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 600),
        child: ListView.separated(
          padding: const EdgeInsets.all(16),
          itemCount: provider.conversations.length,
          separatorBuilder: (_, _i) => const SizedBox(height: 8),
          itemBuilder: (ctx, i) {
            final conv = provider.conversations[i];
            return _ConversationTile(
              conversation: conv,
              onTap: () => _openChat(conv),
              onDelete: () => _confirmDelete(conv),
            );
          },
        ),
      ),
    );
  }
}

class _ConversationTile extends StatelessWidget {
  final Conversation conversation;
  final VoidCallback onTap;
  final VoidCallback onDelete;

  const _ConversationTile({
    required this.conversation,
    required this.onTap,
    required this.onDelete,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      child: ListTile(
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        leading: Container(
          width: 44,
          height: 44,
          decoration: BoxDecoration(
            color: AppTheme.primary.withValues(alpha: 0.15),
            borderRadius: BorderRadius.circular(10),
          ),
          child: const Icon(Icons.chat_bubble_rounded,
              color: AppTheme.primary, size: 22),
        ),
        title: Text(conversation.title,
            style: Theme.of(context).textTheme.titleMedium),
        trailing: IconButton(
          icon: const Icon(Icons.delete_outline_rounded,
              color: AppTheme.onSurfaceDim),
          onPressed: onDelete,
        ),
        onTap: onTap,
      ),
    );
  }
}
