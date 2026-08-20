import 'dart:io';

class PlatformUtil {
  static String get baseUrl {
    // In Android emulator, localhost refers to the emulator itself.
    // Use 10.0.2.2 to reach the host machine.
    if (Platform.isAndroid) {
      return 'http://10.0.2.2:3000';
    }
    // For iOS simulator, desktop, and other platforms use localhost.
    return 'http://localhost:3000';
  }
}
