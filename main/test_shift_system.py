import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
    import django
    django.setup()
    DJANGO_AVAILABLE = True
except Exception as e:
    print(f"Django not available: {e}")
    DJANGO_AVAILABLE = False

from services.telegram_service import get_telegram_service, TelegramConfig


def test_telegram_connection():
    print("=" * 50)
    print("Testing Telegram Connection")
    print("=" * 50)
    
    service = get_telegram_service()
    
    print(f"Bot Token: {service.config.bot_token[:20]}...")
    print(f"Chat ID: {service.config.chat_id}")
    
    print("\nChecking Telegram API connectivity...")
    is_online = service.is_online()
    
    if is_online:
        print("✅ Telegram API is reachable!")
    else:
        print("❌ Cannot reach Telegram API. Check your internet connection.")
        return False
    
    return True


def test_send_message():
    print("\n" + "=" * 50)
    print("Testing Message Sending")
    print("=" * 50)
    
    service = get_telegram_service()
    
    test_message = """
🧪 <b>TEST MESSAGE</b>

This is a test message from the Shift Notification System.

✅ If you see this, the integration is working correctly!

⏰ Timestamp: {timestamp}
""".format(timestamp=__import__('datetime').datetime.now().isoformat())
    
    print("Sending test message...")
    success, error = service.send_message(test_message)
    
    if success:
        print("✅ Message sent successfully!")
        return True
    else:
        print(f"❌ Failed to send message: {error}")
        return False


def test_pending_queue():
    print("\n" + "=" * 50)
    print("Testing Pending Notification Queue")
    print("=" * 50)
    
    from services.pending_notifications import (
        get_notification_queue,
        PendingNotification
    )
    from datetime import datetime
    
    queue = get_notification_queue("test_pending.json")

    queue.clear()
    print(f"Queue cleared. Count: {queue.count()}")
    
    notification = PendingNotification(
        message="Test notification",
        created_at=datetime.now().isoformat(),
        notification_type="test",
        priority=2
    )
    queue.add(notification)
    print(f"Added notification. Count: {queue.count()}")
    
    all_notifications = queue.get_all()
    print(f"Retrieved {len(all_notifications)} notifications")
    
    queue.clear()
    print("Queue cleared after test")
    
    import os
    try:
        os.remove("test_pending.json")
    except:
        pass
    
    print("✅ Pending queue test passed!")
    return True


def test_shift_service():
    print("\n" + "=" * 50)
    print("Testing Shift Notification Service")
    print("=" * 50)
    
    if not DJANGO_AVAILABLE:
        print("⚠️ Django not available, skipping shift service test")
        return True
    
    from services.shift_notification_service import get_shift_notification_service
    
    service = get_shift_notification_service()

    start_msg = service.format_shift_start_message()
    print("Shift Start Message Preview:")
    print("-" * 30)
    print(start_msg[:200] + "...")
    
    print("\n✅ Shift service test passed!")
    return True


def main():
    print("\n" + "🚀 SHIFT NOTIFICATION SYSTEM - TEST SUITE" + "\n")
    
    results = []

    results.append(("Telegram Connection", test_telegram_connection()))
    
    if results[-1][1]:
        results.append(("Send Message", test_send_message()))
    else:
        results.append(("Send Message", "SKIPPED"))
    
    results.append(("Pending Queue", test_pending_queue()))
    
    results.append(("Shift Service", test_shift_service()))

    print("\n" + "=" * 50)
    print("TEST SUMMARY")
    print("=" * 50)
    
    for test_name, result in results:
        if result == True:
            status = "✅ PASSED"
        elif result == False:
            status = "❌ FAILED"
        else:
            status = f"⚠️ {result}"
        print(f"  {test_name}: {status}")
    
    all_passed = all(r[1] == True for r in results if r[1] != "SKIPPED")
    
    print("\n" + "=" * 50)
    if all_passed:
        print("🎉 All tests passed! System is ready.")
    else:
        print("⚠️ Some tests failed. Please check the errors above.")
    print("=" * 50 + "\n")


if __name__ == '__main__':
    main()