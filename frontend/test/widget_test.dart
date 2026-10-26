import 'package:flutter_test/flutter_test.dart';
import 'package:faculty_attendance/main.dart';

void main() {
  testWidgets('shows email sign-in form', (WidgetTester tester) async {
    await tester.pumpWidget(const FacultyAttendanceApp());
    await tester.pump();

    expect(find.text('Smart Attendance'), findsOneWidget);
    expect(find.text('Work email'), findsOneWidget);
    expect(find.text('EMAIL ME A SIGN-IN CODE'), findsOneWidget);
  });
}
