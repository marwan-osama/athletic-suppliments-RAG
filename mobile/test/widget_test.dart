import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/main.dart';

void main() {
  testWidgets('App launches smoke test', (WidgetTester tester) async {
    await tester.pumpWidget(const AthleticRAGApp());
    // The app should build without throwing
    expect(find.byType(AthleticRAGApp), findsOneWidget);
  });
}
