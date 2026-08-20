import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../core/theme.dart';
import 'conversations_provider.dart';

class CreateConversationDialog extends StatefulWidget {
  const CreateConversationDialog({super.key});

  @override
  State<CreateConversationDialog> createState() => _CreateConversationDialogState();
}

class _CreateConversationDialogState extends State<CreateConversationDialog> {
  final _ctrl = TextEditingController();
  final _formKey = GlobalKey<FormState>();

  @override
  void dispose() {
    _ctrl.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate()) return;
    
    final provider = context.read<ConversationsProvider>();
    final conv = await provider.createConversation(_ctrl.text.trim());
    
    if (mounted) {
      if (conv == null && provider.error != null) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(provider.error!)),
        );
      } else {
        Navigator.pop(context, conv);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final loading = context.watch<ConversationsProvider>().loading;

    return AlertDialog(
      backgroundColor: AppTheme.surface,
      title: const Text('New Conversation'),
      content: Form(
        key: _formKey,
        child: TextFormField(
          controller: _ctrl,
          autofocus: true,
          decoration: const InputDecoration(
            hintText: 'e.g. Pre-workout advice',
            labelText: 'Topic',
          ),
          validator: (v) => (v == null || v.trim().isEmpty) ? 'Enter a topic' : null,
          onFieldSubmitted: (_) => _submit(),
        ),
      ),
      actions: [
        TextButton(
          onPressed: loading ? null : () => Navigator.pop(context),
          child: const Text('Cancel'),
        ),
        ElevatedButton(
          onPressed: loading ? null : _submit,
          child: loading
              ? const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                )
              : const Text('Create'),
        ),
      ],
    );
  }
}
