import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// App-wide design tokens and ThemeData.
/// Uses a deep navy / orange accent palette (athletic / sports feel).
class AppTheme {
  // ── Colour palette ────────────────────────────────────────────────────────
  static const Color primary = Color(0xFFFF6B35); // vibrant orange
  static const Color primaryDark = Color(0xFFE05525);
  static const Color background = Color(0xFF0F1117); // near-black
  static const Color surface = Color(0xFF1A1D27); // dark navy card
  static const Color surfaceLight = Color(0xFF252836); // slightly lighter
  static const Color onBackground = Color(0xFFF5F5F5);
  static const Color onSurface = Color(0xFFE0E0E0);
  static const Color onSurfaceDim = Color(0xFF9B9EB2);
  static const Color userBubble = Color(0xFFFF6B35);
  static const Color aiBubble = Color(0xFF252836);
  static const Color divider = Color(0xFF2E3147);
  static const Color error = Color(0xFFFF5252);

  // ── ThemeData factory ─────────────────────────────────────────────────────
  static ThemeData get dark {
    final base = ThemeData.dark();
    final textTheme = GoogleFonts.interTextTheme(base.textTheme).copyWith(
      displayLarge: GoogleFonts.inter(
        color: onBackground,
        fontSize: 32,
        fontWeight: FontWeight.w700,
      ),
      headlineMedium: GoogleFonts.inter(
        color: onBackground,
        fontSize: 22,
        fontWeight: FontWeight.w600,
      ),
      titleLarge: GoogleFonts.inter(
        color: onBackground,
        fontSize: 18,
        fontWeight: FontWeight.w600,
      ),
      titleMedium: GoogleFonts.inter(
        color: onBackground,
        fontSize: 16,
        fontWeight: FontWeight.w500,
      ),
      bodyLarge: GoogleFonts.inter(color: onSurface, fontSize: 15),
      bodyMedium: GoogleFonts.inter(color: onSurface, fontSize: 14),
      bodySmall: GoogleFonts.inter(color: onSurfaceDim, fontSize: 12),
    );

    return base.copyWith(
      colorScheme: const ColorScheme.dark(
        primary: primary,
        secondary: primaryDark,
        surface: surface,
        error: error,
        onPrimary: Colors.white,
        onSecondary: Colors.white,
        onSurface: onSurface,
        onError: Colors.white,
      ),
      scaffoldBackgroundColor: background,
      appBarTheme: AppBarTheme(
        backgroundColor: surface,
        elevation: 0,
        centerTitle: false,
        iconTheme: const IconThemeData(color: onBackground),
        titleTextStyle: GoogleFonts.inter(
          color: onBackground,
          fontSize: 18,
          fontWeight: FontWeight.w600,
        ),
      ),
      textTheme: textTheme,
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: surfaceLight,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: BorderSide.none,
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: divider, width: 1),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: primary, width: 1.5),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: error, width: 1),
        ),
        hintStyle: GoogleFonts.inter(color: onSurfaceDim, fontSize: 14),
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 16,
          vertical: 14,
        ),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          backgroundColor: primary,
          foregroundColor: Colors.white,
          minimumSize: const Size.fromHeight(52),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
          ),
          textStyle: GoogleFonts.inter(
            fontSize: 15,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(foregroundColor: primary),
      ),
      cardTheme: CardThemeData(
        color: surface,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(14),
          side: const BorderSide(color: divider, width: 1),
        ),
      ),
      dividerColor: divider,
      snackBarTheme: const SnackBarThemeData(
        backgroundColor: surfaceLight,
        contentTextStyle: TextStyle(color: onBackground),
      ),
    );
  }
}
