import 'package:flutter/material.dart';

import 'dashboard_screen.dart';
import 'face_registration_screen.dart';
import '../services/api_service.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _emailController = TextEditingController();
  final _otpController = TextEditingController();
  final _apiService = ApiService();

  bool _isOtpSent = false;
  bool _isLoading = false;

  String get _email => _emailController.text.trim().toLowerCase();

  Future<void> _sendOtp() async {
    final email = _email;
    if (!RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$').hasMatch(email)) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Enter a valid email address.")),
      );
      return;
    }

    setState(() => _isLoading = true);
    final result = await _apiService.sendEmailOtp(email);
    if (!mounted) return;
    setState(() => _isLoading = false);

    if (result["success"] == true) {
      setState(() => _isOtpSent = true);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            "If this account is registered, a sign-in code is on its way.",
          ),
          backgroundColor: Colors.green,
        ),
      );
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            result["message"] ?? "Could not send the sign-in code.",
          ),
          backgroundColor: Colors.red,
        ),
      );
    }
  }

  Future<void> _verifyOtp() async {
    final otp = _otpController.text.trim();
    if (!RegExp(r'^\d{6}$').hasMatch(otp)) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text("Enter the 6-digit code from your email."),
        ),
      );
      return;
    }

    setState(() => _isLoading = true);
    final result = await _apiService.verifyEmailOtp(_email, otp);
    if (!mounted) return;
    setState(() => _isLoading = false);

    if (result["success"] != true) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            result["message"] ?? "The code is invalid or has expired.",
          ),
          backgroundColor: Colors.red,
        ),
      );
      return;
    }

    final userId = result["user_id"] as int?;
    if (userId == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            "The account could not be loaded. Please contact your administrator.",
          ),
          backgroundColor: Colors.red,
        ),
      );
      return;
    }

    if (result["needs_face_setup"] == true) {
      await Navigator.pushReplacement(
        context,
        MaterialPageRoute(
          builder: (context) => FaceRegistrationScreen(
            userId: userId,
            userName: result["name"] as String? ?? "Faculty Member",
          ),
        ),
      );
    } else {
      await Navigator.pushReplacement(
        context,
        MaterialPageRoute(
          builder: (context) => DashboardScreen(userId: userId),
        ),
      );
    }
  }

  void _editEmail() {
    setState(() {
      _isOtpSent = false;
      _otpController.clear();
    });
  }

  @override
  void dispose() {
    _emailController.dispose();
    _otpController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF5F7FB),
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 480),
              child: Card(
                elevation: 2,
                clipBehavior: Clip.antiAlias,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Padding(
                  padding: const EdgeInsets.all(32),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      const Icon(
                        Icons.fact_check,
                        size: 52,
                        color: Colors.blue,
                      ),
                      const SizedBox(height: 20),
                      const Text(
                        "Smart Attendance",
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          fontSize: 28,
                          fontWeight: FontWeight.bold,
                          color: Colors.blue,
                        ),
                      ),
                      const SizedBox(height: 8),
                      Text(
                        "Faculty & Staff Portal",
                        textAlign: TextAlign.center,
                        style: TextStyle(fontSize: 16, color: Colors.grey[700]),
                      ),
                      const SizedBox(height: 32),
                      TextField(
                        controller: _emailController,
                        readOnly: _isOtpSent,
                        keyboardType: TextInputType.emailAddress,
                        autofillHints: const [AutofillHints.email],
                        textInputAction: _isOtpSent
                            ? TextInputAction.next
                            : TextInputAction.done,
                        onSubmitted: (_) {
                          if (!_isOtpSent && !_isLoading) _sendOtp();
                        },
                        decoration: const InputDecoration(
                          labelText: "Work email",
                          hintText: "name@college.edu",
                          prefixIcon: Icon(Icons.email_outlined),
                          border: OutlineInputBorder(),
                        ),
                      ),
                      if (_isOtpSent) ...[
                        const SizedBox(height: 18),
                        TextField(
                          controller: _otpController,
                          keyboardType: TextInputType.number,
                          autofillHints: const [AutofillHints.oneTimeCode],
                          maxLength: 6,
                          onSubmitted: (_) {
                            if (!_isLoading) _verifyOtp();
                          },
                          decoration: const InputDecoration(
                            labelText: "Email verification code",
                            prefixIcon: Icon(Icons.lock_outline),
                            border: OutlineInputBorder(),
                            counterText: "",
                          ),
                        ),
                      ],
                      const SizedBox(height: 20),
                      FilledButton(
                        onPressed: _isLoading
                            ? null
                            : (_isOtpSent ? _verifyOtp : _sendOtp),
                        style: FilledButton.styleFrom(
                          minimumSize: const Size.fromHeight(52),
                        ),
                        child: _isLoading
                            ? const SizedBox(
                                height: 22,
                                width: 22,
                                child: CircularProgressIndicator(
                                  strokeWidth: 2,
                                  color: Colors.white,
                                ),
                              )
                            : Text(
                                _isOtpSent
                                    ? "VERIFY & SIGN IN"
                                    : "EMAIL ME A SIGN-IN CODE",
                              ),
                      ),
                      if (_isOtpSent)
                        TextButton(
                          onPressed: _isLoading ? null : _editEmail,
                          child: const Text("Use a different email address"),
                        ),
                      const SizedBox(height: 12),
                      Text(
                        "A one-time code is required each time you sign in.",
                        textAlign: TextAlign.center,
                        style: TextStyle(fontSize: 13, color: Colors.grey[600]),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
