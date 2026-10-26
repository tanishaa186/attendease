import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

class ApiService {
  static const String baseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://127.0.0.1:8000',
  );

  Map<String, dynamic> _decodeResponse(http.Response response) {
    final decoded = Map<String, dynamic>.from(jsonDecode(response.body) as Map);
    if (response.statusCode >= 200 && response.statusCode < 300) {
      return decoded;
    }
    return {
      "success": false,
      "message":
          decoded["detail"] ?? "Request failed (${response.statusCode}).",
    };
  }

  Future<Map<String, dynamic>> sendEmailOtp(String email) async {
    try {
      final response = await http.post(
        Uri.parse("$baseUrl/auth/email/send-otp"),
        headers: {"Content-Type": "application/json"},
        body: jsonEncode({"email": email}),
      );
      return _decodeResponse(response);
    } catch (e) {
      return {
        "success": false,
        "message": "Could not reach the attendance server at $baseUrl: $e",
      };
    }
  }

  Future<Map<String, dynamic>> verifyEmailOtp(String email, String otp) async {
    try {
      final response = await http.post(
        Uri.parse("$baseUrl/auth/email/verify-otp"),
        headers: {"Content-Type": "application/json"},
        body: jsonEncode({"email": email, "otp": otp}),
      );
      return _decodeResponse(response);
    } catch (e) {
      return {
        "success": false,
        "message": "Could not reach the attendance server at $baseUrl: $e",
      };
    }
  }

  Future<Map<String, dynamic>> checkUserExists(String phone) async {
    try {
      final response = await http.get(Uri.parse("$baseUrl/check-user/$phone"));
      if (response.statusCode == 200) {
        return jsonDecode(response.body);
      }
      return {"exists": false};
    } catch (e) {
      debugPrint("Error checking user: $e");
      return {"exists": false};
    }
  }

  Future<Map<String, dynamic>> sendOtp(
    String phone, {
    String method = "sms",
  }) async {
    try {
      final response = await http.post(
        Uri.parse("$baseUrl/send-otp/$phone?method=$method"),
      );
      return jsonDecode(response.body);
    } catch (e) {
      debugPrint("Error sending OTP: $e");
      return {"message": "Error connection to server"};
    }
  }

  Future<Map<String, dynamic>> verifyOtp(String phone, String otp) async {
    try {
      final response = await http.post(
        Uri.parse("$baseUrl/verify-otp"),
        headers: {"Content-Type": "application/json"},
        body: jsonEncode({"phone": phone, "otp": otp}),
      );
      if (response.statusCode == 200) {
        return jsonDecode(response.body);
      }
      return {"success": false, "message": "Invalid OTP"};
    } catch (e) {
      debugPrint("Error verifying OTP: $e");
      return {"success": false, "message": "Server error"};
    }
  }

  Future<bool> register({
    required String facultyId,
    required String name,
    required String email,
    required String phone,
    required String role,
    required int departmentId,
    String? faceImageBase64,
  }) async {
    try {
      final response = await http.post(
        Uri.parse("$baseUrl/register"),
        headers: {"Content-Type": "application/json"},
        body: jsonEncode({
          "faculty_id": facultyId,
          "name": name,
          "email": email,
          "phone": phone,
          "role": role,
          "department_id": departmentId,
          "face_image": faceImageBase64,
        }),
      );
      return response.statusCode == 200;
    } catch (e) {
      debugPrint("Error during registration: $e");
      return false;
    }
  }

  Future<bool> registerFaceOnly({
    required int userId,
    required String faceImageBase64,
  }) async {
    try {
      final response = await http.post(
        Uri.parse("$baseUrl/register-face-only"),
        headers: {"Content-Type": "application/json"},
        body: jsonEncode({
          "user_id": userId,
          "lat": 0.0,
          "lng": 0.0,
          "face_image_base64": faceImageBase64,
        }),
      );
      return response.statusCode == 200;
    } catch (e) {
      debugPrint("Error during face registration: $e");
      return false;
    }
  }

  Future<bool> punchIn({
    required int userId,
    required double lat,
    required double lng,
    required String faceImageBase64,
  }) async {
    try {
      final response = await http.post(
        Uri.parse("$baseUrl/attendance/punch-in"),
        headers: {"Content-Type": "application/json"},
        body: jsonEncode({
          "user_id": userId,
          "lat": lat,
          "lng": lng,
          "face_image_base64": faceImageBase64,
        }),
      );
      return response.statusCode == 200;
    } catch (e) {
      debugPrint("Error punching in: $e");
      return false;
    }
  }

  Future<Map<String, dynamic>?> getHodSummary() async {
    try {
      final response = await http.get(
        Uri.parse("$baseUrl/hod/dashboard-summary"),
      );
      if (response.statusCode == 200) {
        return jsonDecode(response.body);
      }
      return null;
    } catch (e) {
      debugPrint("Error fetching HOD summary: $e");
      return null;
    }
  }

  Future<bool> applyLeave({
    required int userId,
    required String type,
    required String reason,
    required DateTime startDate,
    required DateTime endDate,
  }) async {
    try {
      final response = await http.post(
        Uri.parse("$baseUrl/leave/apply"),
        headers: {"Content-Type": "application/json"},
        body: jsonEncode({
          "user_id": userId,
          "leave_type": type,
          "reason": reason,
          "start_date": startDate.toIso8601String(),
          "end_date": endDate.toIso8601String(),
        }),
      );
      return response.statusCode == 200;
    } catch (e) {
      debugPrint("Error applying for leave: $e");
      return false;
    }
  }
}
